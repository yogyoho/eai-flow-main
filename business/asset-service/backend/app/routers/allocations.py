"""调拨管理路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Allocation, Asset
from app.schemas import (
    AllocationCreate,
    AllocationListResponse,
    AllocationResponse,
    AllocationUpdate,
)

router = APIRouter(prefix="/allocations", tags=["调拨管理"])


@router.get("", response_model=AllocationListResponse)
async def list_allocations(
    asset_id: UUID | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    stmt = select(Allocation)
    count_stmt = select(func.count(Allocation.id))

    if asset_id:
        stmt = stmt.where(Allocation.asset_id == asset_id)
        count_stmt = count_stmt.where(Allocation.asset_id == asset_id)
    if status:
        stmt = stmt.where(Allocation.status == status)
        count_stmt = count_stmt.where(Allocation.status == status)

    result = await db.execute(stmt.offset(skip).limit(limit).order_by(Allocation.created_at.desc()))
    records = result.scalars().all()

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return AllocationListResponse(records=[AllocationResponse.model_validate(r) for r in records], total=total)


@router.post("", response_model=AllocationResponse, status_code=status.HTTP_201_CREATED)
async def create_allocation(
    data: AllocationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    asset_result = await db.execute(select(Asset).where(Asset.id == data.asset_id))
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    record = Allocation(
        **data.model_dump(),
        from_dept_id=asset.dept_id,
        from_dept_name=asset.dept_name,
        from_location=asset.location,
        operator_id=current_user.sub,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return AllocationResponse.model_validate(record)


@router.put("/{allocation_id}", response_model=AllocationResponse)
async def update_allocation(
    allocation_id: UUID,
    data: AllocationUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(Allocation).where(Allocation.id == allocation_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allocation not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(record, key, value)

    if data.status == "approved":
        asset_result = await db.execute(select(Asset).where(Asset.id == record.asset_id))
        asset = asset_result.scalar_one_or_none()
        if asset:
            asset.dept_id = record.to_dept_id
            asset.dept_name = record.to_dept_name
            asset.location = record.to_location

    await db.flush()
    await db.refresh(record)
    return AllocationResponse.model_validate(record)
