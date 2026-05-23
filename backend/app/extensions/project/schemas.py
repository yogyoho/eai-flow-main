"""Pydantic schemas for report project management (workflow-driven)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Enums (as string literals) ──

VALID_REPORT_TYPES = [
    "environmental_impact",
    "geological_survey",
    "feasibility_study",
    "safety_assessment",
    "energy_assessment",
    "other",
]

VALID_PROJECT_STATUSES = ["setup", "outline", "writing", "editing", "approval", "published", "archived"]

VALID_CHAPTER_STATUSES = ["pending", "writing", "draft", "editing", "completed", "rejected", "approved"]

VALID_MEMBER_ROLES = ["manager", "editor", "reviewer", "approver"]

VALID_WORKFLOW_STATUSES = ["pending", "in_progress", "approved", "rejected"]

VALID_APPROVAL_ACTIONS = ["approve", "reject", "comment"]


# ── Chapter ──


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


class ChapterTreeNode(BaseModel):
    """Flat node for outline tree operations (add/reorder/update)."""
    id: UUID | None = None  # None for new chapters
    title: str
    level: int = 1
    sort_order: int = 0
    purpose: str | None = None
    generation_hint: str | None = None
    word_count_target: int = 3000
    children: list["ChapterTreeNode"] = Field(default_factory=list)


class ChapterContentUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    status: str | None = None
    assigned_to: UUID | None = None
    word_count_target: int | None = None


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
    role: str = "editor"


# ── Project ──


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    report_type: str = Field(..., min_length=1)
    template_id: UUID | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    status: str | None = None
    current_stage: int | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str
    template_id: UUID | None = None
    status: str = "setup"
    current_stage: int = 1
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
    status: str = "setup"
    current_stage: int = 1
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


# ── Outline batch update ──


class OutlineBatchUpdate(BaseModel):
    """Replace the entire outline tree with a new structure."""
    chapters: list[ChapterTreeNode] = Field(default_factory=list)


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


# ── Writing / Editing thread responses ──


class StartWritingResponse(BaseModel):
    """Response for POST /projects/{id}/start-writing."""
    thread_id: str
    project_id: UUID


class StartEditingResponse(BaseModel):
    """Response for POST /projects/{id}/chapters/{ch_id}/start-editing."""
    thread_id: str
    project_id: UUID
    chapter_id: UUID
