"""投标资料管理数据模型: 资质元数据/资质版本(MinIO)/样例台账。

形态沿用 eia_samples.KFSample（声明式 Base；commit 1ce049220 领域样例库独立应用先例）。
资质文件本体存 MinIO 桶 bid-qualifications（storage.py），行内只存 minio_key/sha256。
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class BidQualification(Base):
    """资质元数据行。文件本体在 MinIO，行内 current_version 指针决定当前版。"""

    __tablename__ = "bid_qualifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    qual_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    cert_no: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    valid_until: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    scope: Mapped[str | None] = mapped_column(String(500), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    org_scope: Mapped[str | None] = mapped_column(String(100), nullable=True)
    disabled: Mapped[bool] = mapped_column(nullable=False, default=False)  # 软删标记
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())


class BidQualificationVersion(Base):
    """资质文件版本行（不可变只追加）。回滚=改 BidQualification.current_version 指针。"""

    __tablename__ = "bid_qualification_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    qualification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bid_qualifications.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    minio_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_ext: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class BidSample(Base):
    """样例台账（沿用 KFSample 形态; 深度地板统一走 depth_targets.json, 册级不存）。"""

    __tablename__ = "bid_samples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    industry: Mapped[str] = mapped_column(String(50), nullable=False, default="other", index=True)
    project_category: Mapped[str] = mapped_column(String(50), nullable=False, default="IT软件平台", index=True)
    scenario: Mapped[str] = mapped_column(String(50), nullable=False, default="bid_sample")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="indexed", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
