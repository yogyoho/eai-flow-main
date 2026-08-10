"""SQLAlchemy ORM models for the contract-price-analysis ``cpa_`` tables.

Mirrors skills/custom/contract-price-analysis/scripts/models.py — same physical
tables, but this one uses the shared ``app.extensions.database`` Base so the
tables auto-create at gateway startup alongside other extension tables. Keep
the two in sync when changing columns.

v2 (MinIO-backed documents):
  CpaDocument: drop ragflow_doc_id; add file_name / storage_uri (unique) /
    file_hash (SHA-256 exact increment) / file_type / quick_fp / parse_meta /
    error / page_count / page_sizes / preview_prefix.
  CpaItem: add source_page / source_bbox / source_table_idx / source_row_idx
    (traceability) + confidence / validation_status.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class CpaDocument(Base):
    __tablename__ = "cpa_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    storage_uri: Mapped[str] = mapped_column(String(512), unique=True)  # s3://bucket/key
    file_name: Mapped[str] = mapped_column(String(300))
    file_hash: Mapped[str] = mapped_column(String(128), index=True)     # SHA-256
    file_type: Mapped[str] = mapped_column(String(20))                  # pdf / docx
    quick_fp: Mapped[str | None] = mapped_column(String(256))        # name|size fast prefilter
    contract_no: Mapped[str | None] = mapped_column(String(100))
    supplier: Mapped[str | None] = mapped_column(String(200))
    project_name: Mapped[str | None] = mapped_column(String(300))      # 项目/工程名称(首页OCR正则)
    project_location: Mapped[str | None] = mapped_column(String(300))  # 项目所在地/工程地点
    sign_date: Mapped[date | None] = mapped_column()
    parse_mode: Mapped[str] = mapped_column(String(20))                 # ocr / docx / failed
    parse_status: Mapped[str] = mapped_column(String(20))               # pending/parsed/failed/needs_review
    confirm_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/confirmed/skipped/clustered
    parse_meta: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    page_sizes: Mapped[list | None] = mapped_column(JSONB)
    preview_prefix: Mapped[str | None] = mapped_column(String(512))
    raw_text: Mapped[str | None] = mapped_column(Text)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now
    )


class CpaItem(Base):
    __tablename__ = "cpa_items"
    __table_args__ = (
        Index("ix_cpa_items_cluster", "cluster_id"),
        Index("ix_cpa_items_contract", "source_contract_no"),
        Index("ix_cpa_items_goods", "goods_name"),
        Index("ix_cpa_items_validation", "validation_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cpa_documents.id"), nullable=False
    )
    goods_name: Mapped[str] = mapped_column(String(300))
    spec_model: Mapped[str | None] = mapped_column(String(300))
    tech_params: Mapped[dict | None] = mapped_column(JSONB)
    quantity: Mapped[float | None] = mapped_column(Numeric(18, 3))
    unit: Mapped[str | None] = mapped_column(String(50))
    unit_price: Mapped[float | None] = mapped_column(Numeric(18, 2))  # 含税单价(统计用)
    price_untaxed: Mapped[float | None] = mapped_column(Numeric(18, 2))  # 不含税单价(审计)
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cpa_clusters.id")
    )
    source_contract_no: Mapped[str | None] = mapped_column(String(100))
    is_outlier: Mapped[bool] = mapped_column(Boolean, default=False)
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_bbox: Mapped[list | None] = mapped_column(JSONB)
    source_table_idx: Mapped[int | None] = mapped_column(Integer)
    source_row_idx: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    validation_status: Mapped[str] = mapped_column(String(20), default="ok")
    edit_note: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cpa_run_history.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CpaCluster(Base):
    __tablename__ = "cpa_clusters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category: Mapped[str] = mapped_column(String(50))
    representative_name: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    stats: Mapped[dict | None] = mapped_column(JSONB)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    confirmed_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now
    )


class CpaRunHistory(Base):
    __tablename__ = "cpa_run_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trigger_type: Mapped[str] = mapped_column(String(20))
    label: Mapped[str | None] = mapped_column(String(100))
    scope: Mapped[dict | None] = mapped_column(JSONB)
    progress: Mapped[dict | None] = mapped_column(JSONB)  # {total,done,failed,phase}
    status: Mapped[str] = mapped_column(String(20))
    docs_processed: Mapped[int] = mapped_column(Integer, default=0)
    items_extracted: Mapped[int] = mapped_column(Integer, default=0)
    clusters_formed: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    excel_path: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
