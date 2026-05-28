"""Pydantic schemas for report project management."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Enums ──

VALID_REPORT_TYPES = [
    "environmental_impact",
    "geological_survey",
    "feasibility_study",
    "safety_assessment",
    "energy_assessment",
    "other",
]

VALID_PROJECT_STATUSES = ["active", "completed", "archived"]

VALID_MEMBER_ROLES = ["owner", "member"]

VALID_WORKFLOW_STATUSES = ["pending", "in_progress", "approved", "rejected"]

VALID_APPROVAL_ACTIONS = ["approve", "reject", "comment"]


# ── Chapter (kept for ProjectOut compatibility) ──


class ChapterOut(BaseModel):
    id: UUID
    project_id: UUID
    parent_id: UUID | None = None
    title: str
    level: int = 1
    sort_order: int = 0
    status: str = "pending"
    content: str | None = None
    assigned_to: UUID | None = None
    assigned_name: str | None = None
    word_count_target: int = 3000
    word_count_current: int = 0
    purpose: str | None = None
    generation_hint: str | None = None
    children: list["ChapterOut"] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── Member ──


class MemberOut(BaseModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    username: str = ""
    role: str
    created_at: datetime | None = None


class MemberCreate(BaseModel):
    user_id: UUID
    role: str = "member"


# ── Project ──


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    report_type: str = Field(..., min_length=1)
    template_id: UUID | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    status: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str
    template_id: UUID | None = None
    status: str = "active"
    thread_id: str | None = None
    created_by: UUID | None = None
    members: list[MemberOut] = Field(default_factory=list)
    chapters: list[ChapterOut] = Field(default_factory=list)
    chapter_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str
    status: str = "active"
    template_id: UUID | None = None
    template_name: str | None = None
    chapter_count: int = 0
    member_count: int = 0
    created_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectListItem] = Field(default_factory=list)
    total: int = 0


# ── Approval ──


class ApprovalWorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    step_order: int
    step_name: str
    role_required: str
    status: str = "pending"


class ApprovalRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    chapter_id: UUID | None = None
    action: str
    reviewer_id: UUID
    reviewer_name: str = ""
    comment: str | None = None
    created_at: datetime | None = None


class ApprovalActionRequest(BaseModel):
    workflow_id: UUID
    chapter_id: UUID | None = None
    action: str = Field(..., pattern="^(approve|reject|comment)$")
    comment: str | None = None


class ApprovalStepConfig(BaseModel):
    step_order: int
    step_name: str
    reviewer_id: UUID


class ApprovalSubmitRequest(BaseModel):
    steps: list[ApprovalStepConfig]


class ApprovalWorkflowWithRecords(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    step_order: int
    step_name: str
    reviewer_id: UUID | None = None
    role_required: str
    status: str
    records: list[ApprovalRecordOut] = Field(default_factory=list)


class ApprovalStatusOut(BaseModel):
    project_id: UUID
    current_step: int | None
    total_steps: int
    steps: list[ApprovalWorkflowWithRecords]
    all_approved: bool
