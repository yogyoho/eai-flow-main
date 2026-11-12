"""bid_write ORM 模型(批十九 T2,EAI-CUSTOM 2026-11-13)——与 bid_review/models.py
同构镜像(status 状态机+progress+engine_meta JSON);表经 create_all 承接(gateway
启动序 init_db → 本模块经 routers import 注册 metadata,同 bid_review 机制)。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _id() -> str:
    import uuid

    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class WriteTask(Base):
    """商务写作任务(F1 解析→响应矩阵;生成/预审查面 M1/M2 扩状态)。status:
    created|parsing|extracting|matrix_ready|failed(与 bid_review 状态机同形,
    无 awaiting_confirm——矩阵确认走行级 PATCH 卡点,非任务级门)。"""

    __tablename__ = "bid_write_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="created", index=True)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)  # {stage, pct, msg}
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine_meta: Mapped[dict] = mapped_column(JSON, default=dict)  # {docs, schema_version, model…}
    biz_no: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # TBW-YYYYMMDD-NNNN
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lot_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tender_no: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class MatrixRow(Base):
    """响应矩阵行(F1;设计稿 §四 response_matrix[];(task_id, clause_id) 唯一)。
    strategy/status 人工经 PATCH 卡点推进;conf/verified=抽取置信快照(extract
    fields_conf 同源),blocked=低置信未确认禁入生成(F1 强制标红语义)。"""

    __tablename__ = "bid_write_matrix_rows"
    __table_args__ = (UniqueConstraint("task_id", "clause_id", name="uq_bid_write_matrix_task_clause"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("bid_write_tasks.id"), index=True)
    clause_id: Mapped[str] = mapped_column(String(120))  # 确定性键(matrix.assemble 生成)
    kind: Mapped[str] = mapped_column(String(16))  # ROW_KINDS: attachment|clause|aggregate
    source_path: Mapped[str] = mapped_column(String(80))  # tender.* 路径(contracts.COMMERCIAL_TENDER_SUBSET)
    requirement: Mapped[str] = mapped_column(Text, default="")  # 要求原文摘录(只抄不编)
    star: Mapped[bool] = mapped_column(Boolean, default=False)  # ★条款(禁负偏离直通)
    strategy: Mapped[str] = mapped_column(String(12), default="pending")  # MATRIX_STRATEGIES
    target_section: Mapped[str] = mapped_column(String(120), default="")  # 目标章节(M1 装配消费)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)  # [{path,quote,page}]/素材 ID(P1)
    status: Mapped[str] = mapped_column(String(12), default="draft")  # MATRIX_STATUSES
    conf: Mapped[float | None] = mapped_column(Float, nullable=True)  # 模型自报置信(null=未报)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)  # quote 服务端核验(extract.verify_quotes)
    note: Mapped[str] = mapped_column(Text, default="")  # 人工备注(PATCH 卡点 note)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
