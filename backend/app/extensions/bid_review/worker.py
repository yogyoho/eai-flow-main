"""bid_review worker(Task 9)——状态机推进 + claimer 循环 + gateway 生命周期入口。

状态机(设计文档 §4.3):created→parsing→extracting→awaiting_confirm→running→done|failed。
advance_task 为可注入 session/extract_fn 的单步推进函数(测试直调);routers 的
_enqueue_docs 直推走 created 守卫置换(防与 claimer 双跑),claimer 领取后以已持有
入口(parsing|extracting)直进同一管线。
claimer 照 translation worker 惯例:POLL_SECONDS env、SLOTS=1、boot recovery
(running|parsing→extracting)、基础设施异常指数退避 ≤3 → failed(_infra_fail,
终态不复活)。fix-round(2026-10-29 评审):领取入口以领取标记态返回(parsing),
杜绝旧实现守卫二次置换零命中导致 claimed 任务死锁 parsing 的缺陷。

Task 14(2026-10-29):审查阶段按 rule.type 分派——deterministic→run_det_rule /
semantic|hybrid→run_sem_rule(model_fn 经 _wrap_model_fn 注入,response.content 归一
str,A12 T14 约束②);逐规则隔离扩展到 sem/hyb(模型不可用/接线失败降级 need_human,
T9 先例);done 帧 progress 增 durations(各阶段耗时)与 summary(汇总分级,A12 T14
约束①:正式违规计数不含 need_human 条目,待人工单列,routers issues API 共用
summarize_issues 同一口径)。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.bid_review import crud
from app.extensions.bid_review.engine.extract import ExtractFn, ExtractNotConfigured, apply_adjudications, build_baseline
from app.extensions.bid_review.engine.llm_runner import run_sem_rule
from app.extensions.bid_review.engine.rule_runner import _need_human, attach_evidence, load_rulepack, run_det_rule
from app.extensions.bid_review.models import BaselinePackage, ReviewTask
from app.extensions.database import get_session_factory

logger = logging.getLogger(__name__)

RULEPACK_PATH = Path(__file__).parent / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml"
POLL_SECONDS = float(os.environ.get("EAI_BID_REVIEW_POLL_SECONDS", "5"))
SLOTS = 1  # 单槽:审查为重 LLM 任务,先串行;提并发再扩(translation D16 先例)
MAX_INFRA_RETRIES = int(os.environ.get("EAI_BID_REVIEW_INFRA_RETRIES", "3"))
BACKOFF_CAP_SECONDS = 60.0

SEVERITY_ORDER = ("fatal", "major", "minor", "info")


class ModelNotConfigured(RuntimeError):
    """生产 sem/hyb 裁决模型未接线的显式缺口(ExtractNotConfigured 同款先例)。"""


# ── 模型接线(Task 14;A12 T14 约束②归一在 worker 侧,engine._call_model 不改)────


def _content_to_str(content) -> str:
    """response.content 归一为 str:LangChain 分块 list 形态(list 时拼接各 text 部件;
    str 项直取,dict 项取 text 键)——不归一则 check_schema 两试皆败→整规则静默空产出。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict) and isinstance(chunk.get("text"), str):
                parts.append(chunk["text"])
        return "".join(parts)
    return str(content) if content is not None else ""


def _wrap_model_fn(model_fn):
    """模型接线包装层:调注入的 raw model_fn(同步/异步 callable 均可),把
    response.content 归一为 str 后以带 .content 的轻量响应对象回交引擎(契约与
    llm_runner._call_model 的 getattr(response, "content") 对齐)。"""

    async def _wrapped(messages):
        response = model_fn(messages)
        if inspect.isawaitable(response):
            response = await response
        raw = getattr(response, "content", response)
        return SimpleNamespace(content=_content_to_str(raw))

    return _wrapped


def _resolve_model_name() -> str | None:
    """生产模型选择(translation worker 同款先例):EAI_BID_REVIEW_MODEL env 优先
    (值须在 config.yaml models 内,非法值回落),否则 config.yaml 首项;无可用模型
    返回 None(调用方抛 *NotConfigured,绝不静默假交付)。"""
    from deerflow.config import get_app_config

    names = [m.name for m in get_app_config().models]
    env = os.environ.get("EAI_BID_REVIEW_MODEL")
    if env and env in names:
        return env
    return names[0] if names else None


