"""ABAC policy CRUD endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.auth.models import Policy
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/api/policies", tags=["policies"])


class PolicyCreate(BaseModel):
    name: str = Field(..., max_length=200)
    priority: int = 0
    conditions: dict = {}
    grants: dict = {}


class PolicyUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    enabled: bool | None = None
    priority: int | None = None
    conditions: dict | None = None
    grants: dict | None = None


@router.get("")
async def list_policies(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:read")),
):
    result = await db.execute(select(Policy).order_by(Policy.priority))
    policies = result.scalars().all()
    return {
        "policies": [
            {
                "id": str(p.id),
                "name": p.name,
                "enabled": p.enabled,
                "priority": p.priority,
                "conditions": p.conditions,
                "grants": p.grants,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in policies
        ]
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_policy(
    data: PolicyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:create")),
):
    policy = Policy(
        name=data.name,
        priority=data.priority,
        conditions=data.conditions,
        grants=data.grants,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    # EAI-CUSTOM: 返回完整策略行（前端 createPolicy 直接推入列表并渲染 conditions/grants，仅返回 id/name 会令 PolicyRow 读 undefined 崩溃）
    return {
        "id": str(policy.id),
        "name": policy.name,
        "enabled": policy.enabled,
        "priority": policy.priority,
        "conditions": policy.conditions,
        "grants": policy.grants,
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
    }


@router.put("/{policy_id}")
async def update_policy(
    policy_id: UUID,
    data: PolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:update")),
):
    policy = await db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if data.name is not None:
        policy.name = data.name
    if data.enabled is not None:
        policy.enabled = data.enabled
    if data.priority is not None:
        policy.priority = data.priority
    if data.conditions is not None:
        policy.conditions = data.conditions
    if data.grants is not None:
        policy.grants = data.grants
    await db.commit()
    return {"id": str(policy.id), "name": policy.name}


@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:delete")),
):
    policy = await db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    await db.delete(policy)
    await db.commit()
    return {"message": "Policy deleted"}
