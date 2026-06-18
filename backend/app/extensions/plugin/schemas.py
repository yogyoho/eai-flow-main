"""Pydantic schemas for the plugin extension. Field names align with frontend
src/extensions/plugin/types.ts (snake_case in DB, frontend api.ts maps snake<->camel)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Plugin (registry) ──


class PluginResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | str
    name: str
    type: str
    version: str
    author: str | None = None
    description: str | None = None
    config_schema: dict | None = None
    entry_point: str | None = None
    icon: str | None = None
    permissions: list = Field(default_factory=list)
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PluginListResponse(BaseModel):
    items: list[PluginResponse]


# ── PluginInstance ──


class PluginInstanceCreate(BaseModel):
    plugin_id: UUID | str
    project_id: UUID | str | None = None
    config: dict = Field(default_factory=dict)


class PluginInstanceUpdate(BaseModel):
    config: dict | None = None
    status: str | None = None


class PluginInstanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | str
    plugin_id: UUID | str
    plugin_name: str
    plugin_type: str
    project_id: UUID | str | None = None
    config: dict
    status: str
    last_sync_at: datetime | None = None
    created_at: datetime | None = None


class PluginInstanceListResponse(BaseModel):
    items: list[PluginInstanceResponse]


# ── ApiKey ──


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    scope: list[str] = Field(default_factory=list)
    project_id: UUID | str | None = None
    expires_at: datetime | None = None


class ApiKeyResponse(BaseModel):
    """List/detail view — never exposes the plaintext key or the hash."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | str
    name: str
    key_prefix: str
    scope: list[str] = Field(default_factory=list)
    project_id: UUID | str | None = None
    created_by: UUID | None = None
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime | None = None


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyResponse]


class ApiKeyCreateResponse(BaseModel):
    """Returned ONCE on creation — carries the plaintext key."""

    id: UUID | str
    key: str
