"""Definition management endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import RequestContext, get_context
from ..engine import definition as service
from ..engine.serializers import definition_out
from ..models import FlowDefinition, FlowInstance
from ..schemas import DefinitionCreate, DefinitionUpdate

router = APIRouter(prefix="/definitions", tags=["workflow-definitions"])

Db = Annotated[AsyncSession, Depends(get_db)]
Ctx = Annotated[RequestContext, Depends(get_context)]


@router.get("")
async def list_definitions(
    db: Db,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    flow_code: str | None = Query(None, alias="flowCode"),
    flow_name: str | None = Query(None, alias="flowName"),
    category: str | None = None,
    is_publish: int | None = Query(None, alias="isPublish"),
    ctx: Ctx = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    stmt = select(FlowDefinition).where(
        FlowDefinition.del_flag == "0",
        FlowDefinition.tenant_id == ctx.tenant_id,
    )
    if flow_code:
        stmt = stmt.where(FlowDefinition.flow_code.like(f"%{flow_code}%"))
    if flow_name:
        stmt = stmt.where(FlowDefinition.flow_name.like(f"%{flow_name}%"))
    if category:
        stmt = stmt.where(FlowDefinition.category == category)
    if is_publish is not None:
        stmt = stmt.where(FlowDefinition.is_publish == is_publish)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = list(
        (await db.execute(stmt.order_by(FlowDefinition.create_time.desc()).offset((page - 1) * size).limit(size)))
        .scalars()
        .all()
    )
    counts = {}
    if rows:
        count_rows = (
            await db.execute(
                select(FlowInstance.definition_id, func.count())
                .where(FlowInstance.definition_id.in_([row.id for row in rows]))
                .group_by(FlowInstance.definition_id)
            )
        ).all()
        counts = {definition_id: count for definition_id, count in count_rows}

    items = []
    for row in rows:
        item = definition_out(row)
        item["instance_count"] = counts.get(row.id, 0)
        items.append(item)
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("", status_code=201)
async def create_definition(body: DefinitionCreate, db: Db, ctx: Ctx) -> dict[str, Any]:
    definition = await service.create_definition(
        db,
        flow_code=body.flow_code,
        flow_name=body.flow_name,
        category=body.category,
        form_custom=body.form_custom,
        form_path=body.form_path,
        listener_type=body.listener_type,
        listener_path=body.listener_path,
        ext=body.ext,
        actor=ctx.handler,
        tenant_id=ctx.tenant_id,
    )
    return definition_out(definition)


@router.get("/{definition_id}")
async def get_definition(definition_id: int, db: Db) -> dict[str, Any]:
    definition = await service.get_definition(db, definition_id)
    return definition_out(definition)


@router.put("/{definition_id}")
async def update_definition(definition_id: int, body: DefinitionUpdate, db: Db, ctx: Ctx) -> dict[str, Any]:
    values = body.model_dump(exclude_unset=True)
    definition = await service.update_definition(db, definition_id, values, actor=ctx.handler)
    return definition_out(definition)


@router.delete("/{definition_id}", status_code=204)
async def delete_definition(definition_id: int, db: Db) -> None:
    await service.delete_definition(db, definition_id)


@router.post("/{definition_id}/publish")
async def publish(definition_id: int, db: Db, ctx: Ctx) -> dict[str, Any]:
    definition = await service.publish_definition(db, definition_id, actor=ctx.handler)
    return definition_out(definition)


@router.post("/{definition_id}/unpublish")
async def unpublish(definition_id: int, db: Db, ctx: Ctx) -> dict[str, Any]:
    definition = await service.unpublish_definition(db, definition_id, actor=ctx.handler)
    return definition_out(definition)


@router.post("/{definition_id}/copy", status_code=201)
async def copy(definition_id: int, db: Db, ctx: Ctx) -> dict[str, Any]:
    definition = await service.copy_definition(db, definition_id, actor=ctx.handler)
    return definition_out(definition)


@router.post("/{definition_id}/activate")
async def activate(definition_id: int, db: Db, ctx: Ctx) -> dict[str, Any]:
    definition = await service.set_activity(db, definition_id, True, actor=ctx.handler)
    return definition_out(definition)


@router.post("/{definition_id}/suspend")
async def suspend(definition_id: int, db: Db, ctx: Ctx) -> dict[str, Any]:
    definition = await service.set_activity(db, definition_id, False, actor=ctx.handler)
    return definition_out(definition)


@router.get("/{definition_id}/export")
async def export_json(definition_id: int, db: Db) -> dict[str, Any]:
    return await service.export_def_json(db, definition_id)


@router.post("/import", status_code=201)
async def import_json(body: dict[str, Any], db: Db, ctx: Ctx) -> dict[str, Any]:
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else body
    definition = await service.import_def_json(db, payload, actor=ctx.handler, tenant_id=ctx.tenant_id)
    return definition_out(definition)
