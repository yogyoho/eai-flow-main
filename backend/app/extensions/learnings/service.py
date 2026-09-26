"""learnings 扩展服务层 — mint-or-fold / 资格计算 / 状态机(REST/MCP 共用).

EAI-CUSTOM: 自进化循环 P1(设计 docs/designs/self-improving-loop-port.md)。
约定:
- 函数自管会话(doc_graph service 风格), agent/REST 双入口零样板
- mint-or-fold: (user_id, pattern_key) 命中即折叠 recurrence+1 + last_seen +
  threads 合并; resolved 命中重开 pending; dismissed 不自动重开(尊重人工裁决)
- 资格判定确定性 SQL: pending + recurrence>=3 + 跨>=2 thread + 近 30 天
- 载荷构造必须显式全字段(prior learning: pydantic 默认值静默填充陷阱)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.extensions.database import get_db_context
from app.extensions.learnings.models import AgentLearning
from app.extensions.learnings.patterns import (
    AREAS,
    KINDS,
    canonical_pattern_key,
)

logger = logging.getLogger(__name__)

_READY = False

# 晋升门槛(原版量化规则, eng-review 冻结)
PROMOTION_MIN_RECURRENCE = 3
PROMOTION_MIN_THREADS = 2
PROMOTION_WINDOW_DAYS = 30

_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"resolved", "dismissed", "promoted_to_skill"},
    "resolved": {"pending"},
    "dismissed": {"pending"},
    "promoted_to_skill": set(),
}


async def ensure_ready() -> None:
    """幂等初始化: 引擎 + create_all(MCP 子进程启动时调用; gateway 不 import 本模块)."""
    global _READY
    if _READY:
        return
    from app.extensions.database import init_db

    await init_db()
    _READY = True


def _now() -> datetime:
    return datetime.now(UTC)


def _merge_threads(existing: str, new_thread_id: str) -> tuple[str, int]:
    threads = {t for t in (existing or "").split(",") if t}
    if new_thread_id:
        threads.add(new_thread_id[:16])
    return ",".join(sorted(threads))[:1000], len(threads)


async def mint_or_fold(
    *,
    user_id: str,
    kind: str,
    area: str,
    symptom: str,
    summary: str,
    details: str = "",
    suggested_action: str = "",
    source: str = "agent",
    source_thread_id: str = "",
    source_run_id: str = "",
) -> dict:
    """同 (user_id, pattern_key) 命中即折叠(无条件下 count+1, D12), 否则新建."""
    if kind not in KINDS:
        return {"success": False, "error": f"kind 必须是 {KINDS}"}
    if area not in AREAS:
        return {"success": False, "error": f"area 必须是 {AREAS}"}
    summary = (summary or "").strip()[:200]
    if not summary:
        return {"success": False, "error": "summary 必填(<=200 字符)"}
    pattern_key = canonical_pattern_key(area, symptom)
    now = _now()

    async with get_db_context() as db:
        existing = (
            await db.execute(
                select(AgentLearning).where(
                    AgentLearning.user_id == user_id,
                    AgentLearning.pattern_key == pattern_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.recurrence_count += 1
            existing.last_seen_at = now
            threads_csv, distinct = _merge_threads(existing.source_thread_ids, source_thread_id)
            existing.source_thread_ids = threads_csv
            existing.distinct_thread_count = distinct
            if existing.status == "resolved":
                existing.status = "pending"  # 教训再次发生 = 重新打开; dismissed 不动(尊重人工裁决)
            await db.commit()
            return {
                "success": True,
                "id": existing.id,
                "pattern_key": existing.pattern_key,
                "folded": True,
                "recurrence_count": existing.recurrence_count,
                "status": existing.status,
            }
        row = AgentLearning(
            id=str(uuid4()),
            user_id=user_id,
            kind=kind,
            area=area,
            symptom=pattern_key.split(".", 1)[1],
            pattern_key=pattern_key,
            summary=summary,
            details=(details or "")[:4000],
            suggested_action=(suggested_action or "")[:1000],
            status="pending",
            recurrence_count=1,
            first_seen_at=now,
            last_seen_at=now,
            distinct_thread_count=1 if source_thread_id else 0,
            source_thread_ids=(source_thread_id or "")[:16],
            source=source if source in ("agent", "sweep") else "agent",
            source_thread_id=(source_thread_id or None),
            source_run_id=(source_run_id or None),
        )
        db.add(row)
        await db.commit()
        return {
            "success": True,
            "id": row.id,
            "pattern_key": row.pattern_key,
            "folded": False,
            "recurrence_count": 1,
            "status": row.status,
        }


async def surface(user_id: str, limit: int = 5) -> dict:
    """pending 按 (recurrence↓, last_seen↓) + 资格标记 + 计数(资格 = D14 尾注数据源)."""
    cutoff = _now() - timedelta(days=PROMOTION_WINDOW_DAYS)
    async with get_db_context() as db:
        entries = (
            (
                await db.execute(
                    select(AgentLearning)
                    .where(AgentLearning.user_id == user_id, AgentLearning.status == "pending")
                    .order_by(AgentLearning.recurrence_count.desc(), AgentLearning.last_seen_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        pending_total = (
            await db.execute(
                select(func.count())
                .select_from(AgentLearning)
                .where(AgentLearning.user_id == user_id, AgentLearning.status == "pending")
            )
        ).scalar_one()
        promotion_ready = (
            await db.execute(
                select(func.count())
                .select_from(AgentLearning)
                .where(
                    AgentLearning.user_id == user_id,
                    AgentLearning.status == "pending",
                    AgentLearning.recurrence_count >= PROMOTION_MIN_RECURRENCE,
                    AgentLearning.distinct_thread_count >= PROMOTION_MIN_THREADS,
                    AgentLearning.last_seen_at >= cutoff,
                )
            )
        ).scalar_one()
    out = []
    for row in entries:
        item = row.to_dict()
        item["eligible_for_skill"] = (
            row.recurrence_count >= PROMOTION_MIN_RECURRENCE
            and row.distinct_thread_count >= PROMOTION_MIN_THREADS
            and row.last_seen_at.replace(tzinfo=UTC) >= cutoff
        )
        out.append(item)
    return {"success": True, "entries": out, "pending": pending_total, "promotion_ready": promotion_ready}


async def stats(user_id: str) -> dict:
    async with get_db_context() as db:
        rows = (
            await db.execute(
                select(AgentLearning.status, AgentLearning.kind, func.count())
                .where(AgentLearning.user_id == user_id)
                .group_by(AgentLearning.status, AgentLearning.kind)
            )
        ).all()
        top = (
            await db.execute(
                select(AgentLearning)
                .where(AgentLearning.user_id == user_id, AgentLearning.status == "pending")
                .order_by(AgentLearning.recurrence_count.desc())
                .limit(5)
            )
        )
        top_pending = [r.to_dict() for r in top.scalars().all()]
    by_status: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for status, kind, count in rows:
        by_status[status] = by_status.get(status, 0) + count
        by_kind[kind] = by_kind.get(kind, 0) + count
    return {"success": True, "by_status": by_status, "by_kind": by_kind, "top_pending": top_pending}


async def resolve(user_id: str, learning_id: str, note: str = "", status: str = "resolved") -> dict:
    """状态迁移(白名单转移; promoted_to_skill 由晋升流程写入并带 promoted_skill 回链)."""
    if status not in ("resolved", "dismissed", "pending"):
        return {"success": False, "error": "status 只允许 resolved|dismissed|pending"}
    async with get_db_context() as db:
        row = (
            await db.execute(
                select(AgentLearning).where(AgentLearning.user_id == user_id, AgentLearning.id == learning_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return {"success": False, "error": f"learning {learning_id} 不存在"}
        if status not in _STATUS_TRANSITIONS.get(row.status, set()):
            return {"success": False, "error": f"不允许 {row.status} -> {status}"}
        row.status = status
        if note:
            row.details = f"{(row.details or '')} | resolve note: {note[:300]}"[:4000]
        await db.commit()
        return {"success": True, "id": row.id, "status": row.status}


async def counts(user_id: str) -> tuple[int, int]:
    """(pending, promotion_ready) — D14 响应尾注数据源."""
    result = await surface(user_id, limit=1)
    return result.get("pending", 0), result.get("promotion_ready", 0)
