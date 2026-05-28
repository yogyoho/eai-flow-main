"""报废管理路由"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Asset, ScrapRecord
from app.schemas import (
    ScrapListResponse,
    ScrapRecordCreate,
    ScrapRecordResponse,
    ScrapRecordUpdate,
)
from uuid import UUID

router = APIRouter(prefix="/scraps", tags=["报废管理"])


def _generate_scrap_no() -> str:
    from datetime import datetime
    return f"SC{datetime.now().strftime('%Y%m%d%H%M%S')}"


@router.get("", response_model=ScrapListResponse)
async def list_scraps(
    asset_id: UUID | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    stmt = select(ScrapRecord)
    count_stmt = select(func.count(ScrapRecord.id))

    if asset_id:
        stmt = stmt.where(ScrapRecord.asset_id == asset_id)
        count_stmt = count_stmt.where(ScrapRecord.asset_id == asset_id)
    if status:
        stmt = stmt.where(ScrapRecord.status == status)
        count_stmt = count_stmt.where(ScrapRecord.status == status)

    result = await db.execute(stmt.offset(skip).limit(limit).order_by(ScrapRecord.created_at.desc()))
    records = result.scalars().all()

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return ScrapListResponse(records=[ScrapRecordResponse.model_validate(r) for r in records], total=total)


@router.post("", response_model=ScrapRecordResponse, status_code=status.HTTP_201_CREATED)
async def create_scrap(
    data: ScrapRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    asset_result = await db.execute(select(Asset).where(Asset.id == data.asset_id))
    if not asset_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    record = ScrapRecord(
        scrap_no=_generate_scrap_no(),
        **data.model_dump(),
        operator_id=current_user.sub,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return ScrapRecordResponse.model_validate(record)


@router.put("/{scrap_id}", response_model=ScrapRecordResponse)
async def update_scrap(
    scrap_id: str,
    data: ScrapRecordUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(ScrapRecord).where(ScrapRecord.id == UUID(scrap_id)))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scrap record not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(record, key, value)

    if data.status == "approved":
        asset_result = await db.execute(select(Asset).where(Asset.id == record.asset_id))
        asset = asset_result.scalar_one_or_none()
        if asset:
            asset.status = "scrapped"

    await db.flush()
    await db.refresh(record)
    return ScrapRecordResponse.model_validate(record)
