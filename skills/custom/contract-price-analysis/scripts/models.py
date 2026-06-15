"""SQLAlchemy ORM models for cpa_ tables (PostgreSQL postgres-ext).

Tables are prefixed with ``cpa_`` to stay physically isolated from the
procurement-service schema while sharing the same ``postgres-ext`` database.
"""

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
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
    """Cached contract document metadata pulled from RAGFlow."""

    __tablename__ = "cpa_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ragflow_doc_id: Mapped[str] = mapped_column(String(128), unique=True)
    doc_hash: Mapped[str] = mapped_column(String(128), index=True)
    contract_no: Mapped[Optional[str]] = mapped_column(String(100))
    supplier: Mapped[Optional[str]] = mapped_column(String(200))
    sign_date: Mapped[Optional[date]] = mapped_column()
    parse_mode: Mapped[str] = mapped_column(String(20))  # table/list/mixed
    parse_status: Mapped[str] = mapped_column(String(20))  # pending/parsed/failed
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    parsed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now
    )


class CpaItem(Base):
    """A single extracted line-item price from a contract."""

    __tablename__ = "cpa_items"
    __table_args__ = (
        Index("ix_cpa_items_cluster", "cluster_id"),
        Index("ix_cpa_items_contract", "source_contract_no"),
        Index("ix_cpa_items_goods", "goods_name"),
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
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 2))
    cluster_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cpa_clusters.id")
    )
    source_contract_no: Mapped[Optional[str]] = mapped_column(String(100))
    is_outlier: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CpaCluster(Base):
    """A user-reviewed group of goods treated as the same product."""

    __tablename__ = "cpa_clusters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category: Mapped[str] = mapped_column(String(50))  # 设备/物资/配件/...
    representative_name: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/confirmed/rejected
    stats: Mapped[Optional[dict]] = mapped_column(JSONB)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic lock
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now
    )


class CpaRunHistory(Base):
    """Record of each pipeline run (manual or scheduled)."""

    __tablename__ = "cpa_run_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trigger_type: Mapped[str] = mapped_column(String(20))  # manual/scheduled
    scope: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))  # running/completed/failed
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
