"""Transactional outbox dispatcher for approval starts."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.approval_service import workflow_input_for
from app.config import get_settings
from app.database import get_session_maker
from app.domain import utc_now
from app.models import ApprovalRequest, OutboxEvent
from app.workflows.client import start_approval_workflow

logger = logging.getLogger(__name__)
settings = get_settings()


def retry_delay_seconds(attempts: int) -> int:
    """Bounded exponential backoff for outbox retries (5s .. 300s)."""
    return min(300, 5 * (2 ** min(max(attempts, 1), 6)))


def _event_failure(db, event: OutboxEvent, request: ApprovalRequest | None, exc: Exception) -> None:
    event.attempts += 1
    event.last_error = str(exc)[:2000]
    if event.attempts >= settings.outbox_max_attempts:
        event.status = "failed"
        event.processed_at = utc_now()
        event.next_retry_at = None
        if request is not None and request.status in {"pending_start", "failed"}:
            request.status = "failed"
            request.completed_at = utc_now()
            request.failure_reason = f"审批启动失败（已重试 {event.attempts} 次）：{str(exc)[:500]}"
        logger.error("outbox event %s exhausted %s attempts: %s", event.id, event.attempts, exc)
        return
    event.next_retry_at = utc_now() + timedelta(seconds=retry_delay_seconds(event.attempts))


async def dispatch_once(limit: int = 20) -> int:
    if not settings.temporal_enabled:
        return 0
    processed = 0
    async with get_session_maker()() as db:
        events = list(
            (
                await db.execute(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.status == "pending",
                        OutboxEvent.next_retry_at <= utc_now(),
                    )
                    .order_by(OutboxEvent.created_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).scalars()
        )
        for event in events:
            request: ApprovalRequest | None = None
            try:
                if event.event_type != "approval.start":
                    event.status = "processed"
                    event.processed_at = utc_now()
                    continue
                request = (await db.execute(select(ApprovalRequest).where(ApprovalRequest.id == event.aggregate_id).options(selectinload(ApprovalRequest.steps)))).scalar_one_or_none()
                if request is None or request.status not in {"pending_start", "failed"}:
                    event.status = "processed"
                    event.processed_at = utc_now()
                    continue
                payload = workflow_input_for(request)
                try:
                    handle = await start_approval_workflow(payload, str(request.id))
                    request.workflow_id = handle.id
                    request.status = "pending_start"
                    request.completed_at = None
                    request.failure_reason = None
                except Exception as exc:  # noqa: BLE001 - already started is the normal idempotent path
                    from temporalio.exceptions import WorkflowAlreadyStartedError

                    if isinstance(exc, WorkflowAlreadyStartedError) or "already started" in str(exc).lower() or "AlreadyStarted" in exc.__class__.__name__:
                        request.workflow_id = f"{settings.temporal_workflow_id_prefix}-{request.id}"
                        if request.status == "failed":
                            # The start RPC succeeded earlier but the projection
                            # never advanced. Let the reconciler repair it.
                            request.status = "pending_start"
                            request.completed_at = None
                            request.failure_reason = None
                    else:
                        raise
                event.status = "processed"
                event.processed_at = utc_now()
                event.last_error = None
                processed += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("outbox event %s failed: %s", event.id, exc)
                _event_failure(db, event, request, exc)
        await db.commit()
    return processed


async def dispatcher_loop() -> None:
    while True:
        try:
            await dispatch_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("outbox dispatcher loop failed")
        await asyncio.sleep(max(1, settings.outbox_dispatch_interval_seconds))
