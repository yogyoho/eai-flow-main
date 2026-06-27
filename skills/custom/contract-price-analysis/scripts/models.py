"""SQLAlchemy ORM for cpa_ tables (v2: MinIO-backed documents).

Mirrors backend/app/extensions/contract_price/models.py — keep the two in sync
(they share the same physical tables via separate Base).

v2 changes vs v1:
  CpaDocument: drop ragflow_doc_id; add file_name / storage_uri (s3://bucket/key,
    unique) / file_hash (SHA-256, exact increment) / file_type / quick_fp /
    parse_meta (JSONB health report) / error / page_count / page_sizes /
    preview_prefix (MinIO previews/{doc_id}/).
  CpaItem: add source_page / source_bbox / source_table_idx / source_row_idx
    (traceability from OCR bbox) + confidence / validation_status.
"""

import uuid
from datetime import date, datetime, timezone
from typing import Optional

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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class CpaDocument(Base):
    """A contract file stored in the independent MinIO bucket."""

    __tablename__ = "cpa_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    storage_uri: Mapped[str] = mapped_column(String(512), unique=True)  # s3://bucket/key
    file_name: Mapped[str] = mapped_column(String(300))
    file_hash: Mapped[str] = mapped_column(String(128), index=True)     # SHA-256
    file_type: Mapped[str] = mapped_column(String(20))                  # pdf / docx
    quick_fp: Mapped[Optional[str]] = mapped_column(String(256))        # name|size fast prefilter
    contract_no: Mapped[Optional[str]] = mapped_column(String(100))
    supplier: Mapped[Optional[str]] = mapped_column(String(200))
    project_name: Mapped[Optional[str]] = mapped_column(String(300))      # 项目/工程名称(首页OCR正则)
    project_location: Mapped[Optional[str]] = mapped_column(String(300))  # 项目所在地/工程地点
    sign_date: Mapped[Optional[date]] = mapped_column()
    parse_mode: Mapped[str] = mapped_column(String(20))                 # ocr / docx / failed
    parse_status: Mapped[str] = mapped_column(String(20))               # pending/parsed/failed/needs_review
    parse_meta: Mapped[Optional[dict]] = mapped_column(JSONB)           # tables_found/goods_tables/...
    error: Mapped[Optional[str]] = mapped_column(Text)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    page_sizes: Mapped[Optional[list]] = mapped_column(JSONB)
    preview_prefix: Mapped[Optional[str]] = mapped_column(String(512))  # previews/{doc_id}/
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    parsed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
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
    spec_model: Mapped[Optional[str]] = mapped_column(String(300))
    tech_params: Mapped[Optional[dict]] = mapped_column(JSONB)
    quantity: Mapped[Optional[float]] = mapped_column(Numeric(18, 3))
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 2))  # 含税单价(统计用)
    price_untaxed: Mapped[Optional[float]] = mapped_column(Numeric(18, 2))  # 不含税单价(审计)
    cluster_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cpa_clusters.id")
    )
    source_contract_no: Mapped[Optional[str]] = mapped_column(String(100))
    is_outlier: Mapped[bool] = mapped_column(Boolean, default=False)
    # ── traceability (OCR bbox byproduct; normalized 0~1 vs page) ──
    source_page: Mapped[Optional[int]] = mapped_column(Integer)
    source_bbox: Mapped[Optional[list]] = mapped_column(JSONB)
    source_table_idx: Mapped[Optional[int]] = mapped_column(Integer)
    source_row_idx: Mapped[Optional[int]] = mapped_column(Integer)
    # ── validation ──
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    validation_status: Mapped[str] = mapped_column(
        String(20), default="ok"
    )  # ok / needs_review / corrected
    edit_note: Mapped[Optional[str]] = mapped_column(Text)
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
    stats: Mapped[Optional[dict]] = mapped_column(JSONB)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(100))
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
    scope: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))
    docs_processed: Mapped[int] = mapped_column(Integer, default=0)
    items_extracted: Mapped[int] = mapped_column(Integer, default=0)
    clusters_formed: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    excel_path: Mapped[Optional[str]] = mapped_column(String(500))
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
