"""App-center Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── AppDomain ──


class AppDomainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    label: str
    accent_color: str
    sort_order: int
    is_universal: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AppDomainCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=100)
    accent_color: str = "blue"
    sort_order: int = 0
    is_universal: bool = False


class AppDomainUpdate(BaseModel):
    label: str | None = None
    accent_color: str | None = None
    sort_order: int | None = None
    is_universal: bool | None = None


class AppDomainListResponse(BaseModel):
    items: list[AppDomainResponse]


# ── AppDefinition ──


class AppDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    app_id: str
    name: str
    description: str | None = None
    icon_name: str
    business_domain: str
    stage_tag: str | None = None
    path: str
    license_module: str | None = None
    admin_only: bool = False
    sort_order: int = 0
    sort_key: str
    is_builtin: bool = True
    is_enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AppDefinitionCreate(BaseModel):
    app_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    icon_name: str = Field(..., min_length=1, max_length=100)
    business_domain: str = Field(..., min_length=1, max_length=100)
    stage_tag: str | None = None
    path: str = Field(..., min_length=1, max_length=500)
    license_module: str | None = None
    admin_only: bool = False
    sort_order: int = 0
    sort_key: str = Field(..., min_length=1, max_length=200)
    is_enabled: bool = True


class AppDefinitionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon_name: str | None = None
    business_domain: str | None = None
    stage_tag: str | None = None
    path: str | None = None
    license_module: str | None = None
    admin_only: bool | None = None
    sort_order: int | None = None
    sort_key: str | None = None
    is_enabled: bool | None = None


class AppDefinitionListResponse(BaseModel):
    items: list[AppDefinitionResponse]
