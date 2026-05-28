"""见证记录 API 路由"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import WitnessRecord
from app.schemas import (
    WitnessRecordCreate,
    WitnessRecordListResponse,
    WitnessRecordResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/witness-records", tags=["见证记录"])


@router.get("", response_model=WitnessRecordListResponse)
async def list_witness_records(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    project_id: Optional[UUID] = None,
    stage: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """查询见证记录"""
    stmt = select(WitnessRecord)
    if project_id:
        stmt = stmt.where(WitnessRecord.project_id == project_id)
    if stage:
        stmt = stmt.where(WitnessRecord.stage == stage)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.order_by(WitnessRecord.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    records = list(result.scalars().all())

    return WitnessRecordListResponse(
        records=[WitnessRecordResponse.model_validate(r) for r in records],
        total=total,
    )


@router.post("", status_code=201)
async def create_witness_record(
    data: WitnessRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """创建见证记录"""
    record = WitnessRecord(**data.model_dump(), operator_id=current_user.sub)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return WitnessRecordResponse.model_validate(record)
