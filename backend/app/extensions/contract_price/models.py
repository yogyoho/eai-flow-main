"""SQLAlchemy ORM models for the contract-price-analysis ``cpa_`` tables.

These share the Gateway's ``Base`` (``app.extensions.database``) so they are
created at startup alongside the other extension tables, and they reuse the
shared engine pool. The ``cpa_`` prefix keeps them physically isolated from
procurement-service tables in the same ``postgres-ext`` database.

NOTE: the agent skill ``skills/custom/contract-price-analysis/scripts/models.py``
mirrors these definitions (separate Base, same physical tables) so the standalone
pipeline CLI can persist without importing ``app.*``. Keep the two in sync when
changing columns.
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
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CpaDocument(Base):
    __tablename__ = "cpa_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ragflow_doc_id: Mapped[str] = mapped_column(String(128), unique=True)
    doc_hash: Mapped[str] = mapped_column(String(256), index=True)
    contract_no: Mapped[Optional[str]] = mapped_column(String(100))
    supplier: Mapped[Optional[str]] = mapped_column(String(200))
    sign_date: Mapped[Optional[date]] = mapped_column()
    parse_mode: Mapped[str] = mapped_column(String(20))
    parse_status: Mapped[str] = mapped_column(String(20))
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
    is_outlier: Mapped[bool] = mapped_column(Boolean, default=False)
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
