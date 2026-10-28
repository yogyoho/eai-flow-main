"""投标审查子系统 ORM(五张表;新表走 create_all,无需 alembic)。

A8(评审修正):ReviewIssue.verdict 与 ReviewFeedback.action 列一律 String(20)——
false_positive=14 / severity_change=15 溢出 String(12),PostgreSQL 超宽报错不截断。
列类型用可移植 JSON(非 JSONB):Task 7 单测以 sqlite+aiosqlite 内存库直跑。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class ReviewTask(Base):
    __tablename__ = "bid_review_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="created", index=True)  # created|parsing|extracting|awaiting_confirm|running|done|failed
    mode: Mapped[str] = mapped_column(String(10), default="quick")  # quick|deep
    progress: Mapped[dict] = mapped_column(JSON, default=dict)  # {stage, pct, msg}
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine_meta: Mapped[dict] = mapped_column(JSON, default=dict)  # {model, prompt_version, materials_hash}
    prev_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # v2 差异审查
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BaselinePackage(Base):
    __tablename__ = "bid_review_baselines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("bid_review_tasks.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # tender|bid
    payload: Mapped[dict] = mapped_column(JSON)  # clauses 同构 + field_snapshot
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)  # 人工确认门
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ReviewIssue(Base):
    __tablename__ = "bid_review_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("bid_review_tasks.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(10), index=True)
    layer: Mapped[str] = mapped_column(String(2))
    severity: Mapped[str] = mapped_column(String(8))  # fatal|major|minor|info
    verdict: Mapped[str] = mapped_column(String(20))  # violation|need_human|unclear;人工复核回写(false_positive 等,A8)也落本列
    clause_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    fix: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSON, default=list)  # [{doc_id,page,section_path,text}]
    dedup_key: Mapped[str] = mapped_column(String(256), index=True)
    need_human: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RulePackMeta(Base):
    __tablename__ = "bid_review_rulepacks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(64), unique=True)  # bid-review-core
    version: Mapped[str] = mapped_column(String(16))
    stats: Mapped[dict] = mapped_column(JSON, default=dict)  # {rule_id: {hit, fp, adopted}}
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class ReviewFeedback(Base):
    __tablename__ = "bid_review_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    issue_id: Mapped[str] = mapped_column(String(36), ForeignKey("bid_review_issues.id"), index=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(20))  # confirm|false_positive|severity_change(A8:String(20))
    new_severity: Mapped[str | None] = mapped_column(String(8), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
