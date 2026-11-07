"""共享规则分派核(金标准评测集 spec §4,EAI-CUSTOM 2026-11-03):worker._run_review_stage
与 golden 评测器共用同一段分派逻辑——det/sem 分派、None 字段剥离、逐规则异常隔离降级
need_human。金标准尺子量的必须是生产同一段代码,评测器禁复制分派循环(复制=两把尺子,
必然漂移说谎)。bug 编号:无;升级注意:改分派语义须同步跑 tests/test_bid_review_eval_core.py
与金标准全库。本模块无 DB、无状态:worker 侧进度上报(crud.set_status)与条目落库
(crud.add_issue)由调用方以 on_progress 回调 + 返回值自行承担。
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from types import SimpleNamespace

from app.extensions.bid_review.engine.llm_runner import run_sem_rule
from app.extensions.bid_review.engine.rule_runner import Rule, RulePack, _need_human, attach_evidence, run_det_rule

logger = logging.getLogger(__name__)


# ── 模型接线包装(自 worker._wrap_model_fn/_content_to_str 原样迁入,金标准重构;
#    worker 侧留 _wrap_model_fn 兼容别名;engine._call_model 不改)────────────────


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


def wrap_model_fn(model_fn):
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


ProgressCB = Callable[[int, int, Rule], Awaitable[None]]


def _suppress_l3012_by_l2021(issues: list[dict]) -> list[dict]:
    """W9 抑制联动(规格主责矩阵;P1-β批二 A-β2-⑦):L2-021 已报的引用缺失,同实体 L3-012
    violation 折叠(suppressed_by 内标后移除,存在性归 L2 主责);L2-021 未覆盖的行照常出
    L3-012。匹配只取结构化 entity_keys token(≥2 字符),message 全文禁入匹配面(样板词
    自由重叠会误折叠全部 L3-012)。核心不变式:只折叠 violation,need_human 不动;
    L2-021 无 violation 时零折叠。"""
    l2021 = [i for i in issues if i.get("rule_id") == "L2-021" and i.get("verdict") == "violation"]
    if not l2021:
        return issues

    def _names(i: dict) -> set[str]:
        toks: set[str] = set()
        for k in i.get("entity_keys") or []:
            for part in str(k).replace(":", "|").split("|"):
                p = part.strip().lower()
                if len(p) >= 2:
                    toks.add(p)
        return toks

    keys: set[str] = set()
    for i in l2021:
        keys |= _names(i)
    out, suppressed = [], 0
    for i in issues:
        if i.get("rule_id") == "L3-012" and i.get("verdict") == "violation" and (_names(i) & keys):
            suppressed += 1
            continue  # 折叠移除;suppressed_by 内标在审计日志面记(本批不落 issue 流)
        out.append(i)
    if suppressed:
        logger.info("W9 抑制:L2-021 主责下折叠 L3-012 violation %d 条", suppressed)
    return out


def _fold_issues_by_primary(issues: list[dict], primary_rule_id: str, folded_rule_ids: tuple[str, ...]) -> list[dict]:
    """主责折叠泛化(A-续-⑤,P1-β批二续):primary 存在 verdict=violation(definite)时,
    折叠 folded 规则的 violation(need_human 不折叠,suppressed_by 记账同 W9)。rule 级折叠
    无 entity 条件——W9 的 entity 交集是 L2-021/L3-012 特化,entity 级细化挂账。
    与 W9 记账差异(plan Task 2 Step 2 规格):W9 折叠面只在审计日志记(suppressed_by 内标
    本批不落 issue 流);本 helper 额外在 primary 条目上落 ``suppressed_by``(被折叠条目
    dedup_key 列表,审计可反查谁吞了谁)。核心不变式同 W9:只折叠 violation,need_human
    不动;primary 不在/无 definite violation 时零折叠快路径原样返回(W9 本体一行不动)。"""
    primary_idx = [n for n, i in enumerate(issues) if i.get("rule_id") == primary_rule_id and i.get("verdict") == "violation" and not i.get("need_human")]
    if not primary_idx:
        return issues  # 零折叠快路径(primary 不在/仅 need_human 不武装),原样返回
    folded = set(folded_rule_ids)
    kept, folded_n = [], 0
    for it in issues:
        if it.get("rule_id") in folded and it.get("verdict") == "violation" and not it.get("need_human"):
            folded_n += 1
            key = it.get("dedup_key") or str(it.get("rule_id"))
            for n in primary_idx:
                issues[n].setdefault("suppressed_by", []).append(key)
            continue
        kept.append(it)
    if folded_n:
        logger.info("fold_by_primary %s -> %s: %d", primary_rule_id, list(folded_rule_ids), folded_n)
    return kept


async def evaluate_fields(
    pack: RulePack,
    fields: dict,
    *,
    model_fn,
    materials: str = "",
    docs_text: str = "",
    provenance: dict | None = None,
    on_progress: ProgressCB | None = None,
) -> list[dict]:
    """字段 → issues(无 DB、无状态)。model_fn 为已包装形态(wrap_model_fn 产物)。
    与 worker._run_review_stage 分派语义逐字一致(None 剥离/类型分派/逐规则隔离):
    None 值字段先剥离——det 求值器不容 None(比较算子会 TypeError),剥离后两通路统一走
    need_human 约定(on_missing_input=need_human);sem 侧同口径(None 字段=缺字段)。
    逐规则隔离:单规则异常——含模型不可用/接线失败(ModelNotConfigured)——降级
    need_human 条目,兄弟规则照常,禁整批崩。"""
    det_fields = {k: v for k, v in fields.items() if v is not None}
    rules = [r for r in pack.rules if r.enabled]
    total = max(len(rules), 1)
    out: list[dict] = []
    for i, rule in enumerate(rules, start=1):
        if on_progress is not None:
            await on_progress(i, total, rule)
        try:
            if rule.type == "deterministic":
                issues = attach_evidence(run_det_rule(rule, det_fields), rule, provenance)
            else:  # semantic|hybrid
                issues = await run_sem_rule(rule, det_fields, materials, model_fn, docs_text)
        except Exception as exc:  # noqa: BLE001
            # 逐规则异常隔离(worker 同款语义):run_det_rule 只把 KeyError 转 need_human;
            # 求值意外与模型侧故障在此统一降级 need_human,不外溢单规则异常。
            logger.warning("bid_review rule %s crashed, downgraded to need_human: %r", rule.id, exc)
            issues = [_need_human(rule, f"规则执行异常 {exc!r}(逐规则隔离降级 need_human)")]
        out.extend(issues)
    out = _suppress_l3012_by_l2021(out)  # W9 抑制联动(聚合循环后、return 前单插入,A-β2-⑦)
    # L2-051 主责折叠(A-续-⑤,P1-β批二续):草稿/内部标记残留面上,版本/币种一致性(L3-016/018)
    # violation 让位主责;L1-007→L2-030 折叠行 Task 3 加。
    out = _fold_issues_by_primary(out, "L2-051", ("L3-016", "L3-018"))
    return out
