# EAI-CUSTOM: forked from app.extensions.contract_price.schemas (geo-sample-bank Phase 1).
"""Pydantic request/response schemas for the geo-sample-bank management API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

ALLOWED_STAGES = {"survey", "detail", "exploration"}
ALLOWED_MINERALS = {"copper", "coal", "gold", "iron", "lead_zinc", "other"}
ALLOWED_STATUSES = {"uploaded", "parsed", "redacted", "reviewed", "failed"}


class UploadMeta(BaseModel):
    report_id: str = Field(min_length=2, max_length=128, pattern=r"^[a-z0-9][a-z0-9\-_]*$")
    stage: str = "exploration"
    mineral: str = "copper"
    year: int | None = None
    region: str | None = None


class ReviewRequest(BaseModel):
    decision: str  # approve / reject
    note: str | None = None


class RedactionOut(BaseModel):
    id: str
    rule: str
    mode: str
    start: int
    end: int
    original_hash: str


class DocumentOut(BaseModel):
    id: str
    report_id: str
    file_name: str
    file_type: str
    stage: str
    mineral: str
    year: int | None
    region: str | None
    status: str
    parse_mode: str | None
    redaction_summary: str | None
    review_note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: str
    document_id: str | None
    run_type: str
    status: str
    detail: str | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}
