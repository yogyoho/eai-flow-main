"""Pydantic schemas for law management."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LawBase(BaseModel):
    """Law base schema."""

    title: str = Field(..., description="Law title")
    law_number: str | None = Field(None, description="Law number, e.g. GB 3095-2012")
    law_type: str = Field(..., description="Law type")
    status: str | None = Field("active", description="Status: active, deprecated, updating")
    department: str | None = Field(None, description="Issuing department")
    effective_date: datetime | None = Field(None, description="Effective date")
    update_date: datetime | None = Field(None, description="Update date")
    content: str | None = Field(None, description="Law body content")
    summary: str | None = Field(None, description="Summary")
    keywords: list[str] | None = Field(None, description="Keywords")
    referred_laws: list[str] | None = Field(None, description="Referenced laws")
    sector: str | None = Field(None, description="Applicable industry")
    version: str | None = Field(None, description="Version number")
    supersedes: str | None = Field(None, description="Superseded old law")
    superseded_by: str | None = Field(None, description="Superseded by")
    source_url: str | None = Field(None, description="Source URL")


class LawCreate(LawBase):
    """Create law request."""

    pass


class LawUpdate(BaseModel):
    """Update law request."""

    title: str | None = None
    law_number: str | None = None
    law_type: str | None = None
    status: str | None = None
    department: str | None = None
    effective_date: datetime | None = None
    update_date: datetime | None = None
    content: str | None = None
    summary: str | None = None
    keywords: list[str] | None = None
    referred_laws: list[str] | None = None
    sector: str | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    source_url: str | None = None


class LawMetadata(BaseModel):
    """Law metadata."""

    keywords: list[str] = Field(default_factory=list)
    referred_laws: list[str] = Field(default_factory=list)
    sector: str | None = None
    version: str | None = None
    law_number: str | None = None
    effective_date: str | None = None
    issuing_authority: str | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    source_url: str | None = None


class LawResponse(LawBase):
    """Law response."""

    id: str
    ref_count: int = 0
    view_count: int = 0
    ragflow_dataset_id: str | None = None
    ragflow_document_id: str | None = None
    is_synced: str = "pending"
    last_sync_at: datetime | None = None
    metadata: LawMetadata | None = None
    linked_templates: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class LawStatistics(BaseModel):
    """Law statistics."""

    total_count: int = 0
    active_count: int = 0
    deprecated_count: int = 0
    updating_count: int = 0
    synced_count: int = 0
    pending_sync_count: int = 0
    failed_sync_count: int = 0


class LawListResponse(BaseModel):
    """Law list response."""

    laws: list[LawResponse] = Field(default_factory=list)
    total: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)


class RAGFlowKBStatus(BaseModel):
    """RAGFlow knowledge base status."""

    type: str = Field(alias="law_type")
    kb_name: str
    exists: bool = False
    dataset_id: str | None = None
    document_count: int = 0
    status: str = "unknown"

    class Config:
        populate_by_name = True


class RAGFlowStatusResponse(BaseModel):
    """RAGFlow status response."""

    total_kbs: int = 0
    healthy_kbs: int = 0
    missing_kbs: int = 0
    error_kbs: int = 0
    statuses: list[RAGFlowKBStatus] = Field(default_factory=list)


class LawSyncStatus(BaseModel):
    """Law sync status."""

    law_id: str
    law_title: str
    law_type: str
    is_synced: str
    last_sync_at: datetime | None = None
    ragflow_document_id: str | None = None
    error_message: str | None = None


class RAGFlowInitResponse(BaseModel):
    """RAGFlow initialization response."""

    success: bool = True
    message: str = ""
    created: list[str] = Field(default_factory=list)
    already_exists: list[str] = Field(default_factory=list)
    failed: list[dict[str, str]] = Field(default_factory=list)


class LawTemplateRelationCreate(BaseModel):
    """Create law-template relation."""

    law_id: str
    template_id: str
    section_title: str | None = Field(None, description="Linked section title")
    metadata: dict[str, Any] | None = None


class LawTemplateRelationResponse(BaseModel):
    """Law-template relation response."""

    id: str
    law_id: str
    law_title: str
    template_id: str
    template_name: str
    section_title: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class FileParseResponse(BaseModel):
    """Law file parse response."""

    filename: str
    content: str = ""
    char_count: int = 0
    success: bool = True
    error: str | None = None


class ImportProgress(BaseModel):
    """Import progress."""

    task_id: str
    status: str = "pending"
    total: int = 0
    processed: int = 0
    success_count: int = 0
    failed_count: int = 0
    errors: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None


class LawBatchSyncRequest(BaseModel):
    """Batch sync request."""

    law_ids: list[str] = Field(..., description="Law IDs to sync")
    force: bool = Field(False, description="Force sync")


class LawBatchSyncResponse(BaseModel):
    """Batch sync response."""

    success: bool
    message: str
    total: int = 0
    synced: int = 0
    failed: int = 0
    errors: list[dict[str, str]] = Field(default_factory=list)
