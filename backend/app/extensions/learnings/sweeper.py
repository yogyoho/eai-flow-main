"""learnings 扩展 — lazy catch-up 补扫引擎(run 结束后的机械错误捕获).

EAI-CUSTOM: 自进化循环 P1(设计 docs/designs/self-improving-loop-port.md D11/D12)。
有界三重保障: 按 thread 扫域 / 每次 <=20 个未扫 run(新->旧) / 仅近 30 天。
幂等唯一归 learning_sweep_receipts; 角色过滤结构性限定 role=="tool" 且
status=="error" 的 ToolMessage + run.error/llm.error 事件(原版"agent 自话
当错误"弱点不可能发生)。全程永不 raise。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import bindparam, select, text

from app.extensions.database import get_db_context
from app.extensions.learnings import service
from app.extensions.learnings.models import LearningSweepReceipt
from app.extensions.learnings.patterns import match_pattern_key, sanitize_evidence

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("success", "error", "timeout", "interrupted")
MAX_RUNS_PER_CATCHUP = 20
LOOKBACK_DAYS = 30
MAX_DETECTIONS_PER_RUN = 5

_store = None
_store_failed = False


async def get_store():
    """DbRunEventStore(懒初始化; memory 后端返回 None=dev 限制, 调用方降级)."""
    global _store, _store_failed
    if _store is not None:
        return _store
    if _store_failed:
        return None
    try:
        from deerflow.config import get_app_config
        from deerflow.persistence import get_engine, get_session_factory
        from deerflow.persistence.engine import init_engine_from_config  # __init__ 未再导出
        from deerflow.runtime.events.store.db import DbRunEventStore

        if get_engine() is None:
            await init_engine_from_config(get_app_config().database)
        session_factory = get_session_factory()
        if session_factory is None:  # backend=memory
            _store_failed = True
            return None
        _store = DbRunEventStore(session_factory)
        return _store
    except Exception:
        logger.exception("learnings sweeper: run-event store 初始化失败(降级为不补扫)")
        _store_failed = True
        return None


def extract_detections(messages: list[dict], events: list[dict], cap: int = MAX_DETECTIONS_PER_RUN) -> list[dict]:
    """纯函数: 从 run 消息/事件中提取待记录教训(角色过滤在此结构性完成)."""
    detections: list[dict] = []
    for m in messages or []:
        if m.get("role") != "tool" or m.get("status") != "error":
            continue
        body = m.get("content", "")
        if isinstance(body, list):
            body = " ".join(
                str(part.get("text", "") if isinstance(part, dict) else part) for part in body
            )
        body = str(body).strip()
        if not body:
            continue
        area, symptom = match_pattern_key(body)
        detections.append(
            {
                "kind": "error",
                "area": area,
                "symptom": symptom,
                "summary": body.splitlines()[0][:200] if body else "tool error",
                "evidence": sanitize_evidence(body),
            }
        )
        if len(detections) >= cap:
            return detections
    for e in events or []:
        if e.get("event_type") not in ("run.error", "llm.error"):
            continue
        body = str(e.get("error") or e.get("content") or e.get("event_type") or "")[:400]
        if not body:
            continue
        detections.append(
            {
                "kind": "error",
                "area": "runtime",
                "symptom": "failure",
                "summary": body.splitlines()[0][:200],
                "evidence": sanitize_evidence(body),
            }
        )
        if len(detections) >= cap:
            break
    return detections


def select_runs(run_rows: list[dict], swept_run_ids: set[str], cap: int = MAX_RUNS_PER_CATCHUP) -> list[dict]:
    """纯函数: 新->旧过滤已扫 + 截断(更老 run 永不回填, D11)."""
    out = []
    for row in sorted(run_rows, key=lambda r: str(r.get("created_at") or ""), reverse=True):
        if row.get("run_id") in swept_run_ids:
            continue
        out.append(row)
        if len(out) >= cap:
            break
    return out


async def _swept_run_ids(user_id: str, thread_id: str) -> set[str]:
    async with get_db_context() as db:
        rows = (
            await db.execute(
                text("SELECT run_id FROM learning_sweep_receipts WHERE user_id = :u AND thread_id = :t"),
                {"u": user_id, "t": thread_id},
            )
        ).all()
    return {r[0] for r in rows}


async def _terminal_runs(thread_id: str, excluded: set[str]) -> list[dict]:
    """core deerflow 库只读查询(app->deerflow 方向合法); engine 未初始化返回空."""
    from deerflow.persistence import get_engine

    engine = get_engine()
    if engine is None:
        return []
    since = datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)
    stmt = (
        text(
            "SELECT run_id, status, created_at FROM runs "
            "WHERE thread_id = :t AND status IN :sts AND created_at >= :since "
            "ORDER BY created_at DESC LIMIT :lim"
        )
        .bindparams(bindparam("sts", expanding=True))
    )
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                stmt,
                {"t": thread_id, "sts": list(TERMINAL_STATUSES), "since": since, "lim": MAX_RUNS_PER_CATCHUP * 3},
            )
        ).mappings().all()
    return [dict(r) for r in rows]


async def sweep_run(store, user_id: str, thread_id: str, run_id: str, created_at=None) -> dict:
    """扫单个 run: 提取 -> 折叠入账 -> 写 receipt(幂等). 可独立测试(fake store)."""
    async with get_db_context() as db:
        already = (
            await db.execute(
                select(LearningSweepReceipt.run_id).where(LearningSweepReceipt.run_id == run_id)
            )
        ).scalar_one_or_none()
    if already is not None:
        return {"run_id": run_id, "captures": 0, "skipped": "already-swept"}

    # cwd 身份显式传入(独立进程无 auth contextvar; AUTO 会 RuntimeError)
    messages = await store.list_messages_by_run(thread_id, run_id, limit=100, user_id=user_id)
    events = await store.list_events(thread_id, run_id, event_types=["run.error", "llm.error"], user_id=user_id)
    detections = extract_detections(messages, events)
    for d in detections:
        await service.mint_or_fold(
            user_id=user_id,
            kind=d["kind"],
            area=d["area"],
            symptom=d["symptom"],
            summary=d["summary"],
            details="",
            suggested_action="",
            source="sweep",
            source_thread_id=thread_id,
            source_run_id=run_id,
        )
    async with get_db_context() as db:
        db.add(
            LearningSweepReceipt(
                run_id=run_id,
                user_id=user_id,
                thread_id=thread_id,
                captures=len(detections),
            )
        )
        await db.commit()
    return {"run_id": run_id, "captures": len(detections)}


async def catchup_thread(user_id: str, thread_id: str) -> dict:
    """surface 前的有界补扫; 任何失败降级为 warning, 永不 raise."""
    try:
        store = await get_store()
        if store is None:
            return {"swept": 0, "captures": 0, "note": "run-events backend unavailable"}
        swept_ids = await _swept_run_ids(user_id, thread_id)
        run_rows = await _terminal_runs(thread_id, swept_ids)
        runs = select_runs(run_rows, swept_ids)
        swept = 0
        captured = 0
        for run in runs:
            result = await sweep_run(store, user_id, thread_id, run["run_id"], run.get("created_at"))
            swept += 1
            captured += result["captures"]
        if swept or captured:
            logger.info("learnings sweep: thread=%s swept=%d captured=%d", thread_id, swept, captured)
        return {"swept": swept, "captures": captured}
    except Exception:
        logger.warning("learnings sweep: thread=%s 补扫失败(降级跳过)", thread_id, exc_info=True)
        return {"swept": 0, "captures": 0, "note": "sweep-error"}
