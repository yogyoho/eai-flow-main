"""Pydantic schemas for law management."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class LawBase(BaseModel):
    """Law base schema."""

    title: str = Field(..., description="Law title")
    law_number: Optional[str] = Field(None, description="Law number, e.g. GB 3095-2012")
    law_type: str = Field(..., description="Law type")
    status: Optional[str] = Field("active", description="Status: active, deprecated, updating")
    department: Optional[str] = Field(None, description="Issuing department")
    effective_date: Optional[datetime] = Field(None, description="Effective date")
    update_date: Optional[datetime] = Field(None, description="Update date")
    content: Optional[str] = Field(None, description="Law body content")
    summary: Optional[str] = Field(None, description="Summary")
    keywords: Optional[list[str]] = Field(None, description="Keywords")
    referred_laws: Optional[list[str]] = Field(None, description="Referenced laws")
    sector: Optional[str] = Field(None, description="Applicable industry")
    version: Optional[str] = Field(None, description="Version number")
    supersedes: Optional[str] = Field(None, description="Superseded old law")
    superseded_by: Optional[str] = Field(None, description="Superseded by")
    source_url: Optional[str] = Field(None, description="Source URL")


class LawCreate(LawBase):
    """Create law request."""
    pass


class LawUpdate(BaseModel):
    """Update law request."""

    title: Optional[str] = None
    law_number: Optional[str] = None
    law_type: Optional[str] = None
    status: Optional[str] = None
    department: Optional[str] = None
    effective_date: Optional[datetime] = None
    update_date: Optional[datetime] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    keywords: Optional[list[str]] = None
    referred_laws: Optional[list[str]] = None
    sector: Optional[str] = None
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    source_url: Optional[str] = None


class LawMetadata(BaseModel):
    """Law metadata."""

    keywords: list[str] = Field(default_factory=list)
    referred_laws: list[str] = Field(default_factory=list)
    sector: Optional[str] = None
    version: Optional[str] = None
    law_number: Optional[str] = None
    effective_date: Optional[str] = None
    issuing_authority: Optional[str] = None
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    source_url: Optional[str] = None


class LawResponse(LawBase):
    """Law response."""

    id: str
    ref_count: int = 0
    view_count: int = 0
    ragflow_dataset_id: Optional[str] = None
    ragflow_document_id: Optional[str] = None
    is_synced: str = "pending"
    last_sync_at: Optional[datetime] = None
    metadata: Optional[LawMetadata] = None
    linked_templates: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None

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
    dataset_id: Optional[str] = None
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
    last_sync_at: Optional[datetime] = None
    ragflow_document_id: Optional[str] = None
    error_message: Optional[str] = None


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
    section_title: Optional[str] = Field(None, description="Linked section title")
    metadata: Optional[dict[str, Any]] = None


class LawTemplateRelationResponse(BaseModel):
    """Law-template relation response."""

    id: str
    law_id: str
    law_title: str
    template_id: str
    template_name: str
    section_title: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FileParseResponse(BaseModel):
    """Law file parse response."""

    filename: str
    content: str = ""
    char_count: int = 0
    success: bool = True
    error: Optional[str] = None


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
    updated_at: Optional[datetime] = None


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
