"""仪表盘路由"""

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Allocation, Asset, MaintenanceRecord, ScrapRecord
from app.schemas import DashboardStats

router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    total_result = await db.execute(select(func.count(Asset.id)))
    total_assets = total_result.scalar() or 0

    value_result = await db.execute(select(func.coalesce(func.sum(Asset.current_value), 0)))
    total_value = value_result.scalar() or Decimal("0")

    normal_result = await db.execute(select(func.count(Asset.id)).where(Asset.status == "normal"))
    normal_count = normal_result.scalar() or 0

    maintenance_result = await db.execute(
        select(func.count(Asset.id)).where(Asset.status == "maintenance")
    )
    maintenance_count = maintenance_result.scalar() or 0

    allocated_result = await db.execute(
        select(func.count(Asset.id)).where(Asset.status == "allocated")
    )
    allocated_count = allocated_result.scalar() or 0

    scrapped_result = await db.execute(
        select(func.count(Asset.id)).where(Asset.status == "scrapped")
    )
    scrapped_count = scrapped_result.scalar() or 0

    pending_maint_result = await db.execute(
        select(func.count(MaintenanceRecord.id)).where(
            MaintenanceRecord.next_maintenance_date < func.now()
        )
    )
    pending_maintenance = pending_maint_result.scalar() or 0

    pending_alloc_result = await db.execute(
        select(func.count(Allocation.id)).where(Allocation.status == "pending")
    )
    pending_allocations = pending_alloc_result.scalar() or 0

    pending_scrap_result = await db.execute(
        select(func.count(ScrapRecord.id)).where(ScrapRecord.status == "pending")
    )
    pending_scraps = pending_scrap_result.scalar() or 0

    return DashboardStats(
        total_assets=total_assets,
        total_value=total_value,
        normal_count=normal_count,
        maintenance_count=maintenance_count,
        allocated_count=allocated_count,
        scrapped_count=scrapped_count,
        pending_maintenance=pending_maintenance,
        pending_allocations=pending_allocations,
        pending_scraps=pending_scraps,
    )
