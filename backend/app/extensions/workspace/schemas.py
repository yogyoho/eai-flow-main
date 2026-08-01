"""Collab Workspace — Pydantic schemas。

EAI-CUSTOM: 全新模块。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Project ──


class CollabProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    kind: str = Field("quickdoc", pattern="^(quickdoc|report)$")


class CollabProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    compliance_pin: bool | None = None
    status: str | None = Field(None, pattern="^(active|submitted_for_release|released|archived)$")


class CollabProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    kind: str
    doc_id: UUID | None = None
    owner_id: UUID | None = None
    tier_state: str
    tier_signals: list | None = None
    escalated_at: datetime | None = None
    status: str
    compliance_pin: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    section_count: int = 0
    member_count: int = 0
    task_count: int = 0


class CollabProjectTierOut(BaseModel):
    project_id: UUID
    tier_state: str
    escalated_at: datetime | None = None
    signals: list | None = None


# ── Section ──


class CollabSectionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    parent_id: UUID | None = None
    word_count_target: int = Field(3000, ge=0)


class CollabSectionUpdate(BaseModel):
    title: str | None = Field(None, max_length=500)
    status: str | None = Field(None, pattern="^(pending|draft|in_review|completed|deleted)$")


class CollabSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    parent_id: UUID | None = None
    title: str
    level: int
    sort_order: int
    status: str
    doc_id: UUID | None = None
    content: str | None = None
    revision: int
    word_count_target: int
    word_count_current: int
    children: list["CollabSectionOut"] = Field(default_factory=list)


# ── Member ──


class CollabMemberCreate(BaseModel):
    member_type: str = Field(..., pattern="^(human|agent)$")
    user_id: UUID | None = None
    agent_name: str | None = None
    role: str = Field("editor", pattern="^(owner|editor|reviewer|coordinator)$")

    @field_validator("member_type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        return v


class CollabMemberUpdate(BaseModel):
    role: str | None = Field(None, pattern="^(owner|editor|reviewer|coordinator)$")


class CollabMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    member_type: str
    user_id: UUID | None = None
    agent_name: str | None = None
    role: str
    joined_at: datetime | None = None


# ── Task ──


class CollabTaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    kind: str = Field("section_write", pattern="^(section_write|doc_review|research)$")
    section_ref: UUID | None = None
    doc_id: UUID | None = None
    context: dict | None = None
    due_at: datetime | None = None


class CollabTaskAssign(BaseModel):
    assignee_type: str = Field(..., pattern="^(human|agent)$")
    user_id: UUID | None = None
    agent_name: str | None = None


class CollabTaskUpdate(BaseModel):
    title: str | None = None
    status: str | None = Field(None, pattern="^(pending|in_progress|done|blocked)$")
    context: dict | None = None


class CollabTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str
    kind: str
    assignee_type: str | None = None
    assignee_user_id: UUID | None = None
    assignee_agent_name: str | None = None
    status: str
    section_ref: UUID | None = None
    doc_id: UUID | None = None
    context: dict | None = None
    handoff_state: str | None = None
    handoff_payload: dict | None = None
    thread_id: str | None = None
    run_id: str | None = None
    attempt_count: int = 0
    last_error: str | None = None
    revision: int = 0
    due_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── Gate ──


class CollabGateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    task_id: UUID | None = None
    scope: str
    state: str
    mode: str
    participants: list | None = None
    deadline_at: datetime | None = None
    escalation_rule: dict | None = None
    resolved_by: UUID | None = None
    resolved_at: datetime | None = None
    audit: list | None = None
    revision: int = 0
    created_at: datetime | None = None


class CollabGateJudge(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|comment)$")
    comment: str | None = None


# ── Agent run ──


class CollabRunSpawn(BaseModel):
    """spawn agent run for a task. agent_name from task assignee or explicit."""
    agent_name: str | None = None
    prompt_override: str | None = None


class CollabAgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID | None = None
    project_id: UUID
    thread_id: str | None = None
    run_id: str | None = None
    agent_name: str
    status: str
    result: dict | None = None
    max_duration: int
    started_at: datetime | None = None
    finished_at: datetime | None = None


# ── Activity ──


class CollabActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    actor_type: str
    actor_id: str | None = None
    action: str
    target: str | None = None
    detail: dict | None = None
    created_at: datetime | None = None
