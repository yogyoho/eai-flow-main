"""评标管理 API 路由"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Bid, Evaluation
from app.schemas import (
    EvaluationCreate,
    EvaluationListResponse,
    EvaluationResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/evaluations", tags=["评标管理"])


@router.get("", response_model=EvaluationListResponse)
async def list_evaluations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    project_id: Optional[UUID] = None,
    bid_id: Optional[UUID] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """查询评标记录"""
    stmt = select(Evaluation)
    if project_id:
        stmt = stmt.where(Evaluation.project_id == project_id)
    if bid_id:
        stmt = stmt.where(Evaluation.bid_id == bid_id)
    if status:
        stmt = stmt.where(Evaluation.status == status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.order_by(Evaluation.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    evaluations = list(result.scalars().all())

    return EvaluationListResponse(
        evaluations=[EvaluationResponse.model_validate(e) for e in evaluations],
        total=total,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_evaluation(
    data: EvaluationCreate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """创建评标记录"""
    bid_stmt = select(Bid).where(Bid.id == data.bid_id)
    bid_result = await db.execute(bid_stmt)
    bid = bid_result.scalar_one_or_none()
    if not bid:
        raise HTTPException(status_code=404, detail="投标记录不存在")

    evaluation = Evaluation(**data.model_dump())
    db.add(evaluation)
    await db.commit()
    await db.refresh(evaluation)
    return EvaluationResponse.model_validate(evaluation)


@router.post("/{evaluation_id}/verify")
async def verify_evaluation(
    evaluation_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """核验评标记录"""
    stmt = select(Evaluation).where(Evaluation.id == evaluation_id)
    result = await db.execute(stmt)
    evaluation = result.scalar_one_or_none()
    if not evaluation:
        raise HTTPException(status_code=404, detail="评标记录不存在")

    issues: list[str] = []
    if evaluation.total_score is None:
        issues.append("总分未填写")
    if evaluation.evaluation_details is None:
        issues.append("评分明细未填写")

    passed = len(issues) == 0
    evaluation.verified = passed
    evaluation.verification_comment = "，".join(issues) if issues else "核验通过"
    await db.commit()

    return {"passed": passed, "issues": issues}


@router.post("/{evaluation_id}/complete")
async def complete_evaluation(
    evaluation_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """完成评标"""
    stmt = select(Evaluation).where(Evaluation.id == evaluation_id)
    result = await db.execute(stmt)
    evaluation = result.scalar_one_or_none()
    if not evaluation:
        raise HTTPException(status_code=404, detail="评标记录不存在")

    if not evaluation.verified:
        raise HTTPException(status_code=400, detail="请先完成核验")

    evaluation.status = "completed"
    evaluation.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(evaluation)
    return EvaluationResponse.model_validate(evaluation)
