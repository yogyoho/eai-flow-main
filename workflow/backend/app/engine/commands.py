"""Durable command inbox and transactional outbox.

The API never mutates approval state directly once Temporal is enabled. It
writes a ``flow_command`` row and signals the long-running
``FlowInstanceWorkflow``; the worker applies the command through the existing
``engine.runtime`` functions in one database transaction together with the
command status and an outbox event.

With ``TEMPORAL_ENABLED=0`` commands are applied synchronously in-process, which
keeps the standalone demo and the test suite working without a Temporal server.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session_factory
from ..models import (
    FlowCommand,
    FlowDefinition,
    FlowInstance,
    FlowInstanceRuntime,
    FlowOutboxEvent,
    FlowTask,
)
from ..utils import from_json, next_id, to_json, utcnow
from . import runtime
from .enums import FlowStatus
from .errors import ConflictError, NotFoundError, WorkflowError

logger = logging.getLogger("workflow.commands")

COMMAND_START = "START"
COMMAND_APPROVE = "APPROVE"
COMMAND_REJECT = "REJECT"
COMMAND_RETURN = "RETURN"
COMMAND_REJECT_LAST = "REJECT_LAST"
COMMAND_REVOKE = "REVOKE"
COMMAND_TERMINATE = "TERMINATE"
COMMAND_TRANSFER = "TRANSFER"
COMMAND_DEPUTE = "DEPUTE"
COMMAND_ADD_SIGNATURE = "ADD_SIGNATURE"
COMMAND_REDUCE_SIGNATURE = "REDUCE_SIGNATURE"

COMMAND_PENDING = "PENDING"
COMMAND_DISPATCHING = "DISPATCHING"
COMMAND_DISPATCHED = "DISPATCHED"
COMMAND_APPLIED = "APPLIED"
COMMAND_FAILED = "FAILED"
COMMAND_CANCELLED = "CANCELLED"

TERMINAL_FLOW_STATUSES = {
    FlowStatus.FINISHED,
    FlowStatus.TERMINATE,
    FlowStatus.CANCEL,
    FlowStatus.NULLIFY,
}


def workflow_id_for(instance_id: int) -> str:
    return f"{settings.temporal_workflow_id_prefix}-{instance_id}"


def _key(value: str | None) -> str:
    return (value or uuid.uuid4().hex)[:200]


def _payload(command: FlowCommand) -> dict[str, Any]:
    value = from_json(command.payload, {})
    return value if isinstance(value, dict) else {}


def _claims(command: FlowCommand) -> list[str]:
    value = from_json(command.claims, [])
    return [str(item) for item in value] if isinstance(value, list) else []


def _result(command: FlowCommand) -> dict[str, Any]:
    value = from_json(command.result, {})
    return value if isinstance(value, dict) else {}


def raise_for_command(command: FlowCommand | None) -> None:
    if command is None:
        return
    if command.status == COMMAND_FAILED:
        raise WorkflowError(
            command.last_error or "工作流命令执行失败",
            status_code=command.error_code or 409,
        )
    if command.status == COMMAND_CANCELLED:
        raise ConflictError("流程已结束，命令已取消")


def _same_command(
    existing: FlowCommand, *, command_type: str, instance_id: int, task_id: int | None, payload: dict[str, Any]
) -> bool:
    return (
        existing.command_type == command_type
        and existing.instance_id == instance_id
        and (existing.task_id or None) == (task_id or None)
        and _payload(existing) == payload
    )


async def _existing_by_key(session: AsyncSession, key: str) -> FlowCommand | None:
    return (await session.execute(select(FlowCommand).where(FlowCommand.idempotency_key == key))).scalar_one_or_none()


async def find_by_idempotency_key(session: AsyncSession, key: str | None) -> FlowCommand | None:
    if not key:
        return None
    return await _existing_by_key(session, key[:200])


def _task_event_payload(task: FlowTask, assignees: list[str]) -> dict[str, Any]:
    return {
        "id": task.id,
        "node_code": task.node_code,
        "node_name": task.node_name,
        "node_type": task.node_type,
        "flow_status": task.flow_status,
        "assignees": assignees,
    }


async def _event_payload(
    session: AsyncSession,
    instance: FlowInstance,
    command: FlowCommand,
    event_type: str,
) -> dict[str, Any]:
    definition = await session.get(FlowDefinition, instance.definition_id)
    tasks = list(
        (
            await session.execute(
                select(FlowTask)
                .where(FlowTask.instance_id == instance.id, FlowTask.del_flag == "0")
                .order_by(FlowTask.id.asc())
            )
        )
        .scalars()
        .all()
    )
    task_payloads = []
    for task in tasks:
        users = await runtime.task_users(session, task.id)
        task_payloads.append(_task_event_payload(task, [user.processed_by or "" for user in users]))
    return {
        "event": event_type,
        "occurred_at": utcnow().isoformat(),
        "command": {
            "id": command.id,
            "type": command.command_type,
            "actor": command.actor,
        },
        "instance": {
            "id": instance.id,
            "definition_id": instance.definition_id,
            "business_id": instance.business_id,
            "flow_name": definition.flow_name if definition else None,
            "flow_status": instance.flow_status,
            "activity_status": instance.activity_status,
            "node_type": instance.node_type,
            "node_code": instance.node_code,
            "node_name": instance.node_name,
            "variables": from_json(instance.variable, {}),
            "tenant_id": instance.tenant_id,
            "update_time": instance.update_time.isoformat() if instance.update_time else None,
        },
        "tasks": task_payloads,
    }


def _event_type(command_type: str, instance: FlowInstance) -> str:
    if command_type == COMMAND_START:
        return "workflow.instance.started"
    if instance.flow_status in TERMINAL_FLOW_STATUSES:
        return "workflow.instance.completed"
    return "workflow.instance.updated"


async def _add_outbox_event(
    session: AsyncSession,
    instance: FlowInstance,
    command: FlowCommand,
    event_type: str,
) -> FlowOutboxEvent | None:
    dedupe = f"command:{command.id}:{event_type}"
    existing = (
        await session.execute(select(FlowOutboxEvent).where(FlowOutboxEvent.dedupe_key == dedupe))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    event = FlowOutboxEvent(
        id=next_id(),
        instance_id=instance.id,
        command_id=command.id,
        event_type=event_type,
        aggregate_type="flow_instance",
        aggregate_id=str(instance.id),
        payload=to_json(await _event_payload(session, instance, command, event_type)),
        status="PENDING",
        dedupe_key=dedupe,
        attempts=0,
        available_at=utcnow(),
        tenant_id=instance.tenant_id,
        create_time=utcnow(),
        create_by=command.actor,
        update_time=utcnow(),
        update_by=command.actor,
    )
    session.add(event)
    return event


async def start_instance_command(
    session: AsyncSession,
    *,
    flow_code: str,
    business_id: str,
    handler: str,
    variables: dict[str, Any] | None = None,
    flow_status: str | None = None,
    ext: str | None = None,
    tenant_id: str | None = None,
    idempotency_key: str | None = None,
) -> tuple[FlowInstance, FlowCommand]:
    """Create the instance and its START command atomically.

    Start is intentionally synchronous so the caller receives an instance id and
    its first task immediately. The long-running Temporal workflow is started
    right after the transaction by the API/dispatcher; if that call is lost, the
    reconciler starts it from ``flow_instance_runtime``.
    """

    key = _key(idempotency_key)
    existing = await _existing_by_key(session, key)
    if existing is not None:
        existing_payload = _payload(existing)
        if (
            existing.command_type != COMMAND_START
            or existing_payload.get("flow_code") != flow_code
            or existing_payload.get("handler") != handler
        ):
            raise ConflictError("幂等键已被其他启动请求使用")
        if existing.status != COMMAND_APPLIED:
            raise ConflictError("启动命令正在处理中，请稍后重试")
        instance = await session.get(FlowInstance, existing.instance_id)
        if instance is None:
            raise NotFoundError("启动命令对应的实例不存在")
        return instance, existing

    now = utcnow()
    payload = {
        "flow_code": flow_code,
        "business_id": business_id,
        "handler": handler,
        "variables": variables or {},
        "flow_status": flow_status,
        "ext": ext,
    }
    instance = await runtime.start_instance(
        session,
        flow_code=flow_code,
        business_id=business_id,
        handler=handler,
        variables=variables,
        flow_status=flow_status,
        ext=ext,
        tenant_id=tenant_id,
        commit=False,
    )
    command = FlowCommand(
        id=next_id(),
        instance_id=instance.id,
        definition_id=instance.definition_id,
        command_type=COMMAND_START,
        actor=handler,
        payload=to_json(payload),
        claims=to_json([]),
        status=COMMAND_APPLIED,
        idempotency_key=key,
        workflow_id=workflow_id_for(instance.id),
        attempts=0,
        available_at=now,
        applied_at=now,
        dispatched_at=now,
        result=to_json(
            {
                "instance_id": instance.id,
                "flow_status": instance.flow_status,
                "terminal": instance.flow_status in TERMINAL_FLOW_STATUSES,
            }
        ),
        tenant_id=instance.tenant_id,
        create_time=now,
        create_by=handler,
        update_time=now,
        update_by=handler,
    )
    session.add(command)
    terminal = instance.flow_status in TERMINAL_FLOW_STATUSES
    runtime_row = FlowInstanceRuntime(
        instance_id=instance.id,
        workflow_id=workflow_id_for(instance.id),
        run_id=None,
        engine="temporal" if settings.temporal_enabled else "local",
        status=("COMPLETED" if terminal else ("STARTING" if settings.temporal_enabled else "DISABLED")),
        started_at=now,
        last_sync_at=now,
        completed_at=now if terminal else None,
        tenant_id=instance.tenant_id,
        create_time=now,
        create_by=handler,
        update_time=now,
        update_by=handler,
    )
    session.add(runtime_row)
    await _add_outbox_event(session, instance, command, "workflow.instance.started")
    try:
        await session.commit()
    except IntegrityError:
        # Concurrent retry with the same Idempotency-Key. The whole transaction
        # (including the duplicate instance) is rolled back by SQLAlchemy.
        await session.rollback()
        existing = await _existing_by_key(session, key)
        if existing is not None and existing.status == COMMAND_APPLIED:
            instance = await session.get(FlowInstance, existing.instance_id)
            if instance is not None:
                return instance, existing
        raise
    await session.refresh(instance)
    await session.refresh(command)
    return instance, command


async def create_command(
    session: AsyncSession,
    *,
    command_type: str,
    instance_id: int,
    task_id: int | None,
    actor: str,
    payload: dict[str, Any],
    claims: list[str] | None = None,
    idempotency_key: str | None = None,
) -> FlowCommand:
    key = _key(idempotency_key)
    existing = await _existing_by_key(session, key)
    if existing is not None:
        if not _same_command(
            existing, command_type=command_type, instance_id=instance_id, task_id=task_id, payload=payload
        ):
            raise ConflictError("幂等键已被其他命令使用")
        return existing

    instance = await session.get(FlowInstance, instance_id)
    if instance is None or instance.del_flag != "0":
        raise NotFoundError("流程实例不存在")
    if settings.temporal_enabled and instance.flow_status in TERMINAL_FLOW_STATUSES:
        # In-process mode still lets the runtime return the precise permission
        # error for repeated terminal actions (existing API contract). With
        # Temporal, a terminal workflow cannot consume a new signal safely.
        raise ConflictError("流程已结束，无法提交新命令")
    if task_id is not None:
        task = await session.get(FlowTask, task_id)
        if task is None or task.del_flag != "0" or task.instance_id != instance_id:
            raise NotFoundError("待办任务不存在")

    now = utcnow()
    command = FlowCommand(
        id=next_id(),
        instance_id=instance_id,
        definition_id=instance.definition_id,
        task_id=task_id,
        command_type=command_type,
        actor=actor,
        payload=to_json(payload),
        claims=to_json(claims or []),
        status=COMMAND_PENDING,
        idempotency_key=key,
        workflow_id=workflow_id_for(instance_id),
        attempts=0,
        available_at=now,
        tenant_id=instance.tenant_id,
        create_time=now,
        create_by=actor,
        update_time=now,
        update_by=actor,
    )
    session.add(command)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await _existing_by_key(session, key)
        if existing is not None and _same_command(
            existing, command_type=command_type, instance_id=instance_id, task_id=task_id, payload=payload
        ):
            return existing
        raise
    await session.refresh(command)
    return command


async def wait_for_command(command_id: int, timeout: float | None = None) -> FlowCommand | None:
    deadline = time.monotonic() + max(0.2, timeout if timeout is not None else settings.command_wait_timeout_seconds)
    while time.monotonic() < deadline:
        factory = get_session_factory()
        async with factory() as session:
            command = await session.get(FlowCommand, command_id)
            if command is not None and command.status in {
                COMMAND_APPLIED,
                COMMAND_FAILED,
                COMMAND_CANCELLED,
            }:
                return command
        await asyncio.sleep(0.1)
    factory = get_session_factory()
    async with factory() as session:
        return await session.get(FlowCommand, command_id)


async def _apply_domain(session: AsyncSession, command: FlowCommand) -> tuple[FlowInstance, FlowTask | None]:
    payload = _payload(command)
    claims = _claims(command)
    actor = str(payload.get("handler") or command.actor)
    command_type = command.command_type

    if command_type in (COMMAND_APPROVE, COMMAND_REJECT):
        instance = await runtime.handle_task(
            session,
            int(payload["task_id"]),
            handler=actor,
            message=str(payload.get("message") or ""),
            skip_type=str(payload.get("skip_type") or ("REJECT" if command_type == COMMAND_REJECT else "PASS")),
            node_code=payload.get("node_code"),
            variables=payload.get("variables") or {},
            cooperate_type=payload.get("cooperate_type"),
            ignore=bool(payload.get("ignore")),
            ignore_cooperate=bool(payload.get("ignore_cooperate")),
            flow_status=payload.get("flow_status"),
            his_status=payload.get("his_status"),
            claims=claims,
            commit=False,
        )
        return instance, None
    if command_type == COMMAND_RETURN:
        instance = await runtime.return_to_applicant(
            session,
            int(payload["task_id"]),
            handler=actor,
            message=str(payload.get("message") or ""),
            variables=payload.get("variables") or {},
            claims=claims,
            commit=False,
        )
        return instance, None
    if command_type == COMMAND_REJECT_LAST:
        instance = await runtime.reject_last(
            session,
            int(payload["task_id"]),
            handler=actor,
            message=str(payload.get("message") or ""),
            claims=claims,
            commit=False,
        )
        return instance, None
    if command_type == COMMAND_REVOKE:
        instance = await runtime.revoke_instance(
            session,
            command.instance_id,
            handler=actor,
            message=str(payload.get("message") or ""),
            flow_status=payload.get("flow_status"),
            ignore=bool(payload.get("ignore")),
            commit=False,
        )
        return instance, None
    if command_type == COMMAND_TERMINATE:
        instance = await runtime.terminate_instance(
            session,
            command.instance_id,
            handler=actor,
            message=str(payload.get("message") or ""),
            flow_status=payload.get("flow_status"),
            commit=False,
        )
        return instance, None
    if command_type == COMMAND_TRANSFER:
        task = await runtime.transfer_task(
            session,
            int(payload["task_id"]),
            handler=actor,
            add_handlers=[str(item) for item in payload.get("add_handlers") or []],
            message=str(payload.get("message") or ""),
            claims=claims,
            commit=False,
        )
        return await runtime.get_instance(session, task.instance_id), task
    if command_type == COMMAND_DEPUTE:
        task = await runtime.depute_task(
            session,
            int(payload["task_id"]),
            handler=actor,
            add_handlers=[str(item) for item in payload.get("add_handlers") or []],
            message=str(payload.get("message") or ""),
            claims=claims,
            commit=False,
        )
        return await runtime.get_instance(session, task.instance_id), task
    if command_type == COMMAND_ADD_SIGNATURE:
        task = await runtime.add_signature(
            session,
            int(payload["task_id"]),
            handler=actor,
            add_handlers=[str(item) for item in payload.get("add_handlers") or []],
            claims=claims,
            commit=False,
        )
        return await runtime.get_instance(session, task.instance_id), task
    if command_type == COMMAND_REDUCE_SIGNATURE:
        task = await runtime.reduce_signature(
            session,
            int(payload["task_id"]),
            handler=actor,
            reduce_handlers=[str(item) for item in payload.get("reduce_handlers") or []],
            claims=claims,
            commit=False,
        )
        return await runtime.get_instance(session, task.instance_id), task
    raise WorkflowError(f"未知工作流命令：{command_type}")


async def apply_command(session: AsyncSession, command_id: int) -> FlowCommand:
    """Apply one command idempotently in a single database transaction."""

    command = await session.get(FlowCommand, command_id)
    if command is None:
        raise NotFoundError("工作流命令不存在")
    if command.status in (COMMAND_APPLIED, COMMAND_FAILED, COMMAND_CANCELLED):
        return command
    if command.command_type == COMMAND_START:
        command.status = COMMAND_APPLIED
        command.applied_at = command.applied_at or utcnow()
        await session.commit()
        return command

    try:
        instance, task = await _apply_domain(session, command)
        await session.flush()
        now = utcnow()
        command.status = COMMAND_APPLIED
        command.applied_at = now
        command.error_code = None
        command.last_error = None
        terminal = instance.flow_status in TERMINAL_FLOW_STATUSES
        command.result = to_json(
            {
                "instance_id": instance.id,
                "task_id": task.id if task is not None else command.task_id,
                "flow_status": instance.flow_status,
                "node_code": instance.node_code,
                "terminal": terminal,
            }
        )
        if terminal:
            runtime = await session.get(FlowInstanceRuntime, instance.id)
            if runtime is not None:
                runtime.status = "COMPLETED"
                runtime.completed_at = now
                runtime.last_sync_at = now
                runtime.last_error = None
        await _add_outbox_event(session, instance, command, _event_type(command.command_type, instance))
        await session.commit()
        return command
    except WorkflowError as exc:
        await session.rollback()
        failed = await session.get(FlowCommand, command_id)
        if failed is None:
            raise
        failed.status = COMMAND_FAILED
        failed.error_code = exc.status_code
        failed.last_error = exc.message[:2000]
        failed.applied_at = None
        failed.update_time = utcnow()
        failed.update_by = "system"
        await session.commit()
        logger.info("command %s failed: %s", command_id, exc.message)
        return failed


async def submit_command(
    session: AsyncSession,
    *,
    command_type: str,
    instance_id: int,
    task_id: int | None,
    actor: str,
    payload: dict[str, Any],
    claims: list[str] | None = None,
    idempotency_key: str | None = None,
) -> FlowCommand:
    command = await create_command(
        session,
        command_type=command_type,
        instance_id=instance_id,
        task_id=task_id,
        actor=actor,
        payload=payload,
        claims=claims,
        idempotency_key=idempotency_key,
    )
    if command.status in (COMMAND_APPLIED, COMMAND_FAILED, COMMAND_CANCELLED):
        return command
    if not settings.temporal_enabled:
        return await apply_command(session, command.id)

    # Fast path: signal immediately. The background dispatcher retries if this
    # process dies before the signal is delivered.
    try:
        from ..temporal import dispatcher

        await dispatcher.dispatch_command(command.id)
    except Exception:  # noqa: BLE001 - durable command row is the fallback
        logger.exception("immediate dispatch failed for command %s", command.id)
    confirmed = await wait_for_command(command.id)
    return confirmed or command


async def mark_runtime_running(
    session: AsyncSession,
    instance_id: int,
    *,
    run_id: str | None,
) -> None:
    row = await session.get(FlowInstanceRuntime, instance_id)
    if row is None:
        instance = await session.get(FlowInstance, instance_id)
        if instance is None:
            return
        row = FlowInstanceRuntime(
            instance_id=instance_id,
            workflow_id=workflow_id_for(instance_id),
            engine="temporal",
            status="RUNNING",
            tenant_id=instance.tenant_id,
            create_time=utcnow(),
            create_by="system",
            update_time=utcnow(),
            update_by="system",
        )
        session.add(row)
    row.run_id = run_id or row.run_id
    row.status = "RUNNING"
    row.last_sync_at = utcnow()
    row.last_error = None
    await session.commit()


async def mark_runtime_completed(
    session: AsyncSession,
    instance_id: int,
    *,
    status: str = "COMPLETED",
    error: str | None = None,
) -> None:
    row = await session.get(FlowInstanceRuntime, instance_id)
    if row is None:
        return
    row.status = status
    row.completed_at = utcnow() if status in {"COMPLETED", "FAILED"} else row.completed_at
    row.last_sync_at = utcnow()
    row.last_error = error
    await session.commit()


def command_result(command: FlowCommand) -> dict[str, Any]:
    result = _result(command)
    return {
        "id": command.id,
        "instance_id": command.instance_id,
        "task_id": command.task_id,
        "command_type": command.command_type,
        "status": command.status,
        "flow_status": result.get("flow_status"),
        "node_code": result.get("node_code"),
        "terminal": bool(result.get("terminal")),
        "error": command.last_error,
        "error_code": command.error_code,
    }


def status_age_seconds(value: datetime | None) -> float:
    if value is None:
        return 0.0
    now = utcnow()
    if value.tzinfo is None:
        value = value.replace(tzinfo=now.tzinfo)
    return max(0.0, (now - value).total_seconds())
