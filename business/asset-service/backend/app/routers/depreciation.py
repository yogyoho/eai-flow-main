"""折旧计算路由"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Asset
from app.schemas import DepreciationRecord, DepreciationResponse

router = APIRouter(prefix="/depreciation", tags=["折旧计算"])


@router.get("", response_model=DepreciationResponse)
async def compute_depreciation(
    dept_id: str | None = Query(None),
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    stmt = select(Asset).where(Asset.status != "scrapped")
    if dept_id:
        stmt = stmt.where(Asset.dept_id == dept_id)
    if category:
        stmt = stmt.where(Asset.category == category)

    result = await db.execute(stmt.order_by(Asset.created_at.desc()))
    assets = result.scalars().all()

    records = []
    total_value = Decimal("0")
    total_monthly = Decimal("0")

    now = datetime.now(timezone.utc)
    for asset in assets:
        purchase_price = asset.purchase_price or Decimal("0")
        useful_life_months = max(asset.useful_life_years * 12, 1)
        depreciable_amount = purchase_price - asset.residual_value
        monthly_depreciation = (
            depreciable_amount / useful_life_months if useful_life_months > 0 else Decimal("0")
        )

        if asset.purchase_date:
            months_owned = max(
                (now.year - asset.purchase_date.year) * 12 + (now.month - asset.purchase_date.month),
                0
            )
        else:
            months_owned = 0

        accumulated = monthly_depreciation * months_owned
        current_value = max(purchase_price - accumulated, asset.residual_value)

        records.append(
            DepreciationRecord(
                asset_id=asset.id,
                asset_name=asset.name,
                asset_no=asset.asset_no,
                purchase_date=asset.purchase_date,
                purchase_price=asset.purchase_price,
                useful_life_years=asset.useful_life_years,
                residual_value=asset.residual_value,
                current_value=current_value,
                monthly_depreciation=monthly_depreciation.quantize(Decimal("0.01")),
                accumulated_depreciation=accumulated.quantize(Decimal("0.01")),
                status=asset.status,
            )
        )
        total_value += current_value
        total_monthly += monthly_depreciation

    return DepreciationResponse(
        records=records,
        total=total_value.quantize(Decimal("0.01")),
        total_monthly=total_monthly.quantize(Decimal("0.01")),
    )
