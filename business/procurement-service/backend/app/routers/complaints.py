"""投诉管理 API 路由"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Complaint
from app.schemas import (
    ComplaintCreate,
    ComplaintListResponse,
    ComplaintResponse,
    ComplaintUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/complaints", tags=["投诉管理"])


@router.get("", response_model=ComplaintListResponse)
async def list_complaints(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    project_id: Optional[UUID] = None,
    status: Optional[str] = None,
    complaint_type: Optional[str] = None,
    priority: Optional[str] = None,
    keyword: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """查询投诉列表"""
    stmt = select(Complaint)
    if project_id:
        stmt = stmt.where(Complaint.project_id == project_id)
    if status:
        stmt = stmt.where(Complaint.status == status)
    if complaint_type:
        stmt = stmt.where(Complaint.complaint_type == complaint_type)
    if priority:
        stmt = stmt.where(Complaint.priority == priority)
    if keyword:
        stmt = stmt.where(Complaint.title.ilike(f"%{keyword}%"))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.order_by(Complaint.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    complaints = list(result.scalars().all())

    return ComplaintListResponse(
        complaints=[ComplaintResponse.model_validate(c) for c in complaints],
        total=total,
    )


@router.post("", response_model=ComplaintResponse, status_code=status.HTTP_201_CREATED)
async def create_complaint(
    data: ComplaintCreate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """提交投诉"""
    import random
    now = datetime.now(timezone.utc)
    complaint_no = f"TS-{now.strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

    complaint = Complaint(**data.model_dump(), complaint_no=complaint_no)
    db.add(complaint)
    await db.commit()
    await db.refresh(complaint)
    return ComplaintResponse.model_validate(complaint)


@router.get("/{complaint_id}", response_model=ComplaintResponse)
async def get_complaint(
    complaint_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """获取投诉详情"""
    stmt = select(Complaint).where(Complaint.id == complaint_id)
    result = await db.execute(stmt)
    complaint = result.scalar_one_or_none()
    if not complaint:
        raise HTTPException(status_code=404, detail="投诉不存在")
    return ComplaintResponse.model_validate(complaint)


@router.put("/{complaint_id}", response_model=ComplaintResponse)
async def update_complaint(
    complaint_id: UUID,
    data: ComplaintUpdate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """更新投诉"""
    stmt = select(Complaint).where(Complaint.id == complaint_id)
    result = await db.execute(stmt)
    complaint = result.scalar_one_or_none()
    if not complaint:
        raise HTTPException(status_code=404, detail="投诉不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(complaint, field, value)
    await db.commit()
    await db.refresh(complaint)
    return ComplaintResponse.model_validate(complaint)


@router.post("/{complaint_id}/reply", response_model=ComplaintResponse)
async def reply_complaint(
    complaint_id: UUID,
    response_content: str,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """答复投诉"""
    stmt = select(Complaint).where(Complaint.id == complaint_id)
    result = await db.execute(stmt)
    complaint = result.scalar_one_or_none()
    if not complaint:
        raise HTTPException(status_code=404, detail="投诉不存在")

    complaint.response_content = response_content
    complaint.responded_by = current_user.sub
    complaint.responded_at = datetime.now(timezone.utc)
    complaint.status = "processing"
    await db.commit()
    await db.refresh(complaint)
    return ComplaintResponse.model_validate(complaint)


@router.post("/{complaint_id}/decide", response_model=ComplaintResponse)
async def decide_complaint(
    complaint_id: UUID,
    decision_content: str,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """投诉处理决定"""
    stmt = select(Complaint).where(Complaint.id == complaint_id)
    result = await db.execute(stmt)
    complaint = result.scalar_one_or_none()
    if not complaint:
        raise HTTPException(status_code=404, detail="投诉不存在")

    complaint.decision_content = decision_content
    complaint.decided_by = current_user.sub
    complaint.decided_at = datetime.now(timezone.utc)
    complaint.status = "decided"
    await db.commit()
    await db.refresh(complaint)
    return ComplaintResponse.model_validate(complaint)
