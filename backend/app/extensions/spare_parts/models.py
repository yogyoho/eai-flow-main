# EAI-CUSTOM: forked from contract_price/models.py (备件价格体系分析 csp_ 表)。
# 与 contract_price 的差异 = 客户维度(customer_id/customer_name + csp_customers 主数据表)。
"""SQLAlchemy ORM models for the spare-parts-analysis ``csp_`` tables.

镜像 skills/public/spare-parts-analysis/scripts/models.py —— 同一套物理表,
但本文件用共享 ``app.extensions.database`` Base,表在 gateway 启动时随其它
扩展表自动创建。改字段时两边保持同步。

与 contract_price (cpa_) 的核心差异(D3 决策):
  - 新增 ``csp_customers`` 客户主数据表(canonical_name + aliases 别名映射),
    用于把 OCR 抽出的脏 customer_name 归一到 customer_id。
  - ``csp_items`` 加 customer_id / customer_name(冗余,便于按客户 GROUP BY 比价)。
  - 备件名归一走 csp_clusters(复用聚类引擎),cluster_id 是跨客户比价键。
  - goods_name → part_name,spec_model → spec(领域术语)。
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


class CspCustomer(Base):
    """客户主数据表(D3):canonical_name 规范名 + aliases 别名列表。

    OCR 抽出的脏 customer_name 经 aliases 匹配得 customer_id;
    未命中 → status=pending,入待确认队列由管理前端人工认领/合并。
    """

    __tablename__ = "csp_customers"
    __table_args__ = (Index("ix_csp_customers_canonical", "canonical_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_name: Mapped[str] = mapped_column(String(200))  # 规范客户名
    aliases: Mapped[list | None] = mapped_column(JSONB)  # ["别名1","别名2",...]
    source: Mapped[str | None] = mapped_column(String(100))  # 来源(master/imported/ocr)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/pending/merged
    merged_into: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("csp_customers.id")
    )  # 合并去向(status=merged 时指向规范客户)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now
    )


class CspDocument(Base):
    """备件合同扫描件。bucket=csp-parts。customer_id 为该合同采购方(需方)。"""

    __tablename__ = "csp_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    storage_uri: Mapped[str] = mapped_column(String(512), unique=True)  # s3://bucket/key
    file_name: Mapped[str] = mapped_column(String(300))
    file_hash: Mapped[str] = mapped_column(String(128), index=True)  # SHA-256 增量去重
    file_type: Mapped[str] = mapped_column(String(20))  # pdf / docx
    quick_fp: Mapped[str | None] = mapped_column(String(256))  # name|size 快速预过滤
    contract_no: Mapped[str | None] = mapped_column(String(100))
    supplier: Mapped[str | None] = mapped_column(String(200))  # 供方/卖方(文档元数据)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("csp_customers.id"), index=True
    )  # 需方/买方 = 分析维度(D3)
    customer_name: Mapped[str | None] = mapped_column(String(200))  # 冗余,OCR 原文
    project_name: Mapped[str | None] = mapped_column(String(300))
    project_location: Mapped[str | None] = mapped_column(String(300))
    sign_date: Mapped[date | None] = mapped_column()
    parse_mode: Mapped[str] = mapped_column(String(20))  # ocr / docx / failed
    parse_status: Mapped[str] = mapped_column(String(20))  # pending/parsed/failed/needs_review
    confirm_status: Mapped[str] = mapped_column(String(20), default="pending")
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


class CspItem(Base):
    """备件明细行。customer_id 从文档继承(冗余,便于按客户聚合比价)。"""

    __tablename__ = "csp_items"
    __table_args__ = (
        Index("ix_csp_items_cluster", "cluster_id"),
        Index("ix_csp_items_customer", "customer_id"),
        Index("ix_csp_items_part", "part_name"),
        Index("ix_csp_items_contract", "source_contract_no"),
        Index("ix_csp_items_validation", "validation_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("csp_documents.id"), nullable=False
    )
    part_name: Mapped[str] = mapped_column(String(300))  # 备件名(脏,经聚类归一)
    spec: Mapped[str | None] = mapped_column(String(300))  # 规格/型号
    tech_params: Mapped[dict | None] = mapped_column(JSONB)
    quantity: Mapped[float | None] = mapped_column(Numeric(18, 3))
    unit: Mapped[str | None] = mapped_column(String(50))
    unit_price: Mapped[float | None] = mapped_column(Numeric(18, 2))  # 含税单价(统计用)
    price_untaxed: Mapped[float | None] = mapped_column(Numeric(18, 2))  # 不含税单价(审计)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("csp_customers.id")
    )  # 从文档继承(D3 分析维度)
    customer_name: Mapped[str | None] = mapped_column(String(200))  # 冗余
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("csp_clusters.id")
    )  # 备件名聚类 → 跨客户比价键
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
        UUID(as_uuid=True), ForeignKey("csp_run_history.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CspCluster(Base):
    """备件名聚类(复用 clustering/engine)。同 cluster = 同一备件。"""

    __tablename__ = "csp_clusters"

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


class CspRunHistory(Base):
    __tablename__ = "csp_run_history"

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
    customers_resolved: Mapped[int] = mapped_column(Integer, default=0)  # 归一命中的客户数
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
