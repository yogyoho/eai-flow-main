"""资产盘点路由"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Asset, AssetCheck
from app.schemas import (
    AssetCheckCreate,
    AssetCheckListResponse,
    AssetCheckResponse,
    AssetCheckUpdate,
)

router = APIRouter(prefix="/checks", tags=["资产盘点"])


def _generate_check_no() -> str:
    from datetime import datetime
    return f"CK{datetime.now().strftime('%Y%m%d%H%M%S')}"


@router.get("", response_model=AssetCheckListResponse)
async def list_checks(
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    stmt = select(AssetCheck)
    count_stmt = select(func.count(AssetCheck.id))

    if status:
        stmt = stmt.where(AssetCheck.status == status)
        count_stmt = count_stmt.where(AssetCheck.status == status)

    result = await db.execute(stmt.offset(skip).limit(limit).order_by(AssetCheck.created_at.desc()))
    checks = result.scalars().all()

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return AssetCheckListResponse(checks=[AssetCheckResponse.model_validate(c) for c in checks], total=total)


@router.post("", response_model=AssetCheckResponse, status_code=status.HTTP_201_CREATED)
async def create_check(
    data: AssetCheckCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    asset_stmt = select(func.count(Asset.id))
    if data.dept_id:
        asset_stmt = asset_stmt.where(Asset.dept_id == data.dept_id)
    total_result = await db.execute(asset_stmt)
    total_count = total_result.scalar() or 0

    check = AssetCheck(
        check_no=_generate_check_no(),
        check_name=data.check_name,
        dept_id=data.dept_id,
        dept_name=data.dept_name,
        check_date=data.check_date,
        total_count=total_count,
        operator_id=current_user.sub,
    )
    db.add(check)
    await db.flush()
    await db.refresh(check)
    return AssetCheckResponse.model_validate(check)


@router.put("/{check_id}", response_model=AssetCheckResponse)
async def update_check(
    check_id: str,
    data: AssetCheckUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    from uuid import UUID

    result = await db.execute(select(AssetCheck).where(AssetCheck.id == UUID(check_id)))
    check = result.scalar_one_or_none()
    if not check:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Check not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(check, key, value)

    await db.flush()
    await db.refresh(check)
    return AssetCheckResponse.model_validate(check)
