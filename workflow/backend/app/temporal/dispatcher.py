"""Command/outbox dispatcher and scheduled reconciliation loop.

Run as a separate process::

    python -m app.temporal.dispatcher

It has three responsibilities:

* start one long-running ``FlowInstanceWorkflow`` per active instance;
* signal the workflow with durable, idempotent ``flow_command`` rows;
* deliver ``flow_outbox`` events to the marketing BFF webhook with retries.

The reconciler loop repairs commands/workflows/outbox rows that were left in an
intermediate state by a crash or a rolling deploy.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import and_, or_, select, update
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from ..config import settings
from ..database import session_scope
from ..engine import commands
from ..models import FlowCommand, FlowInstance, FlowInstanceRuntime, FlowOutboxEvent
from ..utils import from_json, to_json, utcnow
from .client import close_client, get_client
from .workflow import FlowInstanceWorkflow

logger = logging.getLogger("workflow.dispatcher")

EventSender = Callable[[FlowOutboxEvent, dict[str, Any], dict[str, str], bytes], Awaitable[None]]


def _backoff(base_seconds: int, attempts: int) -> timedelta:
    return timedelta(seconds=min(300, max(1, base_seconds) * (2 ** min(max(attempts, 1), 7))))


async def ensure_workflow_started(
    instance_id: int,
    *,
    client: Any | None = None,
    force: bool = False,
) -> bool:
    if not settings.temporal_enabled:
        return False

    async with session_scope() as session:
        instance = await session.get(FlowInstance, instance_id)
        if instance is None or instance.del_flag != "0":
            return False
        if instance.flow_status in commands.TERMINAL_FLOW_STATUSES:
            row = await session.get(FlowInstanceRuntime, instance_id)
            if row is not None and row.status != "COMPLETED":
                row.status = "COMPLETED"
                row.completed_at = utcnow()
                row.last_sync_at = utcnow()
            return False
        row = await session.get(FlowInstanceRuntime, instance_id)
        if row is None:
            row = FlowInstanceRuntime(
                instance_id=instance_id,
                workflow_id=commands.workflow_id_for(instance_id),
                engine="temporal",
                status="STARTING",
                tenant_id=instance.tenant_id,
                create_time=utcnow(),
                create_by="system",
                update_time=utcnow(),
                update_by="system",
            )
            session.add(row)
            await session.flush()
        if row.status == "DISABLED" and not settings.temporal_enabled:
            return False
        if row.status == "RUNNING" and row.run_id and not force:
            return True
        if row.status == "RUNNING" and not force:
            return True
        workflow_id = row.workflow_id or commands.workflow_id_for(instance_id)
        row.engine = "temporal"
        row.status = "STARTING"
        row.last_sync_at = utcnow()
        row.last_error = None
        await session.commit()

    temporal = client or await get_client()
    handle = None
    try:
        handle = await temporal.start_workflow(
            FlowInstanceWorkflow.run,
            instance_id,
            id=workflow_id,
            task_queue=settings.temporal_task_queue,
            id_reuse_policy=(
                WorkflowIDReusePolicy.ALLOW_DUPLICATE if force else WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY
            ),
        )
    except WorkflowAlreadyStartedError:
        handle = temporal.get_workflow_handle(workflow_id)
    except Exception as exc:  # noqa: BLE001 - version-specific already-started shape
        if isinstance(exc, WorkflowAlreadyStartedError) or "already started" in str(exc).lower():
            handle = temporal.get_workflow_handle(workflow_id)
        else:
            async with session_scope() as session:
                row = await session.get(FlowInstanceRuntime, instance_id)
                if row is not None:
                    row.status = "STARTING"
                    row.last_sync_at = utcnow()
                    row.last_error = f"{exc.__class__.__name__}: {exc}"[:2000]
            raise

    run_id = getattr(handle, "result_run_id", None) if handle is not None else None
    async with session_scope() as session:
        row = await session.get(FlowInstanceRuntime, instance_id)
        if row is not None:
            row.run_id = run_id or row.run_id
            row.status = "RUNNING"
            row.started_at = row.started_at or utcnow()
            row.last_sync_at = utcnow()
            row.last_error = None
    logger.info("workflow started: instance=%s workflow_id=%s", instance_id, workflow_id)
    return True


async def _claim_command(command_id: int) -> FlowCommand | None:
    async with session_scope() as session:
        command = await session.get(FlowCommand, command_id)
        if command is None:
            return None
        if command.status != commands.COMMAND_PENDING:
            return command
        result = await session.execute(
            update(FlowCommand)
            .where(FlowCommand.id == command_id, FlowCommand.status == commands.COMMAND_PENDING)
            .values(
                status=commands.COMMAND_DISPATCHING,
                attempts=FlowCommand.attempts + 1,
                update_time=utcnow(),
            )
        )
        if result.rowcount != 1:
            await session.rollback()
            return await session.get(FlowCommand, command_id)
        await session.commit()
        await session.refresh(command)
        return command


async def dispatch_command(command_id: int, *, client: Any | None = None) -> FlowCommand | None:
    if not settings.temporal_enabled:
        return None
    command = await _claim_command(command_id)
    if command is None:
        return None
    if command.status != commands.COMMAND_DISPATCHING:
        return command

    try:
        ready = await ensure_workflow_started(command.instance_id, client=client)
        if not ready:
            async with session_scope() as session:
                row = await session.get(FlowCommand, command_id)
                if row is not None:
                    row.status = commands.COMMAND_CANCELLED
                    row.error_code = 409
                    row.last_error = "流程已结束或实例不存在，命令取消"
                    row.update_time = utcnow()
                return row
        temporal = client or await get_client()
        workflow_id = command.workflow_id or commands.workflow_id_for(command.instance_id)
        try:
            await temporal.get_workflow_handle(workflow_id).signal("command", {"id": command.id})
        except RPCError as exc:
            if exc.status != RPCStatusCode.NOT_FOUND:
                raise
            # The projection said RUNNING but Temporal lost the execution (e.g.
            # namespace reset). Start a fresh run and signal it once.
            await ensure_workflow_started(command.instance_id, client=client, force=True)
            await temporal.get_workflow_handle(workflow_id).signal("command", {"id": command.id})
        async with session_scope() as session:
            await session.execute(
                update(FlowCommand)
                .where(
                    FlowCommand.id == command_id,
                    FlowCommand.status == commands.COMMAND_DISPATCHING,
                )
                .values(
                    status=commands.COMMAND_DISPATCHED,
                    dispatched_at=utcnow(),
                    last_error=None,
                    update_time=utcnow(),
                )
            )
            return await session.get(FlowCommand, command_id)
    except Exception as exc:  # noqa: BLE001 - durable retry is the point
        logger.warning("command %s dispatch failed: %s", command_id, exc)
        async with session_scope() as session:
            row = await session.get(FlowCommand, command_id)
            if row is None:
                return None
            if row.status != commands.COMMAND_DISPATCHING:
                return row
            row.last_error = f"{exc.__class__.__name__}: {exc}"[:2000]
            if row.attempts >= settings.command_max_attempts:
                row.status = commands.COMMAND_FAILED
                row.error_code = 503
                row.applied_at = None
            else:
                row.status = commands.COMMAND_PENDING
                row.available_at = utcnow() + _backoff(settings.command_backoff_base_seconds, row.attempts)
            row.update_time = utcnow()
            return row


async def dispatch_pending_commands(limit: int = 20, *, client: Any | None = None) -> int:
    if not settings.temporal_enabled:
        return 0
    async with session_scope() as session:
        ids = list(
            (
                await session.execute(
                    select(FlowCommand.id)
                    .where(
                        FlowCommand.status == commands.COMMAND_PENDING,
                        FlowCommand.available_at <= utcnow(),
                    )
                    .order_by(FlowCommand.id.asc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    dispatched = 0
    for command_id in ids:
        result = await dispatch_command(command_id, client=client)
        if result is not None and result.status == commands.COMMAND_DISPATCHED:
            dispatched += 1
    return dispatched


async def start_pending_instances(limit: int = 20, *, client: Any | None = None) -> int:
    if not settings.temporal_enabled:
        return 0
    cutoff = utcnow() - timedelta(seconds=max(1, settings.reconcile_stale_seconds))
    async with session_scope() as session:
        ids = list(
            (
                await session.execute(
                    select(FlowInstanceRuntime.instance_id)
                    .join(FlowInstance, FlowInstance.id == FlowInstanceRuntime.instance_id)
                    .where(
                        or_(
                            FlowInstanceRuntime.status == "STARTING",
                            and_(
                                FlowInstanceRuntime.status == "FAILED",
                                or_(
                                    FlowInstanceRuntime.last_sync_at.is_(None),
                                    FlowInstanceRuntime.last_sync_at < cutoff,
                                ),
                            ),
                        ),
                        FlowInstance.del_flag == "0",
                        FlowInstance.flow_status.notin_(commands.TERMINAL_FLOW_STATUSES),
                    )
                    .order_by(FlowInstanceRuntime.instance_id.asc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    started = 0
    for instance_id in ids:
        try:
            if await ensure_workflow_started(instance_id, client=client):
                started += 1
        except Exception as exc:  # noqa: BLE001 - retried next tick
            logger.warning("instance %s workflow start failed: %s", instance_id, exc)
    return started


async def _post_event(
    event: FlowOutboxEvent,
    payload: dict[str, Any],
    headers: dict[str, str],
    body: bytes,
) -> None:
    async with httpx.AsyncClient(timeout=settings.event_webhook_timeout_seconds) as client:
        response = await client.post(settings.event_webhook_url, content=body, headers=headers)
        response.raise_for_status()


async def _claim_outbox(event_id: int) -> FlowOutboxEvent | None:
    async with session_scope() as session:
        event = await session.get(FlowOutboxEvent, event_id)
        if event is None:
            return None
        if event.status != "PENDING":
            return event
        result = await session.execute(
            update(FlowOutboxEvent)
            .where(FlowOutboxEvent.id == event_id, FlowOutboxEvent.status == "PENDING")
            .values(status="SENDING", attempts=FlowOutboxEvent.attempts + 1, update_time=utcnow())
        )
        if result.rowcount != 1:
            await session.rollback()
            return await session.get(FlowOutboxEvent, event_id)
        await session.commit()
        await session.refresh(event)
        return event


async def dispatch_outbox_once(
    limit: int = 20,
    *,
    sender: EventSender | None = None,
) -> int:
    async with session_scope() as session:
        ids = list(
            (
                await session.execute(
                    select(FlowOutboxEvent.id)
                    .where(
                        FlowOutboxEvent.status == "PENDING",
                        FlowOutboxEvent.available_at <= utcnow(),
                    )
                    .order_by(FlowOutboxEvent.id.asc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    delivered = 0
    for event_id in ids:
        event = await _claim_outbox(event_id)
        if event is None or event.status != "SENDING":
            continue
        payload = from_json(event.payload, {})
        if not isinstance(payload, dict):
            payload = {"value": payload}
        body = to_json(payload).encode("utf-8")
        timestamp = utcnow().isoformat()
        headers = {
            "Content-Type": "application/json",
            "X-Workflow-Event": event.event_type,
            "X-Workflow-Delivery": str(event.id),
            "X-Workflow-Timestamp": timestamp,
        }
        if settings.event_webhook_secret:
            digest = hmac.new(
                settings.event_webhook_secret.encode("utf-8"),
                f"{timestamp}.".encode() + body,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Workflow-Signature"] = f"sha256={digest}"
        try:
            if sender is not None:
                await sender(event, payload, headers, body)
            elif not settings.event_webhook_url:
                async with session_scope() as session:
                    row = await session.get(FlowOutboxEvent, event_id)
                    if row is not None:
                        row.status = "SKIPPED"
                        row.delivered_at = utcnow()
                        row.last_error = "WORKFLOW_EVENT_WEBHOOK_URL is not configured"
                        row.update_time = utcnow()
                continue
            else:
                await _post_event(event, payload, headers, body)
            async with session_scope() as session:
                row = await session.get(FlowOutboxEvent, event_id)
                if row is not None:
                    row.status = "SENT"
                    row.delivered_at = utcnow()
                    row.last_error = None
                    row.update_time = utcnow()
            delivered += 1
        except Exception as exc:  # noqa: BLE001 - retry with backoff
            logger.warning("outbox event %s delivery failed: %s", event_id, exc)
            async with session_scope() as session:
                row = await session.get(FlowOutboxEvent, event_id)
                if row is None:
                    continue
                row.last_error = f"{exc.__class__.__name__}: {exc}"[:2000]
                if row.attempts >= settings.outbox_max_attempts:
                    row.status = "FAILED"
                    row.delivered_at = None
                else:
                    row.status = "PENDING"
                    row.available_at = utcnow() + _backoff(settings.outbox_backoff_base_seconds, row.attempts)
                row.update_time = utcnow()
    return delivered


async def dispatcher_loop() -> None:
    while True:
        try:
            if settings.temporal_enabled:
                await start_pending_instances(limit=20)
                await dispatch_pending_commands(limit=50)
            await dispatch_outbox_once(limit=50)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - loop must survive transient failures
            logger.exception("workflow dispatcher tick failed")
        await asyncio.sleep(max(1, settings.command_dispatch_interval_seconds))


async def run_dispatcher() -> None:
    from .reconciler import reconciler_loop

    logger.info(
        "workflow dispatcher started: queue=%s webhook=%s",
        settings.temporal_task_queue,
        settings.event_webhook_url or "disabled",
    )
    try:
        await asyncio.gather(dispatcher_loop(), reconciler_loop())
    finally:
        await close_client()


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_dispatcher())


if __name__ == "__main__":
    main()
