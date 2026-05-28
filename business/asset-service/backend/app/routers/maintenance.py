"""维修保养路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Asset, MaintenanceRecord
from app.schemas import (
    MaintenanceListResponse,
    MaintenanceRecordCreate,
    MaintenanceRecordResponse,
)

router = APIRouter(prefix="/maintenance", tags=["维修保养"])


@router.get("", response_model=MaintenanceListResponse)
async def list_maintenance(
    asset_id: UUID | None = Query(None),
    maintenance_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    stmt = select(MaintenanceRecord)
    count_stmt = select(func.count(MaintenanceRecord.id))

    if asset_id:
        stmt = stmt.where(MaintenanceRecord.asset_id == asset_id)
        count_stmt = count_stmt.where(MaintenanceRecord.asset_id == asset_id)
    if maintenance_type:
        stmt = stmt.where(MaintenanceRecord.maintenance_type == maintenance_type)
        count_stmt = count_stmt.where(MaintenanceRecord.maintenance_type == maintenance_type)

    result = await db.execute(stmt.offset(skip).limit(limit).order_by(MaintenanceRecord.created_at.desc()))
    records = result.scalars().all()

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return MaintenanceListResponse(records=[MaintenanceRecordResponse.model_validate(r) for r in records], total=total)


@router.post("", response_model=MaintenanceRecordResponse, status_code=status.HTTP_201_CREATED)
async def create_maintenance(
    data: MaintenanceRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    asset_result = await db.execute(select(Asset).where(Asset.id == data.asset_id))
    if not asset_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    record = MaintenanceRecord(
        **data.model_dump(),
        operator_id=current_user.sub,
        operator_name=current_user.username,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return MaintenanceRecordResponse.model_validate(record)
