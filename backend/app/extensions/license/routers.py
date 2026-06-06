"""License API routers."""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.license.schemas import (
    LicenseHistoryItem,
    LicenseHistoryResponse,
    LicenseImportResponse,
    LicenseStatusResponse,
)
from app.extensions.license.service import LicenseError, LicenseService
from app.extensions.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/license", tags=["License"])


@router.get("/status", response_model=LicenseStatusResponse)
async def get_license_status(
    db: AsyncSession = Depends(get_db),
):
    """Get current license status. No auth required — used by frontend route guards."""
    count_result = await db.execute(
        select(func.count(User.id)).where(
            User.is_deleted == False,
            User.status == "active",
        )
    )
    user_count = count_result.scalar() or 0

    status_data = LicenseService.get_status(current_user_count=user_count)
    if status_data.get("machine_id") == "DEV-MODE":
        status_data["is_dev_mode"] = True
    return LicenseStatusResponse(**status_data)


@router.post("/import", response_model=LicenseImportResponse)
async def import_license(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("admin")),
):
    """Import a new license file. Requires admin permission."""
    if not file.filename or not file.filename.endswith(".lic"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Expected .lic file.",
        )

    jwt_raw = (await file.read()).decode("utf-8").strip()
    if not jwt_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty license file.",
        )

    try:
        record = await LicenseService.import_license(db, jwt_raw)
    except LicenseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        ) from e

    return LicenseImportResponse(
        success=True,
        machine_id=record.machine_id,
        type=record.type,
        customer=record.customer,
        message="License imported successfully",
    )


@router.get("/history", response_model=LicenseHistoryResponse)
async def get_license_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("admin")),
):
    """Get license import history. Requires admin permission."""
    items, total = await LicenseService.get_history(db, skip=skip, limit=limit)
    return LicenseHistoryResponse(
        items=[LicenseHistoryItem.model_validate(item) for item in items],
        total=total,
    )


@router.get("/export")
async def export_license(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("admin")),
):
    """Download current active license file. Requires admin permission."""
    jwt_raw = await LicenseService.export_license(db)
    if not jwt_raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active license found",
        )
    return PlainTextResponse(
        content=jwt_raw,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=license.lic"},
    )
