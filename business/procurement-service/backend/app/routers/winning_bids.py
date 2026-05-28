"""中标管理 API 路由"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Bid, Contract, TenderProject, WinningBid
from app.schemas import (
    ContractCreate,
    ContractResponse,
    WinningBidCreate,
    WinningBidResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/winning-bids", tags=["中标管理"])


def _make_contract_no() -> str:
    from datetime import datetime
    import random
    now = datetime.now(timezone.utc)
    return f"HT-{now.strftime('%Y%m%d')}-{random.randint(1000, 9999)}"


@router.post("", response_model=WinningBidResponse, status_code=status.HTTP_201_CREATED)
async def create_winning_bid(
    data: WinningBidCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """创建中标记录"""
    bid_stmt = select(Bid).where(Bid.id == data.bid_id)
    bid_result = await db.execute(bid_stmt)
    bid = bid_result.scalar_one_or_none()
    if not bid:
        raise HTTPException(status_code=404, detail="投标记录不存在")

    existing_stmt = select(WinningBid).where(
        WinningBid.project_id == data.project_id,
        WinningBid.bid_id == data.bid_id,
    )
    existing_result = await db.execute(existing_stmt)
    if existing_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该投标已有中标记录")

    winning_bid = WinningBid(
        project_id=data.project_id,
        bid_id=data.bid_id,
        winning_price=bid.bid_price,
        decision_summary=data.decision_summary,
        decided_by=current_user.sub,
    )
    db.add(winning_bid)

    bid.status = "won"
    await db.commit()
    await db.refresh(winning_bid)
    return WinningBidResponse.model_validate(winning_bid)


@router.post("/{winning_bid_id}/confirm", response_model=WinningBidResponse)
async def confirm_winning_bid(
    winning_bid_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """确认中标结果"""
    stmt = select(WinningBid).where(WinningBid.id == winning_bid_id)
    result = await db.execute(stmt)
    wb = result.scalar_one_or_none()
    if not wb:
        raise HTTPException(status_code=404, detail="中标记录不存在")

    wb.confirmed = True
    wb.confirmed_at = datetime.now(timezone.utc)
    wb.confirmed_by = current_user.sub
    await db.commit()
    await db.refresh(wb)
    return WinningBidResponse.model_validate(wb)


@router.post("/{winning_bid_id}/contract", status_code=status.HTTP_201_CREATED)
async def generate_contract_from_winning_bid(
    winning_bid_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """从中标记录生成合同"""
    stmt = select(WinningBid).where(WinningBid.id == winning_bid_id)
    result = await db.execute(stmt)
    wb = result.scalar_one_or_none()
    if not wb:
        raise HTTPException(status_code=404, detail="中标记录不存在")

    bid_stmt = select(Bid).where(Bid.id == wb.bid_id)
    bid_result = await db.execute(bid_stmt)
    bid = bid_result.scalar_one_or_none()

    proj_stmt = select(TenderProject).where(TenderProject.id == wb.project_id)
    proj_result = await db.execute(proj_stmt)
    project = proj_result.scalar_one_or_none()

    contract = Contract(
        contract_no=_make_contract_no(),
        project_id=wb.project_id,
        winning_bid_id=wb.id,
        bidder_id=bid.bidder_id if bid else None,
        title=f"{project.title} 合同" if project else "采购合同",
        total_price=wb.winning_price,
        operator_id=current_user.sub,
        status="draft",
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return ContractResponse.model_validate(contract)
