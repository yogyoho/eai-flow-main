"""Metadata, demo directory and dashboard endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..demo import ALL_HANDLERS, DEMO_USERS
from ..deps import RequestContext, get_context
from ..engine.enums import (
    CHART_COLORS,
    COOPERATE_LABELS,
    FLOW_STATUS_LABELS,
    FLOW_STATUS_TONE,
    NODE_TYPE_VALUE,
)
from ..models import FlowDefinition, FlowInstance, FlowTask

router = APIRouter(tags=["workflow-meta"])

Db = Annotated[AsyncSession, Depends(get_db)]
Ctx = Annotated[RequestContext, Depends(get_context)]


@router.get("/meta/enums")
async def enums() -> dict[str, Any]:
    return {
        "nodeTypes": NODE_TYPE_VALUE,
        "flowStatus": FLOW_STATUS_LABELS,
        "flowStatusTone": FLOW_STATUS_TONE,
        "cooperateTypes": COOPERATE_LABELS,
        "chartColors": CHART_COLORS,
        "models": {"CLASSICS": "经典模式"},
        "skipTypes": {"PASS": "通过", "REJECT": "退回", "NONE": "无动作"},
        "publishStatus": {"0": "未发布", "1": "已发布", "9": "已失效"},
    }


@router.get("/meta/me")
async def me(ctx: Ctx) -> dict[str, Any]:
    """Current authenticated principal.

    The frontend uses this to stop presenting the demo identity switcher when
    the platform runs behind EAI authentication.
    """

    return {
        "handler": ctx.handler,
        "name": ctx.name,
        "roles": ctx.roles,
        "permissions": ctx.permissions,
        "dept": ctx.dept or "",
        "tenant_id": ctx.tenant_id,
        "is_admin": ctx.is_admin,
        "auth_mode": settings.auth_mode,
    }


@router.get("/meta/users")
async def users() -> list[dict[str, Any]]:
    return [
        {
            "handler": item["storageId"],
            "name": item["handlerName"],
            "group": item["groupName"],
            "roles": item.get("roles", []),
            "dept": item.get("dept"),
        }
        for item in DEMO_USERS
    ]


@router.get("/meta/handlers")
async def handlers() -> list[dict[str, Any]]:
    return [{key: value for key, value in item.items() if key != "roles"} for item in ALL_HANDLERS]


@router.get("/meta/stats")
async def stats(db: Db, ctx: Ctx) -> dict[str, Any]:
    definition_count = (
        await db.execute(
            select(func.count())
            .select_from(FlowDefinition)
            .where(FlowDefinition.del_flag == "0", FlowDefinition.tenant_id == ctx.tenant_id)
        )
    ).scalar_one()
    published_count = (
        await db.execute(
            select(func.count())
            .select_from(FlowDefinition)
            .where(
                FlowDefinition.del_flag == "0",
                FlowDefinition.tenant_id == ctx.tenant_id,
                FlowDefinition.is_publish == 1,
            )
        )
    ).scalar_one()
    instance_count = (
        await db.execute(select(func.count()).select_from(FlowInstance).where(FlowInstance.del_flag == "0"))
    ).scalar_one()
    running_count = (
        await db.execute(
            select(func.count())
            .select_from(FlowInstance)
            .where(FlowInstance.del_flag == "0", FlowInstance.flow_status.in_(["0", "1", "9"]))
        )
    ).scalar_one()
    task_count = (
        await db.execute(select(func.count()).select_from(FlowTask).where(FlowTask.del_flag == "0"))
    ).scalar_one()
    return {
        "definitions": definition_count,
        "published": published_count,
        "instances": instance_count,
        "running": running_count,
        "tasks": task_count,
    }