def _default_model_fn():
    """生产 sem/hyb 裁决模型接线(translation worker create_chat_model 同款先例):
    模型选择经 _resolve_model_name;LangChain 模型 ainvoke 异步调用——claimer/routers
    直推均跑在事件循环上,禁同步 invoke 堵环。无可用模型仍抛 ModelNotConfigured,
    由逐规则隔离降级 need_human,绝不静默假交付。返回值经 _wrap_model_fn 包装,
    content 归一已就位。"""
    name = _resolve_model_name()
    if not name:

        def _fn(messages):
            raise ModelNotConfigured("config.yaml 无可用模型(EAI_BID_REVIEW_MODEL/首项均缺;sem/hyb 规则逐规则降级 need_human)")

        return _fn
    from deerflow.models.factory import create_chat_model

    model = create_chat_model(name)
    logger.info("bid_review sem/hyb using model %s", name)

    async def _fn(messages):
        return await model.ainvoke(messages)

    return _fn


def _parse_json_object(text: str) -> dict:
    """模型输出 → JSON dict(容 ```json 围栏与前后杂文:取首 { 至末 } 切片);
    解析失败或非 dict 抛 ValueError(调用方重试)。"""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"模型输出不含 JSON 对象: {text[:120]!r}")
    payload = json.loads(s[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError(f"模型输出 JSON 非对象: {type(payload).__name__}")
    return payload


# ── sem/hyb 材料装配(v1 纯文本直存契约)──────────────────────────────


def _collect_materials(docs: list[dict]) -> str:
    """规则卡材料注入(§4.5):各文档 doc_id 头 + 正文拼接。"""
    return "\n\n".join(f"[{d['doc_id']}]\n{d['text']}" for d in docs)


def _collect_docs_text(docs: list[dict]) -> dict:
    """证据对齐取材(verify.align_evidence 契约 {doc_id: {page: text}}):v1 文档无分页
    (routers 上传时解码纯文本直存),整篇挂 page 1;页容差 ±1 覆盖 page≤2 锚点,更远
    页码证据对不上 → 七道第2道降级 need_human(§4.6 表),不静默采信。"""
    return {d["doc_id"]: {1: d["text"]} for d in docs}


# ── 汇总分级(Task 14;A12 T14 约束①,worker 与 routers 共用)────────────


def _issue_get(issue, name):
    return issue.get(name) if isinstance(issue, dict) else getattr(issue, name, None)


def summarize_issues(issues) -> dict:
    """汇总分级(A12 T14 集成约束①):正式违规清单/致命计数不含 need_human 条目——
    fatal/major/minor/info 仅计 need_human=False 的正式违规,need_human 条目单列待人工
    计数(工作台 GateMetricsRow 待人工格口径),**不是删除**(条目仍全量落库、issues
    API 仍全量返回)。排序 fatal→major→minor→info(key 序即序)。worker 落
    progress.summary 与 issues 列表 API summary 共用本实现,两侧口径一致;接受 ORM 行
    与引擎 dict 双形态,未知严重度按 info 兜底。"""
    summary = {s: 0 for s in SEVERITY_ORDER}
    summary["need_human"] = 0
    for issue in issues or []:
        if bool(_issue_get(issue, "need_human")):
            summary["need_human"] += 1
        else:
            sev = str(_issue_get(issue, "severity") or "")
            summary[sev if sev in summary else "info"] += 1
    return summary


def _done_progress(durations: dict, summary: dict) -> dict:
    """done 帧 progress:stage/pct 沿用既有契约(前端 TasksView 读 pct),增 durations
    (各阶段耗时,秒,3 位小数)与 summary(汇总分级)。"""
    return {
        "stage": "done",
        "pct": 100,
        "msg": "审查完成",
        "durations": {k: round(v, 3) for k, v in durations.items()},
        "summary": summary,
    }


def _issue_confidence(issue) -> float:
    """confidence 安全取值:引擎条目可能带 None(A12 降级候选继承 det issue 无此键),
    float(None) 会 TypeError;非数值一律回 1.0。"""
    conf = _issue_get(issue, "confidence")
    return float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else 1.0


# ── 文档装载与提取装配 ────────────────────────────────────────────────


def _load_docs(task: ReviewTask) -> list[dict]:
    """ingest(parsing)阶段文档装载。EAI-CUSTOM(2026-10-30 解析层,spec §2):清单条目
    status=parsed → 从任务材料目录 segments 拼回全文(全文不上 wire,内存短暂聚合);
    旧任务(engine_meta.docs 内嵌 text 的 2026-10-30 前格式)走 legacy 分支原样读取,
    存量任务不受解析层改造影响。"""
    raw = (task.engine_meta or {}).get("docs")
    if not isinstance(raw, list):
        return []
    if any(isinstance(item, dict) and item.get("status") == "parsed" for item in raw):
        from app.extensions.bid_review import parse

        return parse.docs_from_entries(task.owner_id, task.id, [i for i in raw if isinstance(i, dict)])
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            out.append({"doc_id": str(item.get("doc_id") or "doc"), "role": str(item.get("role") or "unknown"), "text": item["text"]})
    return out


def _default_extract_fn() -> ExtractFn:
    """生产 LLM 基准提取接线(translation worker create_chat_model 同款先例):
    shard_docs 贪心装箱(≤SHARD_CHARS/prompt,几百页大文档不进单 prompt——spec D5)
    → 逐分片 build_extract_prompt → 同步 invoke(advance_task 以 asyncio.to_thread
    卸载本函数,禁在事件循环直跑)→ _parse_json_object 解析,坏输出重试 1 次,仍失败抛
    RuntimeError → _infra_fail 失败链(≤3 次重投,终态 failed 落因),绝不静默假交付。
    分片 merge 首个非 null 采纳,不回填(conflict 不覆盖非 null——spec D7);provenance
    同法合并。单分片仍失败重试整片;无可用模型抛 ExtractNotConfigured。"""
    name = _resolve_model_name()
    if not name:

        def _fn(docs: list[dict], field_paths: list[str]) -> dict:
            raise ExtractNotConfigured("config.yaml 无可用模型(EAI_BID_REVIEW_MODEL/首项均缺;基准提取未执行)")

        return _fn
    from app.extensions.bid_review.engine.extract import build_extract_prompt, shard_docs
    from deerflow.models.factory import create_chat_model

    model = create_chat_model(name)
    logger.info("bid_review baseline extraction using model %s", name)

    def _invoke_shard(prompt: str) -> dict:
        messages = [{"role": "user", "content": prompt}]
        last_err: Exception | None = None
        for attempt in (1, 2):
            response = model.invoke(messages)
            raw = _content_to_str(getattr(response, "content", ""))
            try:
                return _parse_json_object(raw)
            except ValueError as exc:
                last_err = exc
                logger.warning("bid_review extract parse retry attempt=%d err=%s", attempt, exc)
        raise RuntimeError(f"基准提取两试未获有效 JSON({last_err})") from last_err

    def _fn(docs: list[dict], field_paths: list[str]) -> dict:
        merged: dict[str, Any] = {}
        merged_prov: dict[str, dict] = {}
        merged_cand: dict[str, list] = {}
        merged_conf: dict[str, float] = {}
        for shard in shard_docs(docs) or [[]]:  # 空 docs 也跑一片(旧语义:显式问一遍模型,输出全 null)
            payload = _invoke_shard(build_extract_prompt(shard, field_paths))
            f_raw = payload.get("fields") if isinstance(payload.get("fields"), dict) else payload
            if isinstance(f_raw, dict):
                for k, v in f_raw.items():
                    if k in field_paths and merged.get(k) is None and v is not None:
                        merged[k] = v
            prov = payload.get("provenance") if isinstance(payload, dict) else None
            if isinstance(prov, dict):
                for k, v in prov.items():
                    if k in field_paths and k not in merged_prov and isinstance(v, dict):
                        merged_prov[k] = v
            cand = payload.get("candidates") if isinstance(payload, dict) else None
            if isinstance(cand, dict):  # 二期 spec §1.1:候选按路径 append,上限 8 由归一层兜底
                for k, entries in cand.items():
                    if k in field_paths and isinstance(entries, list):
                        merged_cand.setdefault(k, []).extend(entries)
            conf = payload.get("confidence") if isinstance(payload, dict) else None
            if isinstance(conf, dict):
                for k, v in conf.items():
                    if k in field_paths:
                        merged_conf[k] = v  # 后写覆盖(跨分片同一字段以后见为准)
        return {"fields": merged, "provenance": merged_prov, "candidates": merged_cand, "confidence": merged_conf}

    return _fn


# ── 状态机推进 ────────────────────────────────────────────────────────


async def _guarded_transition(db: AsyncSession, task_id: str, allowed_from: set[str], target: str) -> bool:
    """守卫式流转(translation._set_state 同构):仅当前状态 ∈ allowed_from 时置 target;
    rowcount=0 = 状态已被并发方移动。"""
    result = await db.execute(update(ReviewTask).where(ReviewTask.id == task_id, ReviewTask.status.in_(allowed_from)).values(status=target))
    await db.commit()
    return (result.rowcount or 0) > 0


async def _get_task_any(db: AsyncSession, task_id: str) -> ReviewTask | None:
    """claimer/失败链装载用(领任务时 owner 未知,先按 id 查;后续管线仍走 owner 过滤 crud)。"""
    result = await db.execute(select(ReviewTask).where(ReviewTask.id == task_id))
    return result.scalar_one_or_none()


async def _write_baselines(db: AsyncSession, task_id: str, docs: list[dict], fields: dict, materials_hash: str, provenance: dict | None = None, candidates: dict | None = None, fields_conf: dict | None = None) -> None:
    """基线落库(kind 按 docs role 拆,计划口径);每行携带全量 fields 快照 + 本行 doc_id
    (确认门 UI 逐份核对同一快照)。EAI-CUSTOM(2026-10-30 抽取 v2):payload 增
    provenance(逐字段出处 {doc_id,page,quote},字段抽取层产物;det 求值不消费)。
    EAI-CUSTOM(2026-10-30 二期 spec §1.1/§二):payload 增 candidates(多候选快照,
    冲突判定原料)+ fields_conf({conf,verified},置信投影)。
    写前清旧行——boot recovery 断点续跑(extracting 入口)重放基线时幂等,不产生重复行。"""
    await db.execute(delete(BaselinePackage).where(BaselinePackage.task_id == task_id))
    await db.commit()
    for doc in docs:
        db.add(
            BaselinePackage(
                task_id=task_id,
                kind=str(doc.get("role") or "unknown")[:10],  # String(10) 列宽保护
                payload={
                    "doc_id": doc.get("doc_id"),
                    "fields": fields,
                    "materials_hash": materials_hash,
                    "provenance": provenance or {},
                    "candidates": candidates or {},
                    "fields_conf": fields_conf or {},
                },
            )
        )
    await db.commit()


async def _run_review_stage(db: AsyncSession, task: ReviewTask, fields: dict, owner_id: str, model_fn=None, provenance: dict | None = None) -> int:
    """审查阶段(Task 14):按 rule.type 分派——deterministic→run_det_rule(既有 det
    通路;attach_evidence 回填 provenance 证据,EAI-CUSTOM 2026-10-30)/
    semantic|hybrid→run_sem_rule(model_fn 经 _wrap_model_fn 注入,content 归一
    str,A12 T14 约束②;hyb det 粗筛/候选确认/unclear 存活语义由 llm_runner 承担,worker
    只接线)。逐规则隔离(T9 先例 9cda4828b 扩展到 sem/hyb):单规则异常——含模型不可用/
    接线失败(ModelNotConfigured)——降级 need_human 条目,兄弟规则照常,禁整任务崩;
    crud.add_issue 的 DB 异常不在本包裹内,基础设施失败仍走既有失败链。
    None 值字段先剥离——det 求值器不容 None(比较算子会 TypeError),剥离后两通路统一走
    need_human 约定(on_missing_input=need_human);sem 侧同口径(None 字段=缺字段)。"""
    pack = load_rulepack(RULEPACK_PATH)
    det_fields = {k: v for k, v in fields.items() if v is not None}
    rules = [r for r in pack.rules if r.enabled]
    total = max(len(rules), 1)
    written = 0
    model_fn = _wrap_model_fn(model_fn or _default_model_fn())
    docs = _load_docs(task)
    materials = _collect_materials(docs)
    docs_text = _collect_docs_text(docs)
    for i, rule in enumerate(rules, start=1):
        await crud.set_status(db, task, "running", progress={"stage": "review", "pct": int(i * 100 / total), "msg": f"{rule.id}({i}/{total})"})
        try:
            if rule.type == "deterministic":
                issues = attach_evidence(run_det_rule(rule, det_fields), rule, provenance)
            else:  # semantic|hybrid
                issues = await run_sem_rule(rule, det_fields, materials, model_fn, docs_text)
        except Exception as exc:  # noqa: BLE001
            # 逐规则异常隔离(fix-round 评审项,Task 14 扩展到 sem/hyb):run_det_rule 只把
            # KeyError 转 need_human;求值意外(str/float 比较 TypeError)与模型侧故障
            # (ModelNotConfigured/端点异常)在此统一降级 need_human,不把整条审查任务经
            # _infra_fail 重试 3 次打 failed。
            logger.warning("bid_review task %s rule %s crashed, downgraded to need_human: %r", task.id, rule.id, exc)
            issues = [_need_human(rule, f"规则执行异常 {exc!r}(逐规则隔离降级 need_human)")]
        for issue in issues:
            row = await crud.add_issue(
                db,
                task_id=task.id,
                owner_id=owner_id,
                rule_id=str(_issue_get(issue, "rule_id") or "?"),
                layer=str(_issue_get(issue, "layer") or ""),
                severity=str(_issue_get(issue, "severity") or ""),
                verdict=str(_issue_get(issue, "verdict") or ""),
                message=str(_issue_get(issue, "message") or ""),
                fix=str(_issue_get(issue, "fix") or ""),
                evidence=list(_issue_get(issue, "evidence") or []),
                dedup_key=str(_issue_get(issue, "dedup_key") or ""),
                clause_id=_issue_get(issue, "clause_id"),
                need_human=bool(_issue_get(issue, "need_human")),
                confidence=_issue_confidence(issue),
            )
            if row is not None:
                written += 1
    return written


async def advance_task(
    db: AsyncSession,
    task_id: str,
    owner_id: str,
    docs: list[dict],
    extract_fn: ExtractFn,
    wait_confirm: bool,
    *,
    entry: str = "created",
    model_fn=None,
) -> ReviewTask:
    """状态机单步推进:parsing→extracting→基线落库→wait_confirm ? awaiting_confirm :
    running→review(det+sem/hyb)→done。

    entry="created"(默认,routers 直推)走 created→parsing 守卫置换,失败=已被
    claimer 并发领走,原样返回不双跑;entry="parsing"(claimer _claim_next 领取后的
    领取标记态)与 entry="extracting"(boot recovery 断点续跑)为已持有入口,跳过守卫
    直接进管线。model_fn 为 sem/hyb 规则模型 callable(缺省 _default_model_fn 生产缺口,
    经 _wrap_model_fn 包装归一 content);done 帧 progress 记录 durations(各阶段耗时)与
    summary(汇总分级,A12 T14 约束①)。异常向上抛,由调用方(routers 直推包装 /
    claimer)走 _infra_fail 失败链。
    """
    task = await crud.get_task(db, task_id, owner_id)
    if task is None:
        raise ValueError(f"bid_review task {task_id} not found for owner {owner_id}")
    if entry == "created" and not await _guarded_transition(db, task_id, {"created"}, "parsing"):
        return await crud.get_task(db, task_id, owner_id)  # 并发方已领走,本侧退出
    durations: dict[str, float] = {}
    await db.refresh(task)
    t0 = time.perf_counter()
    await crud.set_status(db, task, "parsing", progress={"stage": "parsing", "pct": 10, "msg": f"载入 {len(docs)} 份文档"})
    # EAI-CUSTOM(2026-10-30 解析层,spec §2):raw 清单条目 → 解析(docx/pdf/text +
    # OCR 图片插回)+ segments/assets 落盘 + 清单回写。OCR 引擎随系统设置
    # (parse.build_ocr_fn);单文档失败=抛出走 _infra_fail 失败链(≤3 重投),
    # 单图 OCR 失败已在 parse 内降级空文本(失败隔离)。旧任务(无 raw 条目)零跳过。
    raw_entries = [e for e in ((task.engine_meta or {}).get("docs") or []) if isinstance(e, dict) and e.get("status") == "raw"]
    if raw_entries:
        from app.extensions.bid_review import parse

        ocr_fn = await parse.build_ocr_fn(db)
        parsed: list[dict] = []
        for e in raw_entries:
            parsed.append(await parse.parse_raw(owner_id, task.id, e, ocr_fn))
        meta = dict(task.engine_meta or {})
        by_slug = {str(p["slug"]): p for p in parsed}
        meta["docs"] = [by_slug.get(str(e.get("slug")), e) for e in meta.get("docs") or []]
        task.engine_meta = meta  # 重新赋值以标记 JSON 列 dirty
        await db.commit()
        await db.refresh(task)
        docs = _load_docs(task)  # 解析产物重载(parsing 后续阶段消费全文内存形态)
    durations["parsing"] = time.perf_counter() - t0
    t1 = time.perf_counter()
    await crud.set_status(db, task, "extracting", progress={"stage": "extracting", "pct": 20, "msg": "基准字段提取中"})
    # 生产 extract_fn 是同步 LLM 调用,而 advance_task 跑在事件循环上(claimer/routers 直推)
    # ——to_thread 卸载防堵环;fake 同步 fn 在线程内语义不变(测试不受影响)。
    payload = await asyncio.to_thread(build_baseline, docs, extract_fn)
    fields = payload["fields"]
    meta = dict(task.engine_meta or {})
    meta["materials_hash"] = payload["materials_hash"]
    task.engine_meta = meta  # 重新赋值以标记 JSON 列 dirty
    await _write_baselines(db, task_id, docs, fields, payload["materials_hash"], payload.get("provenance"), payload.get("candidates"), payload.get("fields_conf"))
    # B1 抽取回填(裁定12:项目/标段/编号从投标文件抽,非向导手填):基线落库后同处
    # 写 task 三列;仅收标量(str/int/float),dict/list 等结构化值不回填(伪零纪律:
    # 抽不到保持 null,前端显 —)。
    def _scalar(v: object) -> str | None:
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
        return None

    task.project_name = _scalar(fields.get("tender.project_identity.name"))
    task.lot_name = _scalar(fields.get("tender.project_identity.lot_section"))
    task.tender_no = _scalar(fields.get("tender.project_identity.code"))
    await db.commit()
    await db.refresh(task)
    durations["extracting"] = time.perf_counter() - t1
    if wait_confirm:
        return await crud.set_status(db, task, "awaiting_confirm", progress={"stage": "confirm_gate", "pct": 40, "msg": "基线已生成,等待人工确认(确认门仅工作台 UI)"})
    t2 = time.perf_counter()
    await crud.set_status(db, task, "running", progress={"stage": "review", "pct": 40, "msg": "规则审查执行中(det+sem/hyb)"})
    await _run_review_stage(db, task, fields, owner_id, model_fn, payload.get("provenance"))
    durations["review"] = time.perf_counter() - t2
    summary = summarize_issues(await crud.list_issues(db, task_id=task_id, owner_id=owner_id))
    return await crud.set_status(db, task, "done", progress=_done_progress(durations, summary))


async def resume_confirmed(db: AsyncSession, task_id: str, owner_id: str, model_fn=None) -> ReviewTask:
    """确认门续跑(routers confirm 端点调用):awaiting_confirm→running→review(det+
    sem/hyb)→done;fields 取基线行内快照(首行,advance_task 各行同快照);model_fn
    语义同 advance_task;done 帧同记录 durations(本调用只含 review 段)与 summary。"""
    task = await crud.get_task(db, task_id, owner_id)
    if task is None:
        raise ValueError(f"bid_review task {task_id} not found for owner {owner_id}")
    fields: dict = {}
    provenance: dict = {}
    for b in await crud.list_baselines(db, task_id=task_id, owner_id=owner_id):
        payload = b.payload if isinstance(b.payload, dict) else {}
        if isinstance(payload.get("fields"), dict):
            fields = payload["fields"]
            prov = payload.get("provenance")
            provenance = prov if isinstance(prov, dict) else {}
            break
    # 二期 spec §1.4:确认门期间的人工裁定合并进快照——裁定就是改基准值,审查引擎无感知
    fields = apply_adjudications(fields, (task.engine_meta or {}).get("adjudications"))
    durations: dict[str, float] = {}
    t2 = time.perf_counter()
    await crud.set_status(db, task, "running", progress={"stage": "review", "pct": 40, "msg": "人工确认完成,规则审查执行中(det+sem/hyb)"})
    await _run_review_stage(db, task, fields, owner_id, model_fn, provenance)
    durations["review"] = time.perf_counter() - t2
    summary = summarize_issues(await crud.list_issues(db, task_id=task_id, owner_id=owner_id))
    return await crud.set_status(db, task, "done", progress=_done_progress(durations, summary))


# ── 失败链 / boot recovery(translation worker 同构)──────────────────


async def _infra_fail(task_id: str, exc: Exception, phase: str, factory=None) -> str:
    """基础设施失败链(R7 同构;计划口径:指数退避 ≤3 → failed):attempts 计数落
    engine_meta;未超限回 created 重投(claimer 按 attempts 指数退避,间隔即天然退避),
    超限 → failed 终态 + error 落库;done/failed/awaiting_confirm 终态/人工门不复活。"""
    factory = factory or get_session_factory()
    async with factory() as db:
        task = await _get_task_any(db, task_id)
        if task is None:
            return "missing"
        if task.status in {"failed", "done", "awaiting_confirm"}:
            return task.status
        meta = dict(task.engine_meta or {})
        attempts = int(meta.get("infra_attempts", 0)) + 1
        meta["infra_attempts"] = attempts
        meta["last_infra_error"] = f"{phase}: {exc!r}"[:500]
        task.engine_meta = meta  # 重新赋值以标记 JSON 列 dirty
        if attempts >= MAX_INFRA_RETRIES:
            task.status = "failed"
            task.error = f"{phase}: {exc!r}"[:2000]
            logger.error("bid_review task %s infra failure terminal (%s): %r", task_id, phase, exc)
        else:
            task.status = "created"
            logger.warning("bid_review task %s infra failure attempt %d/%d (%s): %r", task_id, attempts, MAX_INFRA_RETRIES, phase, exc)
        await db.commit()
        return task.status


async def _read_attempts(task_id: str, factory=None) -> int:
    factory = factory or get_session_factory()
    async with factory() as db:
        task = await _get_task_any(db, task_id)
        return int((task.engine_meta or {}).get("infra_attempts") or 0) if task is not None else 0


async def boot_recovery(factory=None) -> int:
    """启动时把遗留 running/parsing 任务重置为 extracting(计划口径 running→extracting;
    fix-round 补 parsing——它是 claim 领取标记,进程死亡窗口会遗留,一并断点续跑):
    claimer 以 extracting 入口断点续跑(重放基线+det,基线写前清旧行保证幂等)。"""
    factory = factory or get_session_factory()
    async with factory() as db:
        result = await db.execute(update(ReviewTask).where(ReviewTask.status.in_(["running", "parsing"])).values(status="extracting"))
        await db.commit()
        n = result.rowcount or 0
        if n:
            logger.info("bid_review boot recovery: %d in-flight task(s) reset to extracting", n)
        return n


# ── claimer 循环(D18 gateway 内嵌,SLOTS=1)────────────────────────────


async def _claim_next(factory=None) -> tuple[str, str] | None:
    """领取一个待审任务(FOR UPDATE SKIP LOCKED 防多进程争抢,translation 先例;
    锁子句按 dialect 注入,sqlite 测试方言无该语法):
    created→parsing(领取标记,完整管线入口)或 extracting(boot recovery 断点续跑入口)。
    返回 (task_id, entry),entry=领取后实际状态(parsing|extracting),与 advance_task
    的已持有入口对齐——claimer 不再回传 "created",否则守卫二次置换零命中早退,
    任务死锁 parsing(fix-round 评审缺陷)。created 条件置换校验 rowcount,零命中=已被
    routers 直推并发领走,放弃本次领取防双跑;无任务返回 None。"""
    factory = factory or get_session_factory()
    async with factory() as db:
        lock = " FOR UPDATE SKIP LOCKED" if db.bind.dialect.name == "postgresql" else ""
        row = (await db.execute(text(f"SELECT id, status FROM bid_review_tasks WHERE status IN ('created','extracting') ORDER BY created_at LIMIT 1{lock}"))).first()
        if row is None:
            return None
        task_id, status = str(row[0]), str(row[1])
        if status == "created":
            marked = await db.execute(text("UPDATE bid_review_tasks SET status='parsing' WHERE id = :id AND status = 'created'"), {"id": task_id})
            await db.commit()
            if not (marked.rowcount or 0):
                return None  # 状态已被并发方移动(直推已领),本侧退出防双跑
            return task_id, "parsing"
        await db.commit()
        return task_id, "extracting"


async def _run_claimed(task_id: str, entry: str) -> str:
    """claimer 侧执行:独立短会话;docs 由 _load_docs 装载;entry 为 _claim_next 给出的
    已持有入口(parsing=新建领取,extracting=断点续跑);deep 模式停确认门,quick 直跑
    到 done。"""
    factory = get_session_factory()
    async with factory() as db:
        task = await _get_task_any(db, task_id)
        if task is None:
            return "missing"
        final = await advance_task(
            db,
            task_id,
            owner_id=task.owner_id,
            docs=_load_docs(task),
            extract_fn=_default_extract_fn(),
            model_fn=_default_model_fn(),
            wait_confirm=(task.mode == "deep"),
            entry=entry,
        )
        return final.status


async def bid_review_claimer_loop(stop: asyncio.Event | None = None) -> None:
    """常驻 claimer(SLOTS=1):领取 created/extracting → advance 管线;空闲 poll;
    基础设施失败按 attempts 指数退避(封顶 BACKOFF_CAP_SECONDS)后重投再领。"""
    stop = stop or asyncio.Event()
    logger.info("bid_review claimer loop started (poll=%.1fs, slots=%d)", POLL_SECONDS, SLOTS)
    backoff = 0.0
    while not stop.is_set():
        if backoff > 0:
            try:
                await asyncio.wait_for(stop.wait(), timeout=backoff)
                return
            except TimeoutError:
                backoff = 0.0
        claimed = None
        try:
            claimed = await _claim_next()
        except Exception:
            logger.exception("bid_review claimer: claim failed")
        if claimed is None:
            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
            except TimeoutError:
                pass
            continue
        task_id, entry = claimed
        try:
            final = await _run_claimed(task_id, entry)
            logger.info("bid_review claimer: task %s -> %s", task_id, final)
        except Exception as exc:
            logger.exception("bid_review claimer: task %s crashed", task_id)
            state = await _infra_fail(task_id, exc, phase="pipeline")
            if state == "created":
                backoff = min(POLL_SECONDS * (2 ** await _read_attempts(task_id)), BACKOFF_CAP_SECONDS)


async def start_bid_review_worker() -> asyncio.Task:
    """lifespan 入口:boot recovery(running→extracting)+ 单槽 claimer 循环(D18)。"""
    await boot_recovery()
    stop = asyncio.Event()

    async def _runner() -> None:
        await bid_review_claimer_loop(stop)

    runner = asyncio.create_task(_runner())
    runner.stop_event = stop  # type: ignore[attr-defined]
    return runner


async def stop_bid_review_worker(runner: asyncio.Task) -> None:
    """优雅停机(供后续 lifespan 收尾接线;uvicorn 兜底 cancel 亦可)。"""
    stop = getattr(runner, "stop_event", None)
    if stop is not None:
        stop.set()
    try:
        await asyncio.wait_for(asyncio.shield(runner), timeout=10)
    except (TimeoutError, asyncio.CancelledError):
        runner.cancel()
