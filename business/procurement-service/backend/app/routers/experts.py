"""评标专家 API 路由"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Expert, ExpertDraw, ExpertReview
from app.schemas import (
    ExpertCreate,
    ExpertDrawCreate,
    ExpertDrawListResponse,
    ExpertDrawResponse,
    ExpertListResponse,
    ExpertResponse,
    ExpertReviewCreate,
    ExpertReviewResponse,
    ExpertUpdate,
    MessageResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/experts", tags=["评标专家管理"])


@router.get("", response_model=ExpertListResponse)
async def list_experts(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    expertise: Optional[str] = None,
    region: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """查询评标专家列表"""
    stmt = select(Expert)
    if keyword:
        stmt = stmt.where(Expert.name.ilike(f"%{keyword}%"))
    if expertise:
        stmt = stmt.where(Expert.expertise.ilike(f"%{expertise}%"))
    if region:
        stmt = stmt.where(Expert.region == region)
    if is_active is not None:
        stmt = stmt.where(Expert.is_active == is_active)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.order_by(Expert.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    experts = list(result.scalars().all())

    return ExpertListResponse(
        experts=[ExpertResponse.model_validate(e) for e in experts],
        total=total,
    )


@router.post("", response_model=ExpertResponse, status_code=status.HTTP_201_CREATED)
async def create_expert(
    data: ExpertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """创建评标专家"""
    expert = Expert(**data.model_dump())
    db.add(expert)
    await db.commit()
    await db.refresh(expert)
    return ExpertResponse.model_validate(expert)


@router.get("/{expert_id}", response_model=ExpertResponse)
async def get_expert(
    expert_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """获取专家详情"""
    stmt = select(Expert).where(Expert.id == expert_id)
    result = await db.execute(stmt)
    expert = result.scalar_one_or_none()
    if not expert:
        raise HTTPException(status_code=404, detail="专家不存在")
    return ExpertResponse.model_validate(expert)


@router.put("/{expert_id}", response_model=ExpertResponse)
async def update_expert(
    expert_id: UUID,
    data: ExpertUpdate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """更新专家信息"""
    stmt = select(Expert).where(Expert.id == expert_id)
    result = await db.execute(stmt)
    expert = result.scalar_one_or_none()
    if not expert:
        raise HTTPException(status_code=404, detail="专家不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(expert, field, value)
    await db.commit()
    await db.refresh(expert)
    return ExpertResponse.model_validate(expert)


@router.delete("/{expert_id}", response_model=MessageResponse)
async def delete_expert(
    expert_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """删除专家"""
    stmt = select(Expert).where(Expert.id == expert_id)
    result = await db.execute(stmt)
    expert = result.scalar_one_or_none()
    if not expert:
        raise HTTPException(status_code=404, detail="专家不存在")
    await db.delete(expert)
    await db.commit()
    return MessageResponse(message="专家删除成功")


@router.post("/batch", response_model=ExpertListResponse, status_code=status.HTTP_201_CREATED)
async def batch_import_experts(
    experts_data: list[ExpertCreate],
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """批量导入专家"""
    experts = [Expert(**e.model_dump()) for e in experts_data]
    db.add_all(experts)
    await db.commit()
    for e in experts:
        await db.refresh(e)
    return ExpertListResponse(
        experts=[ExpertResponse.model_validate(e) for e in experts],
        total=len(experts),
    )


@router.post("/draws", response_model=ExpertDrawResponse, status_code=status.HTTP_201_CREATED)
async def draw_experts(
    data: ExpertDrawCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """抽取评标专家"""
    expert_stmt = select(Expert).where(Expert.is_active == True).order_by(func.random()).limit(data.required_count)
    result = await db.execute(expert_stmt)
    selected = list(result.scalars().all())

    if len(selected) < data.required_count:
        raise HTTPException(
            status_code=400,
            detail=f"可用专家数量不足，需要 {data.required_count} 人，当前仅 {len(selected)} 人",
        )

    draw = ExpertDraw(
        project_id=data.project_id,
        drawn_expert_ids=[e.id for e in selected],
        required_count=data.required_count,
        draw_method=data.draw_method,
        operator_id=current_user.sub,
    )
    db.add(draw)
    await db.commit()
    await db.refresh(draw)
    return ExpertDrawResponse.model_validate(draw)


@router.get("/draws", response_model=ExpertDrawListResponse)
async def list_expert_draws(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    project_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """查询专家抽取记录"""
    stmt = select(ExpertDraw)
    if project_id:
        stmt = stmt.where(ExpertDraw.project_id == project_id)
    stmt = stmt.order_by(ExpertDraw.drawn_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    draws = list(result.scalars().all())
    return ExpertDrawListResponse(
        draws=[ExpertDrawResponse.model_validate(d) for d in draws],
        total=len(draws),
    )


@router.post("/reviews", response_model=ExpertReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_expert_review(
    data: ExpertReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """评价专家"""
    review = ExpertReview(
        expert_id=data.expert_id,
        project_id=data.project_id,
        bid_id=data.bid_id,
        punctuality_score=data.punctuality_score,
        professional_score=data.professional_score,
        fairness_score=data.fairness_score,
        comment=data.comment,
        reviewer_id=current_user.sub,
    )
    db.add(review)

    if all(x is not None for x in [data.punctuality_score, data.professional_score, data.fairness_score]):
        avg_score = (data.punctuality_score + data.professional_score + data.fairness_score) / 3
        stmt = select(Expert).where(Expert.id == data.expert_id)
        result = await db.execute(stmt)
        expert = result.scalar_one_or_none()
        if expert:
            new_count = expert.evaluation_count + 1
            if expert.avg_score is None:
                expert.avg_score = float(avg_score)
            else:
                expert.avg_score = (expert.avg_score * expert.evaluation_count + float(avg_score)) / new_count
            expert.evaluation_count = new_count

    await db.commit()
    await db.refresh(review)
    return ExpertReviewResponse.model_validate(review)
