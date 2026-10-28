"""Runtime endpoints: instances, tasks, approvals and history."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import RequestContext, get_context
from ..engine import commands as command_service
from ..engine import definition as definition_service
from ..engine import runtime
from ..engine.chart import build_chart
from ..engine.enums import FLOW_STATUS_LABELS
from ..engine.serializers import (
    build_def_json,
    his_out,
    instance_out,
    snapshot_flow_name,
    snapshot_node,
    task_out,
)
from ..models import FlowDefinition, FlowInstance, FlowTask
from ..schemas import HandlerActionRequest, HandleTaskRequest, RevokeRequest, StartInstanceRequest

router = APIRouter(tags=["workflow-runtime"])

Db = Annotated[AsyncSession, Depends(get_db)]
Ctx = Annotated[RequestContext, Depends(get_context)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]

logger = logging.getLogger("workflow.api.runtime")


def _actor(requested: str | None, ctx: RequestContext) -> str:
    if requested and requested not in ("", "system"):
        return requested
    return ctx.handler


async def _instance_projection(
    db: AsyncSession,
    instance_id: int,
    command: Any,
) -> dict[str, Any]:
    command_service.raise_for_command(command)
    # The worker committed in another session. Drop this request's snapshot
    # before reloading the read model.
    await db.rollback()
    detail = await runtime.instance_detail(db, instance_id)
    return detail["instance"]


async def _task_projection(db: AsyncSession, task_id: int, command: Any) -> dict[str, Any]:
    command_service.raise_for_command(command)
    await db.rollback()
    return task_out(await runtime.get_task(db, task_id))


@router.post("/instances", status_code=201)
async def start_instance(
    body: StartInstanceRequest,
    db: Db,
    ctx: Ctx,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    instance, _ = await command_service.start_instance_command(
        db,
        flow_code=body.flow_code,
        business_id=body.business_id,
        handler=_actor(body.handler, ctx),
        variables=body.variables,
        flow_status=body.flow_status,
        ext=body.ext,
        tenant_id=ctx.tenant_id,
        idempotency_key=idempotency_key,
    )
    instance_id = instance.id
    if settings.temporal_enabled:
        try:
            from ..temporal import dispatcher

            await dispatcher.ensure_workflow_started(instance_id)
        except Exception:  # noqa: BLE001 - STARTING row is reconciled later
            logger.warning("workflow start deferred for instance %s", instance_id, exc_info=True)
    await db.rollback()
    detail = await runtime.instance_detail(db, instance_id)
    return detail["instance"]


@router.get("/instances")
async def list_instances(
    db: Db,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    definition_id: int | None = Query(None, alias="definitionId"),
    business_id: str | None = Query(None, alias="businessId"),
    flow_status: str | None = Query(None, alias="flowStatus"),
    handler: str | None = None,
    ctx: Ctx = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    stmt = (
        select(FlowInstance, FlowDefinition.flow_name)
        .join(FlowDefinition, FlowDefinition.id == FlowInstance.definition_id)
        .where(FlowInstance.del_flag == "0")
    )
    if definition_id:
        stmt = stmt.where(FlowInstance.definition_id == definition_id)
    if business_id:
        stmt = stmt.where(FlowInstance.business_id.like(f"%{business_id}%"))
    if flow_status:
        stmt = stmt.where(FlowInstance.flow_status == flow_status)
    if handler:
        stmt = stmt.where(FlowInstance.create_by == handler)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await db.execute(stmt.order_by(FlowInstance.create_time.desc()).offset((page - 1) * size).limit(size))
    ).all()
    items = []
    for instance, flow_name in rows:
        item = instance_out(instance, flow_name=flow_name)
        item.pop("def_json", None)
        items.append(item)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/instances/{instance_id}")
async def get_instance(instance_id: int, db: Db) -> dict[str, Any]:
    return await runtime.instance_detail(db, instance_id)


@router.post("/instances/{instance_id}/revoke")
async def revoke(
    instance_id: int,
    db: Db,
    ctx: Ctx,
    body: RevokeRequest | None = None,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    payload = {
        "handler": _actor(body.handler if body else None, ctx),
        "message": body.message if body else "",
        "flow_status": body.flow_status if body else None,
        "ignore": ctx.handler == "system",
    }
    command = await command_service.submit_command(
        db,
        command_type=command_service.COMMAND_REVOKE,
        instance_id=instance_id,
        task_id=None,
        actor=ctx.handler,
        payload=payload,
        claims=ctx.claims,
        idempotency_key=idempotency_key,
    )
    return await _instance_projection(db, instance_id, command)


@router.post("/instances/{instance_id}/terminate")
async def terminate(
    instance_id: int,
    db: Db,
    ctx: Ctx,
    body: RevokeRequest | None = None,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    payload = {
        "handler": _actor(body.handler if body else None, ctx),
        "message": body.message if body else "",
        "flow_status": body.flow_status if body else None,
    }
    command = await command_service.submit_command(
        db,
        command_type=command_service.COMMAND_TERMINATE,
        instance_id=instance_id,
        task_id=None,
        actor=ctx.handler,
        payload=payload,
        claims=ctx.claims,
        idempotency_key=idempotency_key,
    )
    return await _instance_projection(db, instance_id, command)


@router.get("/tasks")
async def list_tasks(
    db: Db,
    assignee: str | None = None,
    instance_id: int | None = Query(None, alias="instanceId"),
    node_code: str | None = Query(None, alias="nodeCode"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    ctx: Ctx = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    handler = assignee or ctx.handler
    items = await runtime.list_tasks(
        db, handler=handler, instance_id=instance_id, node_code=node_code, claims=ctx.claims
    )
    total = len(items)
    return {"items": items[(page - 1) * size : page * size], "total": total, "page": page, "size": size}


async def _task_detail(db: AsyncSession, task: FlowTask) -> dict[str, Any]:
    instance = await runtime.get_instance(db, task.instance_id)
    definition = await definition_service.get_definition(db, task.definition_id)
    flow_name = snapshot_flow_name(instance, definition.flow_name)
    users = await runtime.task_users(db, task.id)
    detail = task_out(task, flow_name=flow_name, business_id=instance.business_id)
    detail["assignees"] = [user.processed_by for user in users]
    node = snapshot_node(instance, task.node_code)
    if node is None:
        # Legacy instances created before formSnapshot/definition snapshots.
        definition_json = await build_def_json(db, definition, instance=instance)
        node = next(
            (item for item in definition_json["nodeList"] if item["nodeCode"] == task.node_code),
            None,
        )
    detail["node"] = node
    detail["instance"] = instance_out(instance, flow_name=flow_name)
    detail["chart"] = await build_chart(db, instance)
    detail["variables"] = detail["instance"].get("variable") or {}
    detail["form"] = node if node else None
    return detail


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, db: Db) -> dict[str, Any]:
    task = await runtime.get_task(db, task_id)
    return await _task_detail(db, task)


async def _submit_task_command(
    db: AsyncSession,
    ctx: RequestContext,
    *,
    task_id: int,
    command_type: str,
    body: HandleTaskRequest,
    idempotency_key: str | None,
) -> tuple[int, Any]:
    payload = {
        "task_id": task_id,
        "handler": _actor(body.handler, ctx),
        "message": body.message,
        "skip_type": "REJECT"
        if command_type in (command_service.COMMAND_REJECT, command_service.COMMAND_RETURN)
        else "PASS",
        "node_code": body.node_code,
        "variables": body.variables,
        "cooperate_type": body.cooperate_type,
        "ignore": body.ignore,
        "ignore_cooperate": body.ignore_cooperate,
        "flow_status": body.flow_status,
        "his_status": body.his_status,
    }
    existing = await command_service.find_by_idempotency_key(db, idempotency_key)
    if existing is not None:
        instance_id = existing.instance_id
    else:
        instance_id = (await runtime.get_task(db, task_id)).instance_id
    command = await command_service.submit_command(
        db,
        command_type=command_type,
        instance_id=instance_id,
        task_id=task_id,
        actor=ctx.handler,
        payload=payload,
        claims=ctx.claims,
        idempotency_key=idempotency_key,
    )
    return instance_id, command


@router.post("/tasks/{task_id}/approve")
async def approve(
    task_id: int,
    db: Db,
    ctx: Ctx,
    body: HandleTaskRequest | None = None,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    body = body or HandleTaskRequest()
    instance_id, command = await _submit_task_command(
        db,
        ctx,
        task_id=task_id,
        command_type=command_service.COMMAND_APPROVE,
        body=body,
        idempotency_key=idempotency_key,
    )
    return await _instance_projection(db, instance_id, command)


@router.post("/tasks/{task_id}/reject")
async def reject(
    task_id: int,
    db: Db,
    ctx: Ctx,
    body: HandleTaskRequest | None = None,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    body = body or HandleTaskRequest()
    instance_id, command = await _submit_task_command(
        db,
        ctx,
        task_id=task_id,
        command_type=command_service.COMMAND_REJECT,
        body=body,
        idempotency_key=idempotency_key,
    )
    return await _instance_projection(db, instance_id, command)


@router.post("/tasks/{task_id}/return-to-applicant")
async def return_to_applicant(
    task_id: int,
    db: Db,
    ctx: Ctx,
    body: HandleTaskRequest | None = None,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    body = body or HandleTaskRequest()
    instance_id, command = await _submit_task_command(
        db,
        ctx,
        task_id=task_id,
        command_type=command_service.COMMAND_RETURN,
        body=body,
        idempotency_key=idempotency_key,
    )
    return await _instance_projection(db, instance_id, command)


@router.post("/tasks/{task_id}/reject-last")
async def reject_last(
    task_id: int,
    db: Db,
    ctx: Ctx,
    body: HandleTaskRequest | None = None,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    body = body or HandleTaskRequest()
    instance_id, command = await _submit_task_command(
        db,
        ctx,
        task_id=task_id,
        command_type=command_service.COMMAND_REJECT_LAST,
        body=body,
        idempotency_key=idempotency_key,
    )
    return await _instance_projection(db, instance_id, command)


async def _submit_handler_command(
    db: AsyncSession,
    ctx: RequestContext,
    *,
    task_id: int,
    command_type: str,
    body: HandlerActionRequest,
    idempotency_key: str | None,
) -> Any:
    payload = {
        "task_id": task_id,
        "handler": _actor(body.handler, ctx),
        "add_handlers": body.add_handlers,
        "reduce_handlers": body.reduce_handlers,
        "message": body.message,
    }
    existing = await command_service.find_by_idempotency_key(db, idempotency_key)
    if existing is not None:
        instance_id = existing.instance_id
    else:
        instance_id = (await runtime.get_task(db, task_id)).instance_id
    return await command_service.submit_command(
        db,
        command_type=command_type,
        instance_id=instance_id,
        task_id=task_id,
        actor=ctx.handler,
        payload=payload,
        claims=ctx.claims,
        idempotency_key=idempotency_key,
    )


@router.post("/tasks/{task_id}/transfer")
async def transfer(
    task_id: int,
    body: HandlerActionRequest,
    db: Db,
    ctx: Ctx,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = await _submit_handler_command(
        db,
        ctx,
        task_id=task_id,
        command_type=command_service.COMMAND_TRANSFER,
        body=body,
        idempotency_key=idempotency_key,
    )
    return await _task_projection(db, task_id, command)


@router.post("/tasks/{task_id}/depute")
async def depute(
    task_id: int,
    body: HandlerActionRequest,
    db: Db,
    ctx: Ctx,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = await _submit_handler_command(
        db,
        ctx,
        task_id=task_id,
        command_type=command_service.COMMAND_DEPUTE,
        body=body,
        idempotency_key=idempotency_key,
    )
    return await _task_projection(db, task_id, command)


@router.post("/tasks/{task_id}/add-signature")
async def add_signature(
    task_id: int,
    body: HandlerActionRequest,
    db: Db,
    ctx: Ctx,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = await _submit_handler_command(
        db,
        ctx,
        task_id=task_id,
        command_type=command_service.COMMAND_ADD_SIGNATURE,
        body=body,
        idempotency_key=idempotency_key,
    )
    return await _task_projection(db, task_id, command)


@router.post("/tasks/{task_id}/reduce-signature")
async def reduce_signature(
    task_id: int,
    body: HandlerActionRequest,
    db: Db,
    ctx: Ctx,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    command = await _submit_handler_command(
        db,
        ctx,
        task_id=task_id,
        command_type=command_service.COMMAND_REDUCE_SIGNATURE,
        body=body,
        idempotency_key=idempotency_key,
    )
    return await _task_projection(db, task_id, command)


@router.get("/history")
async def list_history(
    db: Db,
    instance_id: int | None = Query(None, alias="instanceId"),
    handler: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    ctx: Ctx = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    rows = await runtime.list_history(db, handler=handler or None, instance_id=instance_id)
    total = len(rows)
    rows = rows[(page - 1) * size : page * size]
    items = []
    for his in rows:
        definition = await db.get(FlowDefinition, his.definition_id)
        item = his_out(his)
        item["flow_name"] = definition.flow_name if definition else None
        items.append(item)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/status-labels")
async def status_labels() -> dict[str, str]:
    return FLOW_STATUS_LABELS
