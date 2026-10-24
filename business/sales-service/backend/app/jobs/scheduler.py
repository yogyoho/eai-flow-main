"""Periodic rule jobs: stage overdue, todo escalation and probability refresh."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select, text

from app.config import get_settings
from app.database import get_session_maker
from app.domain import create_todo, refresh_probability, utc_now
from app.models import Opportunity, Todo, TodoEscalation

logger = logging.getLogger(__name__)
settings = get_settings()
LOCK_KEY = 82420261022


async def run_once() -> dict[str, int]:
    created = 0
    escalated = 0
    refreshed = 0
    async with get_session_maker()() as db:
        locked = (await db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY})).scalar()
        if not locked:
            return {"created": 0, "escalated": 0, "refreshed": 0, "skipped": 1}
        try:
            overdue = list(
                (
                    await db.execute(
                        select(Opportunity).where(
                            Opportunity.status == "active",
                            Opportunity.stage_due_at.is_not(None),
                            Opportunity.stage_due_at < utc_now(),
                        )
                    )
                ).scalars()
            )
            for opp in overdue:
                await refresh_probability(db, opp)
                refreshed += 1
                bucket = utc_now().strftime("%Y%m%d")
                todo = await create_todo(
                    db,
                    type="rule_event",
                    severity="high",
                    title=f"阶段超期：{opp.name}",
                    description=f"{opp.opportunity_no} 在 {opp.stage} 阶段停留超过 SLA，需推进或回退并说明原因。",
                    object_type="opportunity",
                    object_id=opp.id,
                    dedupe_key=f"stage-overdue:{opp.id}:{opp.stage}:{bucket}",
                    source_rule="STAGE_OVERDUE",
                    assignee_role="regional_manager",
                    created_by="scheduler",
                    due_hours=24,
                )
                if todo:
                    created += 1

            due_todos = list(
                (
                    await db.execute(
                        select(Todo).where(
                            Todo.status.in_(["open", "in_progress"]),
                            Todo.type != "approval",
                            Todo.due_at.is_not(None),
                            Todo.due_at < utc_now(),
                            Todo.escalation_level < 2,
                        )
                    )
                ).scalars()
            )
            for todo in due_todos:
                previous_role = todo.assignee_role
                todo.escalation_level += 1
                todo.severity = "blocker"
                if previous_role == "regional_manager":
                    todo.assignee_role = "sales_director"
                    todo.assignee_id = None
                elif previous_role in {"sales_rep", "bid_manager"}:
                    todo.assignee_role = "regional_manager"
                    todo.assignee_id = None
                elif previous_role == "compliance_officer":
                    todo.assignee_role = "sales_director"
                    todo.assignee_id = None
                todo.due_at = utc_now() + timedelta(hours=4)
                db.add(
                    TodoEscalation(
                        todo_id=todo.id,
                        level=todo.escalation_level,
                        from_assignee=todo.assignee_id,
                        to_role=todo.assignee_role,
                        reason="SLA 超时自动升级",
                    )
                )
                escalated += 1
            await db.commit()
        finally:
            await db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
            await db.commit()
    return {"created": created, "escalated": escalated, "refreshed": refreshed}


async def scheduler_loop() -> None:
    while True:
        try:
            result = await run_once()
            if result.get("created") or result.get("escalated") or result.get("refreshed"):
                logger.info("sales scheduler: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("sales scheduler failed")
        await asyncio.sleep(settings.scheduler_interval_seconds)
