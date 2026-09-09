# backend/app/extensions/bid_materials/schemas.py
"""投标资料管理 Pydantic 契约(形态参考 eia_samples/schemas.py)。"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, Field

QualType = Literal["营业执照", "CMMI", "ISO9001", "ISO27001", "业绩证明", "软件著作权", "高新技术企业", "其他"]


class QualificationCreate(BaseModel):
    qual_type: QualType
    cert_no: str = Field(min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    valid_until: datetime.date | None = None
    scope: str | None = Field(default=None, max_length=500)
    org_scope: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class QualificationUpdate(BaseModel):
    qual_type: QualType | None = None
    cert_no: str | None = Field(default=None, min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    valid_until: datetime.date | None = None
    scope: str | None = Field(default=None, max_length=500)
    org_scope: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    disabled: bool | None = None


class QualificationVersionUploadResponse(BaseModel):
    """版本上传响应：created=False 表示 sha256 去重命中（幂等返回既有版）。"""

    created: bool
    version: int
    sha256: str


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

    model_config = {"from_attributes": True}


class WhitelistEntry(BaseModel):
    """entities_whitelist 增量条目(证号=WP-2.4 组织级权威源)。

    valid_until 存字符串: entities_whitelist 为 JSON 线格式故存字符串。
    """

    type: Literal["company", "person"]
    value: str = Field(min_length=1)
    cert_no: str | None = None
    valid_until: str | None = None


class SampleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    source_path: str = Field(min_length=1, max_length=1000)
    file_hash: str = Field(min_length=64, max_length=64)
    industry: str = Field(default="other", max_length=50)
    project_category: str = Field(default="IT软件平台", max_length=50)
    scenario: str = Field(default="bid_sample", max_length=50)  # 值域暂不收枚举，台账自由文本（枚举契约后续统一）
    status: str = Field(default="indexed", max_length=30)  # 值域暂不收枚举，台账自由文本（枚举契约后续统一）
    notes: str | None = None


class SampleBulkItem(SampleCreate):
    pass


class SampleBulkImportRequest(BaseModel):
    items: list[SampleBulkItem] = Field(min_length=1, max_length=500)


class SampleBulkImportResponse(BaseModel):
    created: int
    updated: int
    total: int


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

    model_config = {"from_attributes": True}
