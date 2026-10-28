"""bid_review worker(Task 9)——状态机推进 + claimer 循环 + gateway 生命周期入口。

状态机(设计文档 §4.3):created→parsing→extracting→awaiting_confirm→running→done|failed。
advance_task 为可注入 session/extract_fn 的单步推进函数(测试直调);routers 的
_enqueue_docs 直推走 created 守卫置换(防与 claimer 双跑),claimer 领取后以已持有
入口(parsing|extracting)直进同一管线。
claimer 照 translation worker 惯例:POLL_SECONDS env、SLOTS=1、boot recovery
(running|parsing→extracting)、基础设施异常指数退避 ≤3 → failed(_infra_fail,
终态不复活)。fix-round(2026-10-29 评审):领取入口以领取标记态返回(parsing),
杜绝旧实现守卫二次置换零命中导致 claimed 任务死锁 parsing 的缺陷。
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.bid_review import crud
from app.extensions.bid_review.engine.extract import ExtractFn, ExtractNotConfigured, build_baseline
from app.extensions.bid_review.engine.rule_runner import _need_human, load_rulepack, run_det_rule
from app.extensions.bid_review.models import BaselinePackage, ReviewTask
from app.extensions.database import get_session_factory

logger = logging.getLogger(__name__)

RULEPACK_PATH = Path(__file__).parent / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml"
POLL_SECONDS = float(os.environ.get("EAI_BID_REVIEW_POLL_SECONDS", "5"))
SLOTS = 1  # 单槽:审查为重 LLM 任务,先串行;提并发再扩(translation D16 先例)
MAX_INFRA_RETRIES = int(os.environ.get("EAI_BID_REVIEW_INFRA_RETRIES", "3"))
BACKOFF_CAP_SECONDS = 60.0


# ── 文档装载与提取装配 ────────────────────────────────────────────────


def _load_docs(task: ReviewTask) -> list[dict]:
    """ingest(parsing)阶段文档装载:docs 落在 task.engine_meta["docs"](routers 上传
    时解码写入,JSON 列)。缺口标注(计划 Task 9 Step 3 授权):bid_materials 仅有资质
    影像/样例台账域(MinIO),无文档文本解析入口可接,故 v1 采用上传时解码的纯文本直存;
    PDF/Word 结构化解析 v2 接入时仅需替换本函数取数源。"""
    raw = (task.engine_meta or {}).get("docs")
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            out.append({"doc_id": str(item.get("doc_id") or "doc"), "role": str(item.get("role") or "unknown"), "text": item["text"]})
    return out


def _default_extract_fn() -> ExtractFn:
    """生产提取函数装配点(显式缺口,translation worker `_default_index_fn` 同款先例):
    LLM 基准提取未接线(生产模型工厂装配属后续任务)→ 抛 ExtractNotConfigured 落
    failed,绝不静默假交付。接线时仅改本函数。"""

    def _fn(docs: list[dict], field_paths: list[str]) -> dict:
        raise ExtractNotConfigured("生产 LLM 基准提取未接线(worker._default_extract_fn 显式缺口;接线前 quick/deep 任务将 failed)")

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


async def _write_baselines(db: AsyncSession, task_id: str, docs: list[dict], fields: dict, materials_hash: str) -> None:
    """基线落库(kind 按 docs role 拆,计划口径);每行携带全量 fields 快照 + 本行 doc_id
    (确认门 UI 逐份核对同一快照)。写前清旧行——boot recovery 断点续跑(extracting 入口)
    重放基线时幂等,不产生重复行。"""
    await db.execute(delete(BaselinePackage).where(BaselinePackage.task_id == task_id))
    await db.commit()
    for doc in docs:
        db.add(
            BaselinePackage(
                task_id=task_id,
                kind=str(doc.get("role") or "unknown")[:10],  # String(10) 列宽保护
                payload={"doc_id": doc.get("doc_id"), "fields": fields, "materials_hash": materials_hash},
            )
        )
    await db.commit()


async def _run_det_stage(db: AsyncSession, task: ReviewTask, fields: dict, owner_id: str) -> int:
    """det 规则执行(sem/hyb 集成属 Task 14,此处只跑 type=deterministic):
    逐条 run_det_rule → crud.add_issue(dedup_key 由 rule_runner 产出);progress.pct 按 i/len。
    None 值字段先剥离——det 求值器不容 None(比较算子会 TypeError),剥离后 run_det_rule
    走既有 need_human 通路(on_missing_input=need_human 约定)。"""
    pack = load_rulepack(RULEPACK_PATH)
    det_fields = {k: v for k, v in fields.items() if v is not None}
    rules = [r for r in pack.rules if r.enabled and r.type == "deterministic"]
    total = max(len(rules), 1)
    written = 0
    for i, rule in enumerate(rules, start=1):
        await crud.set_status(db, task, "running", progress={"stage": "det", "pct": int(i * 100 / total), "msg": f"{rule.id}({i}/{total})"})
        try:
            issues = run_det_rule(rule, det_fields)
        except Exception as exc:  # noqa: BLE001
            # fix-round 评审项:逐规则异常隔离——run_det_rule 只把 KeyError 转 need_human,其余求值
            # 意外(如 str/float 比较 TypeError、求值器强转漏网)在此降级 need_human,不把整条审查
            # 任务经 _infra_fail 重试 3 次打 failed;crud.add_issue 的 DB 异常不在本包裹内,基础设施
            # 失败仍走既有失败链。
            logger.warning("bid_review task %s rule %s crashed, downgraded to need_human: %r", task.id, rule.id, exc)
            issues = [_need_human(rule, f"规则求值异常 {exc!r}(逐规则隔离降级 need_human)")]
        for issue in issues:
            row = await crud.add_issue(
                db,
                task_id=task.id,
                owner_id=owner_id,
                rule_id=str(issue.get("rule_id", "?")),
                layer=str(issue.get("layer", "")),
                severity=str(issue.get("severity", "")),
                verdict=str(issue.get("verdict", "")),
                message=str(issue.get("message", "")),
                fix=str(issue.get("fix") or ""),
                evidence=list(issue.get("evidence") or []),
                dedup_key=str(issue.get("dedup_key") or ""),
                need_human=bool(issue.get("need_human")),
                confidence=float(issue.get("confidence", 1.0)),
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
) -> ReviewTask:
    """状态机单步推进:parsing→extracting→基线落库→wait_confirm ? awaiting_confirm :
    running→det→done。

    entry="created"(默认,routers 直推)走 created→parsing 守卫置换,失败=已被
    claimer 并发领走,原样返回不双跑;entry="parsing"(claimer _claim_next 领取后的
    领取标记态)与 entry="extracting"(boot recovery 断点续跑)为已持有入口,跳过守卫
    直接进管线。异常向上抛,由调用方(routers 直推包装 / claimer)走 _infra_fail 失败链。
    """
    task = await crud.get_task(db, task_id, owner_id)
    if task is None:
        raise ValueError(f"bid_review task {task_id} not found for owner {owner_id}")
    if entry == "created" and not await _guarded_transition(db, task_id, {"created"}, "parsing"):
        return await crud.get_task(db, task_id, owner_id)  # 并发方已领走,本侧退出
    await db.refresh(task)
    await crud.set_status(db, task, "parsing", progress={"stage": "parsing", "pct": 10, "msg": f"载入 {len(docs)} 份文档"})
    await crud.set_status(db, task, "extracting", progress={"stage": "extracting", "pct": 20, "msg": "基准字段提取中"})
    payload = build_baseline(docs, extract_fn)
    fields = payload["fields"]
    meta = dict(task.engine_meta or {})
    meta["materials_hash"] = payload["materials_hash"]
    task.engine_meta = meta  # 重新赋值以标记 JSON 列 dirty
    await _write_baselines(db, task_id, docs, fields, payload["materials_hash"])
    if wait_confirm:
        return await crud.set_status(db, task, "awaiting_confirm", progress={"stage": "confirm_gate", "pct": 40, "msg": "基线已生成,等待人工确认(确认门仅工作台 UI)"})
    await crud.set_status(db, task, "running", progress={"stage": "det", "pct": 40, "msg": "确定性规则执行中"})
    await _run_det_stage(db, task, fields, owner_id)
    return await crud.set_status(db, task, "done", progress={"stage": "done", "pct": 100, "msg": "审查完成"})


async def resume_confirmed(db: AsyncSession, task_id: str, owner_id: str) -> ReviewTask:
    """确认门续跑(routers confirm 端点调用):awaiting_confirm→running→det→done;
    fields 取基线行内快照(首行,advance_task 各行同快照)。"""
    task = await crud.get_task(db, task_id, owner_id)
    if task is None:
        raise ValueError(f"bid_review task {task_id} not found for owner {owner_id}")
    fields: dict = {}
    for b in await crud.list_baselines(db, task_id=task_id, owner_id=owner_id):
        payload = b.payload if isinstance(b.payload, dict) else {}
        if isinstance(payload.get("fields"), dict):
            fields = payload["fields"]
            break
    await crud.set_status(db, task, "running", progress={"stage": "det", "pct": 40, "msg": "人工确认完成,确定性规则执行中"})
    await _run_det_stage(db, task, fields, owner_id)
    return await crud.set_status(db, task, "done", progress={"stage": "done", "pct": 100, "msg": "审查完成"})


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
