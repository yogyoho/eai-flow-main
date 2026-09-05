"""Read-only query helpers over runs / run_events for ops diagnosis.

EAI-CUSTOM (route-D): all queries are SELECT-only. The `runs` table gives
per-run terminal state (status/stop_reason/tokens); the `run_events` table
gives the ordered event stream (tool calls, tool results, errors).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.persistence.models.run_event import RunEventRow
from deerflow.persistence.run.model import RunRow

DEFAULT_EVENT_LIMIT = 200
MAX_EVENT_LIMIT = 1000
DEFAULT_MAX_CONTENT_CHARS = 2000


def _decode_content(raw: str) -> str:
    """run_events.content is TEXT; JSON-encoded payloads are decoded back to readable JSON text."""
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return raw
    if isinstance(parsed, str):
        return parsed
    return json.dumps(parsed, ensure_ascii=False, default=str)


def _clip(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


async def list_thread_runs(session: AsyncSession, thread_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Run inventory for a thread: terminal state + token totals + event counts."""
    event_counts = select(RunEventRow.run_id, func.count().label("n")).where(RunEventRow.thread_id == thread_id).group_by(RunEventRow.run_id).subquery()
    stmt = (
        select(
            RunRow.run_id,
            RunRow.status,
            RunRow.stop_reason,
            RunRow.model_name,
            RunRow.operation_kind,
            RunRow.error,
            RunRow.total_tokens,
            RunRow.llm_call_count,
            RunRow.message_count,
            RunRow.created_at,
            func.coalesce(event_counts.c.n, 0).label("event_count"),
        )
        .outerjoin(event_counts, event_counts.c.run_id == RunRow.run_id)
        .where(RunRow.thread_id == thread_id)
        .order_by(RunRow.created_at)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "run_id": r.run_id,
            "run8": r.run_id[:8],
            "status": r.status,
            "stop_reason": r.stop_reason,
            "model_name": r.model_name,
            "operation_kind": r.operation_kind,
            "error": (r.error[:500] if r.error else None),
            "total_tokens": r.total_tokens,
            "llm_call_count": r.llm_call_count,
            "message_count": r.message_count,
            "event_count": int(r.event_count),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def get_run_events(
    session: AsyncSession,
    thread_id: str,
    *,
    run_id: str | None = None,
    event_type: str | None = None,
    text_match: str | None = None,
    limit: int = DEFAULT_EVENT_LIMIT,
    max_content_chars: int = DEFAULT_MAX_CONTENT_CHARS,
) -> dict[str, Any]:
    """Filtered run-event stream. Server-side filtering keeps big threads from blowing the agent's context."""
    limit = max(1, min(int(limit), MAX_EVENT_LIMIT))
    conditions = [RunEventRow.thread_id == thread_id]
    if run_id:
        conditions.append(RunEventRow.run_id == run_id)
    if event_type:
        conditions.append(RunEventRow.event_type == event_type)
    if text_match:
        conditions.append(RunEventRow.content.like(f"%{text_match}%"))

    total_stmt = select(func.count()).select_from(RunEventRow).where(*conditions)
    total = (await session.execute(total_stmt)).scalar() or 0

    stmt = select(RunEventRow).where(*conditions).order_by(RunEventRow.seq).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()

    events = []
    for row in rows:
        text = _decode_content(row.content)
        clipped, was_clipped = _clip(text, max_content_chars)
        events.append(
            {
                "seq": row.seq,
                "run_id": row.run_id,
                "event_type": row.event_type,
                "category": row.category,
                "content": clipped,
                "truncated": was_clipped or bool((row.event_metadata or {}).get("content_truncated")),
                "metadata": row.event_metadata or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return {"total_matching": total, "returned": len(events), "events": events}
