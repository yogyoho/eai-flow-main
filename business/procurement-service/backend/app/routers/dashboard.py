"""仪表盘统计 API 路由"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Bid, Complaint, Contract, Evaluation, TenderProject
from app.schemas import DashboardStats

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["仪表盘统计"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """获取仪表盘统计数据"""
    active_result = await db.execute(
        select(func.count(TenderProject.id)).where(
            TenderProject.status.in_(["published", "bidding", "evaluating"])
        )
    )
    active_projects = active_result.scalar() or 0

    bid_result = await db.execute(
        select(func.count(Bid.id)).where(Bid.status == "submitted")
    )
    ongoing_bids = bid_result.scalar() or 0

    eval_result = await db.execute(
        select(func.count(Evaluation.id)).where(Evaluation.status == "pending")
    )
    pending_evaluations = eval_result.scalar() or 0

    contract_result = await db.execute(
        select(func.count(Contract.id)).where(Contract.status == "signed")
    )
    active_contracts = contract_result.scalar() or 0

    complaint_result = await db.execute(
        select(func.count(Complaint.id)).where(
            Complaint.status.in_(["submitted", "reviewing", "processing"])
        )
    )
    pending_complaints = complaint_result.scalar() or 0

    budget_result = await db.execute(
        select(func.sum(TenderProject.budget)).where(
            TenderProject.status.in_(["published", "bidding", "evaluating"])
        )
    )
    total_budget = budget_result.scalar() or 0

    contract_value_result = await db.execute(
        select(func.sum(Contract.total_price)).where(
            Contract.status.in_(["signed", "performance"])
        )
    )
    total_contracts_value = contract_value_result.scalar() or 0

    from decimal import Decimal

    return DashboardStats(
        active_projects=active_projects,
        ongoing_bids=ongoing_bids,
        pending_evaluations=pending_evaluations,
        active_contracts=active_contracts,
        pending_complaints=pending_complaints,
        total_budget=Decimal(str(total_budget or 0)),
        total_contracts_value=Decimal(str(total_contracts_value or 0)),
    )
