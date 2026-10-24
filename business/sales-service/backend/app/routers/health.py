from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.errors import SalesError
from app.storage import health as storage_health
from app.workflows.client import temporal_health

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "sales-service",
        "version": "0.1.0",
        "database": db_ok,
        "auth_mode": settings.auth_mode,
        "temporal": await temporal_health(),
        "attachments": {
            "enabled": settings.minio_enabled,
            "bucket": settings.minio_bucket,
            "ready": await storage_health(),
        },
    }


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        raise SalesError("数据库未就绪", "SALES-503-DB", 503) from exc
    return {"ready": True}
