"""Pydantic schemas for the data_source extension. Field names align with
frontend src/extensions/data-source/types.ts (snake_case in DB, the frontend
api.ts already maps snake_case <-> camelCase)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DataSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    type: str = Field(..., description="database | api | file | gis")
    connection_config: dict = Field(default_factory=dict)
    auth_type: str = "none"
    sync_mode: str = "manual"
    sync_config: dict | None = None


class DataSourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    type: str | None = None
    connection_config: dict | None = None
    auth_type: str | None = None
    sync_mode: str | None = None
    sync_config: dict | None = None
    status: str | None = None


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | str
    name: str
    description: str | None = None
    type: str
    connection_config: dict
    auth_type: str
    sync_mode: str
    sync_config: dict | None = None
    status: str
    last_sync_at: datetime | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DataSourceListResponse(BaseModel):
    items: list[DataSourceResponse]


class TestConnectionResult(BaseModel):
    success: bool
    message: str
    metadata: dict | None = None


class SyncResponse(BaseModel):
    id: UUID | str
    status: str
    last_sync_at: datetime
    metadata: dict = Field(default_factory=dict)
