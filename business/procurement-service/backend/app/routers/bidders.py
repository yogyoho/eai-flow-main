"""投标人 API 路由"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Bidder
from app.schemas import (
    BidderCreate,
    BidderListResponse,
    BidderResponse,
    BidderUpdate,
    MessageResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bidders", tags=["投标人管理"])


@router.get("", response_model=BidderListResponse)
async def list_bidders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    region: Optional[str] = None,
    status: Optional[str] = None,
    credit_rating: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """查询投标人列表"""
    stmt = select(Bidder)
    if keyword:
        stmt = stmt.where(Bidder.name.ilike(f"%{keyword}%"))
    if region:
        stmt = stmt.where(Bidder.region == region)
    if status:
        stmt = stmt.where(Bidder.status == status)
    if credit_rating:
        stmt = stmt.where(Bidder.credit_rating == credit_rating)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.order_by(Bidder.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    bidders = list(result.scalars().all())

    return BidderListResponse(
        bidders=[BidderResponse.model_validate(b) for b in bidders],
        total=total,
    )


@router.post("", response_model=BidderResponse, status_code=status.HTTP_201_CREATED)
async def create_bidder(
    data: BidderCreate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """创建投标人"""
    bidder = Bidder(**data.model_dump())
    db.add(bidder)
    await db.commit()
    await db.refresh(bidder)
    return BidderResponse.model_validate(bidder)


@router.get("/{bidder_id}", response_model=BidderResponse)
async def get_bidder(
    bidder_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """获取投标人详情"""
    stmt = select(Bidder).where(Bidder.id == bidder_id)
    result = await db.execute(stmt)
    bidder = result.scalar_one_or_none()
    if not bidder:
        raise HTTPException(status_code=404, detail="投标人不存在")
    return BidderResponse.model_validate(bidder)


@router.put("/{bidder_id}", response_model=BidderResponse)
async def update_bidder(
    bidder_id: UUID,
    data: BidderUpdate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """更新投标人信息"""
    stmt = select(Bidder).where(Bidder.id == bidder_id)
    result = await db.execute(stmt)
    bidder = result.scalar_one_or_none()
    if not bidder:
        raise HTTPException(status_code=404, detail="投标人不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(bidder, field, value)
    await db.commit()
    await db.refresh(bidder)
    return BidderResponse.model_validate(bidder)


@router.delete("/{bidder_id}", response_model=MessageResponse)
async def delete_bidder(
    bidder_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """删除投标人"""
    stmt = select(Bidder).where(Bidder.id == bidder_id)
    result = await db.execute(stmt)
    bidder = result.scalar_one_or_none()
    if not bidder:
        raise HTTPException(status_code=404, detail="投标人不存在")
    await db.delete(bidder)
    await db.commit()
    return MessageResponse(message="投标人删除成功")


@router.post("/batch", response_model=BidderListResponse, status_code=status.HTTP_201_CREATED)
async def batch_import_bidders(
    bidders_data: list[BidderCreate],
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """批量导入投标人"""
    bidders = [Bidder(**b.model_dump()) for b in bidders_data]
    db.add_all(bidders)
    await db.commit()
    for b in bidders:
        await db.refresh(b)
    return BidderListResponse(
        bidders=[BidderResponse.model_validate(b) for b in bidders],
        total=len(bidders),
    )
