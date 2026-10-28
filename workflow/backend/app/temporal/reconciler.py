"""Periodic reconciliation between Temporal and the database projection."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from temporalio.service import RPCError, RPCStatusCode

from ..config import settings
from ..database import session_scope
from ..engine import commands
from ..models import FlowCommand, FlowInstance, FlowInstanceRuntime, FlowOutboxEvent
from ..utils import utcnow
from .client import get_client
from .dispatcher import ensure_workflow_started

logger = logging.getLogger("workflow.reconciler")

_ACTIVE_RUNTIME = {"STARTING", "RUNNING", "FAILED"}
_COMMAND_IN_FLIGHT = (commands.COMMAND_PENDING, commands.COMMAND_DISPATCHING, commands.COMMAND_DISPATCHED)
_WORKFLOW_TERMINAL = {"COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT", "CANCELED"}


async def _stale_commands(limit: int) -> int:
    cutoff = utcnow() - timedelta(seconds=max(1, settings.command_stale_seconds))
    repaired = 0
    async with session_scope() as session:
        rows = list(
            (
                await session.execute(
                    select(FlowCommand)
                    .where(
                        FlowCommand.status.in_([commands.COMMAND_DISPATCHING, commands.COMMAND_DISPATCHED]),
                        FlowCommand.update_time < cutoff,
                    )
                    .order_by(FlowCommand.update_time.asc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if row.attempts >= settings.command_max_attempts:
                row.status = commands.COMMAND_FAILED
                row.error_code = 503
                row.last_error = "命令分发超时且已达到最大重试次数"
            else:
                row.status = commands.COMMAND_PENDING
                row.available_at = utcnow()
                row.last_error = "分发状态超时，已重新入队"
            row.update_time = utcnow()
            repaired += 1
    return repaired


async def _terminal_commands(limit: int) -> int:
    repaired = 0
    async with session_scope() as session:
        rows = list(
            (
                await session.execute(
                    select(FlowCommand)
                    .join(FlowInstance, FlowInstance.id == FlowCommand.instance_id)
                    .where(
                        FlowCommand.status.in_(_COMMAND_IN_FLIGHT),
                        FlowInstance.flow_status.in_(commands.TERMINAL_FLOW_STATUSES),
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.status = commands.COMMAND_CANCELLED
            row.error_code = 409
            row.last_error = "流程已结束，命令取消"
            row.update_time = utcnow()
            repaired += 1
    return repaired


async def _stale_outbox(limit: int) -> int:
    cutoff = utcnow() - timedelta(seconds=max(1, settings.outbox_stale_seconds))
    repaired = 0
    async with session_scope() as session:
        rows = list(
            (
                await session.execute(
                    select(FlowOutboxEvent)
                    .where(FlowOutboxEvent.status == "SENDING", FlowOutboxEvent.update_time < cutoff)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if row.attempts >= settings.outbox_max_attempts:
                row.status = "FAILED"
            else:
                row.status = "PENDING"
                row.available_at = utcnow()
            row.last_error = "投递状态超时，已重新入队"
            row.update_time = utcnow()
            repaired += 1
    return repaired


async def _fail_instance_commands(instance_id: int, reason: str) -> None:
    async with session_scope() as session:
        await session.execute(
            update(FlowCommand)
            .where(
                FlowCommand.instance_id == instance_id,
                FlowCommand.status.in_(_COMMAND_IN_FLIGHT),
            )
            .values(
                status=commands.COMMAND_FAILED,
                error_code=503,
                last_error=reason[:2000],
                update_time=utcnow(),
            )
        )


async def _reconcile_one_runtime(instance_id: int, *, client: Any | None = None) -> str:
    temporal = client or await get_client()
    async with session_scope() as session:
        row = await session.get(FlowInstanceRuntime, instance_id)
        if row is None:
            return "missing"
        instance = await session.get(FlowInstance, instance_id)
        if instance is None:
            return "missing"
        workflow_id = row.workflow_id or commands.workflow_id_for(instance_id)
        if instance.flow_status in commands.TERMINAL_FLOW_STATUSES:
            row.status = "COMPLETED"
            row.completed_at = row.completed_at or utcnow()
            row.last_sync_at = utcnow()
            terminal = True
            current_status = row.status
        else:
            terminal = False
            current_status = row.status

    if terminal:
        # The instance may have become terminal through a direct/local path.
        # Stop an otherwise long-running workflow so it does not stay open.
        try:
            await temporal.get_workflow_handle(workflow_id).signal("stop", "instance terminal")
        except Exception:  # noqa: BLE001 - a completed/missing workflow is fine
            pass
        return "terminal"

    if current_status in {"STARTING", "FAILED"}:
        try:
            await ensure_workflow_started(instance_id, client=temporal, force=current_status == "FAILED")
            return "started"
        except Exception as exc:  # noqa: BLE001
            async with session_scope() as session:
                row = await session.get(FlowInstanceRuntime, instance_id)
                if row is not None:
                    row.status = "FAILED"
                    row.last_sync_at = utcnow()
                    row.last_error = f"启动失败：{exc}"[:2000]
            return "start-failed"

    try:
        description = await temporal.get_workflow_handle(workflow_id).describe(
            rpc_timeout=timedelta(seconds=max(1.0, settings.temporal_rpc_timeout_seconds))
        )
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            logger.warning("workflow %s not found; starting a new run", workflow_id)
            try:
                await ensure_workflow_started(instance_id, client=temporal, force=True)
                return "restarted"
            except Exception as start_exc:  # noqa: BLE001
                async with session_scope() as session:
                    row = await session.get(FlowInstanceRuntime, instance_id)
                    if row is not None:
                        row.status = "FAILED"
                        row.last_error = f"重启失败：{start_exc}"[:2000]
                        row.last_sync_at = utcnow()
                return "restart-failed"
        logger.warning("cannot describe workflow %s: %s", workflow_id, exc)
        return "describe-failed"
    except Exception as exc:  # noqa: BLE001 - Temporal may be temporarily down
        logger.warning("cannot describe workflow %s: %s", workflow_id, exc)
        return "describe-failed"

    status_name = description.status.name
    if status_name in {"RUNNING", "CONTINUED_AS_NEW"}:
        async with session_scope() as session:
            row = await session.get(FlowInstanceRuntime, instance_id)
            if row is not None:
                row.status = "RUNNING"
                row.last_sync_at = utcnow()
                row.last_error = None
        return "running"

    if status_name == "COMPLETED":
        try:
            result = await temporal.get_workflow_handle(workflow_id).result(
                rpc_timeout=timedelta(seconds=max(1.0, settings.temporal_rpc_timeout_seconds))
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("cannot load workflow result %s: %s", workflow_id, exc)
            return "result-failed"
        terminal = isinstance(result, dict) and bool(result.get("terminal"))
        flow_status = result.get("flow_status") if isinstance(result, dict) else None
        async with session_scope() as session:
            row = await session.get(FlowInstanceRuntime, instance_id)
            instance = await session.get(FlowInstance, instance_id)
            if row is not None:
                row.status = "COMPLETED"
                row.completed_at = utcnow()
                row.last_sync_at = utcnow()
                row.last_error = None
            if instance is not None and not terminal and instance.flow_status not in commands.TERMINAL_FLOW_STATUSES:
                reason = f"Temporal 工作流已结束但实例仍为 {instance.flow_status}（结果 {flow_status}）"
                if row is not None:
                    row.status = "FAILED"
                    row.last_error = reason
                await session.execute(
                    update(FlowCommand)
                    .where(
                        FlowCommand.instance_id == instance_id,
                        FlowCommand.status.in_(_COMMAND_IN_FLIGHT),
                    )
                    .values(
                        status=commands.COMMAND_FAILED,
                        error_code=503,
                        last_error=reason[:2000],
                        update_time=utcnow(),
                    )
                )
        return "completed"

    if status_name in _WORKFLOW_TERMINAL:
        reason = f"Temporal 工作流状态 {status_name}"
        async with session_scope() as session:
            row = await session.get(FlowInstanceRuntime, instance_id)
            if row is not None:
                row.status = "FAILED"
                row.last_sync_at = utcnow()
                row.last_error = reason
        await _fail_instance_commands(instance_id, reason)
        return "failed"

    logger.info("workflow %s status %s is not terminal", workflow_id, status_name)
    return status_name.lower()


async def _reconcile_runtimes(limit: int, *, client: Any | None = None) -> int:
    cutoff = utcnow() - timedelta(seconds=max(1, settings.reconcile_stale_seconds))
    async with session_scope() as session:
        ids = list(
            (
                await session.execute(
                    select(FlowInstanceRuntime.instance_id)
                    .join(FlowInstance, FlowInstance.id == FlowInstanceRuntime.instance_id)
                    .where(
                        FlowInstanceRuntime.status.in_(_ACTIVE_RUNTIME),
                        FlowInstance.del_flag == "0",
                        (FlowInstanceRuntime.last_sync_at.is_(None)) | (FlowInstanceRuntime.last_sync_at < cutoff),
                    )
                    .order_by(FlowInstanceRuntime.last_sync_at.asc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    repaired = 0
    for instance_id in ids:
        try:
            result = await _reconcile_one_runtime(instance_id, client=client)
            if result not in {"running", "missing", "describe-failed"}:
                repaired += 1
        except Exception:  # noqa: BLE001
            logger.exception("reconciler failed for instance %s", instance_id)
    return repaired


async def reconcile_once(*, client: Any | None = None) -> dict[str, int]:
    if not settings.temporal_enabled:
        return {"commands": 0, "terminal_commands": 0, "outbox": 0, "runtimes": 0}
    limit = max(1, settings.reconcile_batch_size)
    result = {
        "commands": await _stale_commands(limit),
        "terminal_commands": await _terminal_commands(limit),
        "outbox": await _stale_outbox(limit),
        "runtimes": await _reconcile_runtimes(limit, client=client),
    }
    if any(result.values()):
        logger.info("reconciled: %s", result)
    return result


async def reconciler_loop() -> None:
    while True:
        try:
            await reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - loop must survive transient failures
            logger.exception("workflow reconciler tick failed")
        await asyncio.sleep(max(10, settings.reconcile_interval_seconds))
