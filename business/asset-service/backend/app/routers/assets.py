"""资产台账路由"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Asset
from app.schemas import (
    AssetCreate,
    AssetListResponse,
    AssetResponse,
    AssetUpdate,
)

router = APIRouter(prefix="/assets", tags=["资产台账"])


@router.get("", response_model=AssetListResponse)
async def list_assets(
    keyword: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    dept_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    stmt = select(Asset)
    count_stmt = select(func.count(Asset.id))

    if keyword:
        stmt = stmt.where(Asset.name.ilike(f"%{keyword}%") | Asset.asset_no.ilike(f"%{keyword}%"))
        count_stmt = count_stmt.where(Asset.name.ilike(f"%{keyword}%") | Asset.asset_no.ilike(f"%{keyword}%"))
    if category:
        stmt = stmt.where(Asset.category == category)
        count_stmt = count_stmt.where(Asset.category == category)
    if status:
        stmt = stmt.where(Asset.status == status)
        count_stmt = count_stmt.where(Asset.status == status)
    if dept_id:
        stmt = stmt.where(Asset.dept_id == dept_id)
        count_stmt = count_stmt.where(Asset.dept_id == dept_id)

    result = await db.execute(stmt.offset(skip).limit(limit).order_by(Asset.created_at.desc()))
    assets = result.scalars().all()

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return AssetListResponse(assets=[AssetResponse.model_validate(a) for a in assets], total=total)


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    data: AssetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    asset = Asset(**data.model_dump(), created_by=current_user.username)
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return AssetResponse.model_validate(asset)


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return AssetResponse.model_validate(asset)


@router.put("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: UUID,
    data: AssetUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(asset, key, value)
    await db.flush()
    await db.refresh(asset)
    return AssetResponse.model_validate(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    await db.delete(asset)
