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
    generate_summary: bool = Field(False, description="Use AI to generate a change summary")
    content: str | None = Field(None, description="Current document content as markdown text")


class VersionRestoreResponse(BaseModel):
    version: int
    message: str


class VersionDiffResponse(BaseModel):
    from_version: int
    to_version: int
    from_summary: str | None = None
    to_summary: str | None = None
    from_created_at: datetime | None = None
    to_created_at: datetime | None = None
    diff_blocks: list[dict] = Field(default_factory=list, description="Block-level diff entries")
    ai_summary: str | None = Field(None, description="AI-generated summary of changes")
    legacy_notice: str | None = Field(None, description="Shown when one or both versions lack text snapshots")


# ─── AI Document-Level Review ─────────────────────────────────────────────


class AIReviewRequest(BaseModel):
    doc_id: UUID
    review_type: str = Field(default="full", description="full | style | logic | completeness")
    content: str | None = Field(None, description="Document content (markdown) from frontend editor")


class AIReviewComment(BaseModel):
    block_id: str | None = None
    comment: str
    severity: str = Field(default="info", description="info | warning | error")


class AIReviewResponse(BaseModel):
    review_id: str
    comments: list[AIReviewComment] = Field(default_factory=list)
    overall_score: float | None = None
    summary: str | None = None
