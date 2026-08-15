"""Collab Workspace — SQLAlchemy 模型（7 张新表，完全独立）。

EAI-CUSTOM: 全新模块，零引用 extensions/project/workflow/approval。
复用共享底座：ai_documents / collab_documents / collab_versions 数据表（docmgr），
但本项目不 import docmgr service（其内部 import ProjectMember）。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ── collab_projects ──


class CollabProject(Base):
    """协作项目 — 完全自足（quickdoc 单文档 / report 多章节）。"""

    __tablename__ = "collab_projects"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'quickdoc' AND doc_id IS NOT NULL) OR (kind = 'report')",
            name="ck_collab_projects_kind_doc",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="quickdoc")  # quickdoc|report
    doc_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_documents.id", ondelete="SET NULL"), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    tier_state: Mapped[str] = mapped_column(String(20), nullable=False, default="tier1")  # tier1|tier2|tier3 (derived cache)
    tier_signals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")  # active|submitted_for_release|released|archived
    compliance_pin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)  # 多租户预留，恒 NULL
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


# ── collab_sections ──


class CollabSection(Base):
    """report 章节模型 — 全新，非 project_chapters。"""

    __tablename__ = "collab_sections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collab_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending|draft|in_review|completed|deleted
    doc_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_documents.id", ondelete="SET NULL"), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 内容乐观锁
    word_count_target: Mapped[int] = mapped_column(Integer, nullable=False, default=3000)
    word_count_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


# ── collab_members ──


class CollabMember(Base):
    """项目成员（human/agent 判别）。S1 信号数据源。"""

    __tablename__ = "collab_members"
    __table_args__ = (
        CheckConstraint(
            "(member_type = 'human' AND user_id IS NOT NULL AND agent_name IS NULL) OR (member_type = 'agent' AND agent_name IS NOT NULL AND user_id IS NULL)",
            name="ck_collab_members_type",
        ),
        UniqueConstraint("project_id", "member_type", "user_id", "agent_name", name="uq_collab_members_proj_type_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collab_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    member_type: Mapped[str] = mapped_column(String(10), nullable=False)  # human|agent
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="editor")  # owner|editor|reviewer|coordinator
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


# ── collab_tasks ──


class CollabTask(Base):
    """通用任务 — 人/agent 指派。"""

    __tablename__ = "collab_tasks"
    __table_args__ = (
        CheckConstraint(
            "assignee_type IS NULL OR (assignee_type = 'human' AND assignee_user_id IS NOT NULL AND assignee_agent_name IS NULL) OR (assignee_type = 'agent' AND assignee_agent_name IS NOT NULL AND assignee_user_id IS NULL)",
            name="ck_collab_tasks_assignee",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collab_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="section_write")  # section_write|doc_review|research
    assignee_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # human|agent|NULL(未指派)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    assignee_agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending|in_progress|done|blocked
    section_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("collab_sections.id", ondelete="SET NULL"), nullable=True)
    doc_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_documents.id", ondelete="SET NULL"), nullable=True)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    handoff_state: Mapped[str | None] = mapped_column(String(20), nullable=True)  # acked|progress|done|blocked
    handoff_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


# ── collab_gates ──


class CollabGate(Base):
    """闸门原语 — 稳定 ID + fail-closed + 审计。"""

    __tablename__ = "collab_gates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collab_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("collab_tasks.id", ondelete="SET NULL"), nullable=True)
    scope: Mapped[str] = mapped_column(String(30), nullable=False, default="task")  # task|project_release
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending|approved|rejected
    mode: Mapped[str] = mapped_column(String(30), nullable=False, default="all_must_approve")
    participants: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # [{type, user_id|agent_name, weight}]
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    escalation_rule: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {after_days, action}
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    audit: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    propagated_to: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


# ── collab_agent_runs ──


class CollabAgentRun(Base):
    """agent 执行桥审计。"""

    __tablename__ = "collab_agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("collab_tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collab_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    thread_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="spawned")  # spawned|running|success|failed|timed_out
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    max_duration: Mapped[int] = mapped_column(Integer, nullable=False, default=1800)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ── collab_activity ──


class CollabActivity(Base):
    """执行桥 provenance — 任务/run/闸门/文档动作审计。"""

    __tablename__ = "collab_activity"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collab_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False, default="human")  # human|agent
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
