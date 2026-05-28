"""场所工位 API 路由"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import VenueSpace
from app.schemas import (
    VenueSpaceCreate,
    VenueSpaceListResponse,
    VenueSpaceResponse,
    VenueSpaceUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/venue-spaces", tags=["场所工位"])


@router.get("", response_model=VenueSpaceListResponse)
async def list_venue_spaces(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """查询场所工位"""
    stmt = select(VenueSpace)
    count_stmt = select(func.count(VenueSpace.id))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.order_by(VenueSpace.venue_name, VenueSpace.space_no).offset(skip).limit(limit)
    result = await db.execute(stmt)
    spaces = list(result.scalars().all())

    return VenueSpaceListResponse(
        spaces=[VenueSpaceResponse.model_validate(s) for s in spaces],
        total=total,
    )


@router.post("", response_model=VenueSpaceResponse, status_code=201)
async def create_venue_space(
    data: VenueSpaceCreate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """创建场所工位"""
    space = VenueSpace(**data.model_dump())
    db.add(space)
    await db.commit()
    await db.refresh(space)
    return VenueSpaceResponse.model_validate(space)


@router.put("/{space_id}", response_model=VenueSpaceResponse)
async def update_venue_space(
    space_id: UUID,
    data: VenueSpaceUpdate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """更新场所工位"""
    stmt = select(VenueSpace).where(VenueSpace.id == space_id)
    result = await db.execute(stmt)
    space = result.scalar_one_or_none()
    if not space:
        raise HTTPException(status_code=404, detail="工位不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(space, field, value)
    await db.commit()
    await db.refresh(space)
    return VenueSpaceResponse.model_validate(space)
