"""Pydantic schemas for license module."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SystemInfo(BaseModel):
    """System information for license request."""

    hostname: str = ""
    platform: str = ""


class LicenseStatusResponse(BaseModel):
    """GET /api/license/status response."""

    valid: bool
    machine_id: str | None = None
    type: str | None = None
    customer: str | None = None
    max_users: int | None = None
    current_users: int = 0
    modules: dict[str, bool] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None
    days_remaining: int | None = None
    in_grace_period: bool = False
    grace_period_remaining_days: int | None = None
    warnings: list[str] = Field(default_factory=list)
    is_dev_mode: bool = False
    system_info: SystemInfo = Field(default_factory=SystemInfo)


class LicenseImportResponse(BaseModel):
    """POST /api/license/import response."""

    success: bool
    machine_id: str | None = None
    type: str | None = None
    customer: str | None = None
    message: str


class LicenseHistoryItem(BaseModel):
    """Single history record."""

    id: str
    jwt_jti: str
    machine_id: str
    type: str
    customer: str | None = None
    max_users: int | None = None
    modules: dict[str, bool] = Field(default_factory=dict)
    issued_at: datetime
    expires_at: datetime | None = None
    imported_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


class LicenseHistoryResponse(BaseModel):
    """GET /api/license/history response."""

    items: list[LicenseHistoryItem]
    total: int
