# backend/app/extensions/bid_materials/schemas.py
"""投标资料管理 Pydantic 契约(形态镜像 eia_samples/schemas.py)。"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, Field

QualType = Literal["营业执照", "CMMI", "ISO9001", "ISO27001", "业绩证明", "软件著作权", "高新技术企业", "其他"]


class QualificationCreate(BaseModel):
    qual_type: QualType
    cert_no: str = Field(min_length=1, max_length=200)
    issuer: str | None = None
    valid_until: datetime.date | None = None
    scope: str | None = None
    org_scope: str | None = None
    notes: str | None = None


class QualificationUpdate(BaseModel):
    qual_type: QualType | None = None
    cert_no: str | None = Field(default=None, min_length=1, max_length=200)
    issuer: str | None = None
    valid_until: datetime.date | None = None
    scope: str | None = None
    org_scope: str | None = None
    notes: str | None = None
    disabled: bool | None = None


class QualificationVersionResponse(BaseModel):
    version: int
    sha256: str
    file_ext: str
    file_size: int
    note: str | None
    uploaded_at: datetime.datetime


class QualificationResponse(BaseModel):
    id: uuid.UUID
    qual_type: str
    cert_no: str
    issuer: str | None
    valid_until: datetime.date | None
    scope: str | None
    current_version: int
    org_scope: str | None
    disabled: bool
    notes: str | None
    versions: list[QualificationVersionResponse] = []


class WhitelistEntry(BaseModel):
    """entities_whitelist 增量条目(证号=WP-2.4 组织级权威源)。"""

    type: Literal["company", "person"]
    value: str
    cert_no: str | None = None
    valid_until: str | None = None


class SampleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    source_path: str = Field(min_length=1, max_length=1000)
    file_hash: str = Field(min_length=64, max_length=64)
    industry: str = Field(default="other", max_length=50)
    project_category: str = Field(default="IT软件平台", max_length=50)
    scenario: str = "bid_sample"
    status: str = "indexed"
    notes: str | None = None


class SampleBulkItem(SampleCreate):
    pass


class SampleBulkImportRequest(BaseModel):
    items: list[SampleBulkItem] = Field(min_length=1)


class SampleResponse(BaseModel):
    id: uuid.UUID
    title: str
    source_path: str
    file_hash: str
    industry: str
    project_category: str
    scenario: str
    status: str
    notes: str | None
