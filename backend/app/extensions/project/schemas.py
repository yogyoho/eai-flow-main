"""Pydantic schemas for report project management."""

from datetime import datetime
from pydantic import BaseModel, Field


# ── Project ──


class ProjectMemberIn(BaseModel):
    user_id: str
    role: str


class ProjectCreate(BaseModel):
    name: str
    report_type: str
    client: str
    target_standard: str | None = None
    template_id: str | None = None
    compliance_rule_set_id: str | None = None
    law_ids: list[str] | None = None
    members: list[ProjectMemberIn] | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    client: str | None = None
    target_standard: str | None = None
    status: str | None = None
    compliance_rule_set_id: str | None = None
    law_ids: list[str] | None = None


class ProjectMemberOut(BaseModel):
    user_id: str
    username: str = ""
    role: str
    chapter_assignments: list[str] = Field(default_factory=list)
    avatar_url: str | None = None


class OutlineNode(BaseModel):
    id: str
    project_id: str
    parent_id: str | None = None
    title: str
    order: int = 0
    status: str = "not_started"
    assignee_id: str | None = None
    assignee_name: str | None = None
    word_count_target: int = 3000
    word_count_current: int = 0
    description: str = ""


class MilestoneOut(BaseModel):
    id: str
    project_id: str
    name: str
    due_date: str
    completed_at: str | None = None
    status: str = "pending"


class ProjectOut(BaseModel):
    id: str
    name: str
    report_type: str
    client: str
    target_standard: str = ""
    status: str = "planning"
    template_id: str | None = None
    compliance_rule_set_id: str | None = None
    law_ids: list[str] = Field(default_factory=list)
    members: list[ProjectMemberOut] = Field(default_factory=list)
    outline: dict | None = None
    milestones: list[MilestoneOut] = Field(default_factory=list)
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""


class ProjectListResponse(BaseModel):
    items: list[ProjectOut] = Field(default_factory=list)


class OutlineListResponse(BaseModel):
    items: list[OutlineNode] = Field(default_factory=list)


class OutlineUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    assignee_id: str | None = None
    word_count_target: int | None = None
    word_count_current: int | None = None
    description: str | None = None


class MilestoneListResponse(BaseModel):
    items: list[MilestoneOut] = Field(default_factory=list)


class MemberCreate(BaseModel):
    user_id: str
    role: str
