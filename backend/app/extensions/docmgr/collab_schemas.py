"""Pydantic schemas for collaborative editing endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CommentCreateRequest(BaseModel):
    block_id: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=10000)
    parent_id: UUID | None = Field(None, description="Reply to this comment ID")


class CommentUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class CommentResponse(BaseModel):
    id: UUID
    doc_id: UUID
    block_id: str
    content: str
    parent_id: UUID | None = None
    user_id: UUID
    resolved: bool
    created_at: datetime
    updated_at: datetime
    username: str | None = None
    full_name: str | None = None


class VersionResponse(BaseModel):
    id: int
    doc_id: UUID
    version: int
    summary: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    username: str | None = None
    full_name: str | None = None


class VersionCreateRequest(BaseModel):
    summary: str | None = Field(None, max_length=500)


class VersionRestoreResponse(BaseModel):
    version: int
    message: str
