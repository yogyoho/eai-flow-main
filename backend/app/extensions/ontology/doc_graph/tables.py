"""doc_graph 表模型（dg_* 前缀, extensions 库, gateway 启动 create_all 自动建表）.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-11-ontology-doc-graph-design.md §4。
双时间（借 Semantica BiTemporalFact 设计）: valid_from/valid_to=业务有效期;
created_at/updated_at + dg_merges 留痕=事务时间。dg_mentions 为证据链（永不删, error 列支持重投）。
"""

import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class DgEntity(Base):
    __tablename__ = "dg_entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(50), index=True)  # 抽取域: bid / contract / ...
    etype: Mapped[str] = mapped_column(String(50), index=True)  # 实体类型: project / bidder / goods / qualification
    canonical_name: Mapped[str] = mapped_column(String(300))
    norm_name: Mapped[str] = mapped_column(String(300))  # 归一化名（幂等 upsert 键的一部分）
    attrs: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=1.0)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | pending_review | merged
    valid_from: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("uq_dg_entities_natural", "domain", "etype", "norm_name", unique=True),)


class DgRelation(Base):
    __tablename__ = "dg_relations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dg_entities.id"), index=True)
    predicate: Mapped[str] = mapped_column(String(100), index=True)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dg_entities.id"), index=True)
    attrs: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=1.0)
    valid_from: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DgMention(Base):
    __tablename__ = "dg_mentions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("dg_entities.id"), index=True)
    relation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("dg_relations.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(100), default="")
    document_id: Mapped[str] = mapped_column(String(200))
    doc_span: Mapped[dict | None] = mapped_column(JSONB)  # {page?, quote_start?, quote_end?}
    quote: Mapped[str | None] = mapped_column(Text)
    extracted_by: Mapped[str] = mapped_column(String(100), default="llm")
    extracted_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    error: Mapped[str | None] = mapped_column(Text)  # 抽取失败留痕（可重投）


class DgMerge(Base):
    __tablename__ = "dg_merges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dg_entities.id"), index=True)
    canonical_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dg_entities.id"), index=True)
    method: Mapped[str] = mapped_column(String(30), default="similarity")  # similarity | manual
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=1.0)
    merged_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
