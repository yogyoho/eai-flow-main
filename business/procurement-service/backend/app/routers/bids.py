"""投标管理 API 路由"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Bid, Bidder, TenderProject
from app.schemas import (
    BidCreate,
    BidListResponse,
    BidResponse,
    BidUpdate,
    MessageResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bids", tags=["投标管理"])


@router.get("", response_model=BidListResponse)
async def list_bids(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    project_id: Optional[UUID] = None,
    bidder_id: Optional[UUID] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """查询投标记录"""
    stmt = select(Bid)
    if project_id:
        stmt = stmt.where(Bid.project_id == project_id)
    if bidder_id:
        stmt = stmt.where(Bid.bidder_id == bidder_id)
    if status:
        stmt = stmt.where(Bid.status == status)
    if keyword:
        stmt = stmt.where(Bid.bid_no.ilike(f"%{keyword}%"))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.order_by(Bid.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    bids = list(result.scalars().all())

    return BidListResponse(
        bids=[BidResponse.model_validate(b) for b in bids],
        total=total,
    )


@router.post("", response_model=BidResponse, status_code=status.HTTP_201_CREATED)
async def create_bid(
    data: BidCreate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """提交投标"""
    proj_stmt = select(TenderProject).where(TenderProject.id == data.project_id)
    proj_result = await db.execute(proj_stmt)
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="招标项目不存在")
    if project.status not in ("published", "bidding"):
        raise HTTPException(status_code=400, detail="项目当前不处于招标中状态，无法投标")

    bidder_stmt = select(Bidder).where(Bidder.id == data.bidder_id)
    bidder_result = await db.execute(bidder_stmt)
    bidder = bidder_result.scalar_one_or_none()
    if not bidder:
        raise HTTPException(status_code=404, detail="投标人不存在")
    if bidder.status != "approved":
        raise HTTPException(status_code=400, detail="投标人状态异常，无法投标")

    bid = Bid(**data.model_dump(), submitted_at=datetime.now(timezone.utc))
    db.add(bid)
    await db.commit()
    await db.refresh(bid)
    return BidResponse.model_validate(bid)


@router.get("/{bid_id}", response_model=BidResponse)
async def get_bid(
    bid_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """获取投标详情"""
    stmt = select(Bid).where(Bid.id == bid_id)
    result = await db.execute(stmt)
    bid = result.scalar_one_or_none()
    if not bid:
        raise HTTPException(status_code=404, detail="投标记录不存在")
    return BidResponse.model_validate(bid)


@router.put("/{bid_id}", response_model=BidResponse)
async def update_bid(
    bid_id: UUID,
    data: BidUpdate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """更新投标"""
    stmt = select(Bid).where(Bid.id == bid_id)
    result = await db.execute(stmt)
    bid = result.scalar_one_or_none()
    if not bid:
        raise HTTPException(status_code=404, detail="投标记录不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(bid, field, value)
    await db.commit()
    await db.refresh(bid)
    return BidResponse.model_validate(bid)


@router.post("/{bid_id}/compliance-check")
async def check_bid_compliance(
    bid_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """投标合规性自查"""
    stmt = select(Bid).where(Bid.id == bid_id)
    result = await db.execute(stmt)
    bid = result.scalar_one_or_none()
    if not bid:
        raise HTTPException(status_code=404, detail="投标记录不存在")

    issues: list[str] = []
    if bid.bid_price is None:
        issues.append("投标价格未填写")
    if bid.technical_proposal_url is None:
        issues.append("技术方案未上传")

    passed = len(issues) == 0
    bid.compliance_check_passed = passed
    bid.compliance_issues = issues if issues else None
    await db.commit()

    return {
        "passed": passed,
        "score": max(0, 100 - len(issues) * 30),
        "issues": issues,
    }
