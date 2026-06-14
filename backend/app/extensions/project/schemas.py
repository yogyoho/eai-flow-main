"""Pydantic schemas for report project management."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Enums ──

# Report types are now managed via the business_dictionaries table (category="report_type")
# and enforced by the frontend dropdown. No hardcoded validation list — the DB is the source of truth.

VALID_PROJECT_STATUSES = ["setup", "outline", "writing", "editing", "approval", "in_progress", "active", "completed", "archived"]

VALID_MEMBER_ROLES = ["owner", "manager", "editor", "reviewer", "approver", "member"]

VALID_WORKFLOW_STATUSES = ["pending", "in_progress", "approved", "rejected"]

VALID_APPROVAL_ACTIONS = ["approve", "reject", "comment"]

VALID_DUTY_KEYS = {"leader", "writer", "dept_reviewer", "company_reviewer", "lead", "reviewer", "approver", "data_reviewer", "write"}


# ── State transitions ──

VALID_STATE_TRANSITIONS: dict[str, set[str]] = {
    "setup": {"outline", "active", "in_progress"},
    "outline": {"writing", "setup"},
    "writing": {"editing", "setup"},
    "editing": {"approval", "writing", "setup"},
    "approval": {"completed", "editing"},
    "in_progress": {"editing", "approval", "completed", "active"},
    "active": {"setup", "in_progress", "completed", "archived"},
    "completed": {"archived", "setup"},
    "archived": {"setup"},
}


def validate_status_transition(current: str, target: str) -> str | None:
    """Return error message if transition is invalid, None if valid.

    Admin/bypass callers can ignore the result; this is a guard for
    normal state-machine progression.
    """
    if target not in VALID_PROJECT_STATUSES:
        return f"Unknown status: {target!r}"
    allowed = VALID_STATE_TRANSITIONS.get(current, set())
    if target not in allowed:
        return f"Cannot transition from {current!r} to {target!r}"
    return None


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


class MemberUpdate(BaseModel):
    role: str | None = None
    phase_duties: dict | None = None


# ── Project ──


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    report_type: str = Field(..., min_length=1, max_length=100)
    template_id: UUID | None = None
    workflow_id: UUID | None = None
    auto_start_workflow: bool = False
    members: list["MemberWithDuties"] | None = None


class MemberWithDuties(BaseModel):
    """A member to add during project creation, with optional org unit and phase duties."""

    user_id: UUID
    role: str = "member"
    source_org_unit_id: UUID | None = None
    phase_duties: dict | None = None

    @field_validator("phase_duties")
    @classmethod
    def validate_phase_duties(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        for node_id, duties in v.items():
            if not isinstance(duties, dict):
                raise ValueError(f"phase_duties[{node_id!r}] must be a dict, got {type(duties).__name__}")
            duty = duties.get("duty")
            if duty is not None and duty not in VALID_DUTY_KEYS:
                raise ValueError(
                    f"phase_duties[{node_id!r}].duty = {duty!r} is not valid. "
                    f"Expected one of: {sorted(VALID_DUTY_KEYS)}"
                )
        return v


class ProjectCopyFrom(BaseModel):
    """Request to create a new project by copying from an existing one."""
    name: str = Field(..., min_length=1, max_length=255)
    source_project_id: UUID
    copy_members: bool = True
    copy_outline: bool = True
    copy_workflow: bool = True


# Resolve forward references
ProjectCreate.model_rebuild()


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    status: str | None = None
    workflow_id: UUID | None = None
    current_phase_node: str | None = None


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
    workflow_id: UUID | None = None
    temporal_workflow_id: str | None = None
    current_phase_node: str | None = None


class ProjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str
    status: str = "active"
    template_id: UUID | None = None
    template_name: str | None = None
    chapter_count: int = 0
    completed_chapter_count: int = 0
    progress_percentage: float = 0.0
    member_count: int = 0
    created_by: UUID | None = None
    created_by_name: str | None = None
    created_by_dept: str | None = None
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


# ── Project Permissions ──


class ProjectPermissionsOut(BaseModel):
    """User's effective permissions within a project."""
    role: str | None = None
    permissions: list[str] = Field(default_factory=list)
    phase_duties: dict | None = None
    is_admin: bool = False


# ── Phase Board ──


class PhaseBoardChapter(BaseModel):
    """A chapter in the phase board view."""

    id: UUID
    title: str
    status: str = "pending"
    assigned_to: UUID | None = None
    assigned_name: str | None = None
    level: int = 1
    sort_order: int = 0
    word_count_target: int = 3000
    word_count_current: int = 0


class PhaseBoardMember(BaseModel):
    """A project member with duties for this phase."""

    user_id: UUID
    username: str = ""
    role: str
    duty: str | None = None  # lead / writer / reviewer — from phase_duties


class PhaseBoardResponse(BaseModel):
    """Phase board data: chapters + members + review summary."""

    phase_node: str
    phase_label: str = ""
    chapters: list[PhaseBoardChapter] = Field(default_factory=list)
    members: list[PhaseBoardMember] = Field(default_factory=list)
    total_chapters: int = 0
    completed_chapters: int = 0


class BatchAssignRequest(BaseModel):
    """Batch assign chapters to users."""

    assignments: list[dict] = Field(
        ...,
        description="List of {chapter_id: UUID, assigned_to: UUID | None}",
    )


# ── Phase Readiness ──


class PhaseReadinessResponse(BaseModel):
    """Phase readiness check result."""

    ready: bool
    phase_node: str
    phase_label: str = ""
    filled_roles: list[dict] = Field(default_factory=list)
    missing_roles: list[dict] = Field(default_factory=list)
    suggested_members: list[dict] = Field(default_factory=list)
    error: str | None = None
