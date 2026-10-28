"""Form definition CRUD."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import RequestContext, get_context
from ..engine.errors import ConflictError, NotFoundError
from ..engine.serializers import form_out
from ..models import FlowDefinition, FlowForm
from ..schemas import FormCreate, FormUpdate
from ..utils import next_id, utcnow

router = APIRouter(prefix="/forms", tags=["workflow-forms"])

Db = Annotated[AsyncSession, Depends(get_db)]
Ctx = Annotated[RequestContext, Depends(get_context)]


async def _next_version(db: AsyncSession, form_code: str) -> str:
    versions = list(
        (await db.execute(select(FlowForm.version).where(FlowForm.form_code == form_code, FlowForm.del_flag == "0")))
        .scalars()
        .all()
    )
    highest = 0
    for version in versions:
        try:
            highest = max(highest, int(version))
        except (TypeError, ValueError):
            continue
    return str(highest + 1)


async def _get(db: AsyncSession, form_id: int) -> FlowForm:
    form = await db.get(FlowForm, form_id)
    if form is None or form.del_flag != "0":
        raise NotFoundError("表单不存在")
    return form


@router.get("")
async def list_forms(
    db: Db,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    form_code: str | None = Query(None, alias="formCode"),
    form_name: str | None = Query(None, alias="formName"),
    is_publish: int | None = Query(None, alias="isPublish"),
) -> dict[str, Any]:
    stmt = select(FlowForm).where(FlowForm.del_flag == "0")
    if form_code:
        stmt = stmt.where(FlowForm.form_code.like(f"%{form_code}%"))
    if form_name:
        stmt = stmt.where(FlowForm.form_name.like(f"%{form_name}%"))
    if is_publish is not None:
        stmt = stmt.where(FlowForm.is_publish == is_publish)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = list(
        (await db.execute(stmt.order_by(FlowForm.create_time.desc()).offset((page - 1) * size).limit(size)))
        .scalars()
        .all()
    )
    return {"items": [form_out(form) for form in rows], "total": total, "page": page, "size": size}


@router.post("", status_code=201)
async def create_form(body: FormCreate, db: Db, ctx: Ctx) -> dict[str, Any]:
    version = await _next_version(db, body.form_code)
    now = utcnow()
    form = FlowForm(
        id=next_id(),
        form_code=body.form_code,
        form_name=body.form_name,
        version=version,
        is_publish=0,
        form_type=body.form_type,
        form_content=body.form_content,
        form_path=body.form_path or f"{body.form_code}:{version}",
        ext=body.ext,
        create_time=now,
        create_by=ctx.handler,
        update_time=now,
        update_by=ctx.handler,
        tenant_id=ctx.tenant_id,
    )
    db.add(form)
    await db.commit()
    await db.refresh(form)
    return form_out(form)


@router.get("/{form_id}")
async def get_form(form_id: int, db: Db) -> dict[str, Any]:
    return form_out(await _get(db, form_id))


@router.put("/{form_id}")
async def update_form(form_id: int, body: FormUpdate, db: Db, ctx: Ctx) -> dict[str, Any]:
    form = await _get(db, form_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(form, field, value)
    form.update_time = utcnow()
    form.update_by = ctx.handler
    await db.commit()
    await db.refresh(form)
    return form_out(form)


@router.delete("/{form_id}", status_code=204)
async def delete_form(form_id: int, db: Db) -> None:
    form = await _get(db, form_id)
    if form.is_publish == 1:
        used = (
            await db.execute(
                select(func.count())
                .select_from(FlowDefinition)
                .where(
                    FlowDefinition.form_path == form.form_path,
                    FlowDefinition.del_flag == "0",
                    FlowDefinition.is_publish == 1,
                )
            )
        ).scalar_one()
        if used:
            raise ConflictError("表单已被已发布的流程引用，禁止删除")
    form.del_flag = "1"
    form.update_time = utcnow()
    await db.commit()


@router.post("/{form_id}/publish")
async def publish_form(form_id: int, db: Db, ctx: Ctx) -> dict[str, Any]:
    form = await _get(db, form_id)
    old = list(
        (
            await db.execute(
                select(FlowForm).where(
                    FlowForm.form_code == form.form_code,
                    FlowForm.id != form.id,
                    FlowForm.is_publish == 1,
                    FlowForm.del_flag == "0",
                )
            )
        )
        .scalars()
        .all()
    )
    for item in old:
        item.is_publish = 9
        item.update_time = utcnow()
        item.update_by = ctx.handler
    form.is_publish = 1
    form.update_time = utcnow()
    form.update_by = ctx.handler
    await db.commit()
    await db.refresh(form)
    return form_out(form)
