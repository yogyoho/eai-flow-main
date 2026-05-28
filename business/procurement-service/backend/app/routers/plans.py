"""招标计划 API 路由"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import TenderPlan
from app.schemas import (
    MessageResponse,
    TenderPlanCreate,
    TenderPlanListResponse,
    TenderPlanResponse,
    TenderPlanUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/plans", tags=["招标计划管理"])


@router.get("", response_model=TenderPlanListResponse)
async def list_plans(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    procurement_type: Optional[str] = None,
    dept_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """查询招标计划列表"""
    stmt = select(TenderPlan)
    if keyword:
        stmt = stmt.where(TenderPlan.title.ilike(f"%{keyword}%"))
    if status:
        stmt = stmt.where(TenderPlan.status == status)
    if procurement_type:
        stmt = stmt.where(TenderPlan.procurement_type == procurement_type)
    if dept_id:
        stmt = stmt.where(TenderPlan.dept_id == dept_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.order_by(TenderPlan.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    plans = list(result.scalars().all())

    return TenderPlanListResponse(
        plans=[TenderPlanResponse.model_validate(p) for p in plans],
        total=total,
    )


@router.post("", response_model=TenderPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    data: TenderPlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """创建招标计划"""
    plan = TenderPlan(**data.model_dump(), created_by=current_user.sub)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return TenderPlanResponse.model_validate(plan)


@router.get("/{plan_id}", response_model=TenderPlanResponse)
async def get_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """获取计划详情"""
    stmt = select(TenderPlan).where(TenderPlan.id == plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="招标计划不存在")
    return TenderPlanResponse.model_validate(plan)


@router.put("/{plan_id}", response_model=TenderPlanResponse)
async def update_plan(
    plan_id: UUID,
    data: TenderPlanUpdate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """更新招标计划"""
    stmt = select(TenderPlan).where(TenderPlan.id == plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="招标计划不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(plan, field, value)
    await db.commit()
    await db.refresh(plan)
    return TenderPlanResponse.model_validate(plan)


@router.delete("/{plan_id}", response_model=MessageResponse)
async def delete_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """删除招标计划"""
    stmt = select(TenderPlan).where(TenderPlan.id == plan_id)
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="招标计划不存在")
    if plan.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="仅草稿状态的计划可删除")
    await db.delete(plan)
    await db.commit()
    return MessageResponse(message="招标计划删除成功")
