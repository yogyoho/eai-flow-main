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
    run_type: str  # parse | redact | compile（compile=模块级编译，document_id 为 None）
    status: str
    detail: str | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


# --- ore_pack 孵化（P5 T5）-----------------------------------------------------


class OrePackExtractRequest(BaseModel):
    """LLM 批量抽取请求。mineral 词表校验在路由做（错误文案含「不孵化」裁决说明）；
    slice_paths 上限 20（单请求切片预算）。"""

    mineral: str
    slice_paths: list[str] = Field(min_length=1, max_length=20)


class DraftReviewRequest(BaseModel):
    note: str | None = None
