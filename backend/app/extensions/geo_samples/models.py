# EAI-CUSTOM: forked from app.extensions.contract_price/models.py (geo-sample-bank Phase 1, gsb_ 表), spec 2026-09-01.
# gsb_ tables auto-create at gateway startup via shared Base; new columns MUST go
# through database.migrate_db() idempotent ALTER (create_all never adds columns).
"""SQLAlchemy ORM models for the geo-sample-bank ``gsb_`` tables.

Phase 1 资产层:样例报告文档(gsb_documents)、脱敏事件流水(gsb_redactions
—— 只落位置与原文 hash,绝不落明文)、解析/脱敏运行历史(gsb_run_history)。
表在 gateway 启动时随其它扩展表经共享 Base 自动创建;给已有表新增列必须走
database.migrate_db() 的幂等 ALTER(create_all 不会给已存在的表加列)。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class GsbDocument(Base):
    """一份样例报告的资产行。status: uploaded→parsed→redacted→reviewed（Phase 2 追加 compiled）。"""

    __tablename__ = "gsb_documents"

    # String(36) PK (not sibling's UUID(as_uuid=True)): all consumers (routers/schemas/MinIO URIs) treat ids as strings; no cross-family joins exist.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    file_name: Mapped[str] = mapped_column(String(512))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    file_type: Mapped[str] = mapped_column(String(16))  # docx / pdf
    stage: Mapped[str] = mapped_column(String(16), default="exploration")  # survey/detail/exploration
    mineral: Mapped[str] = mapped_column(String(32), default="copper")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="uploaded", index=True)
    parse_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)  # docx/pdf_text/pdf_ocr/failed
    raw_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)  # s3://geo-samples/raw/<report_id>/<file>
    work_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)  # s3://geo-samples/work/<report_id>/parsed.md（未脱敏中间件）
    clean_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)  # s3://geo-samples/clean/<report_id>/source.md
    redaction_summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: {rule: count}
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=utc_now)


class GsbRedaction(Base):
    """脱敏事件流水——只落位置与原文 hash，绝不落明文。"""

    __tablename__ = "gsb_redactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # no FK on purpose: audit event log must survive document deletion (retention semantics; cpa sibling uses FK, we intentionally diverge).
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    rule: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))  # auto / review
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    original_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GsbRunHistory(Base):
    __tablename__ = "gsb_run_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # no FK on purpose: audit event log must survive document deletion (retention semantics; cpa sibling uses FK, we intentionally diverge).
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    run_type: Mapped[str] = mapped_column(String(16))  # parse / redact
    status: Mapped[str] = mapped_column(String(16), default="running")  # running/done/failed
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
