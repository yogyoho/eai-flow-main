"""Pydantic schemas for approval workflow."""

from pydantic import BaseModel, Field


class ApprovalStepOut(BaseModel):
    id: str
    workflow_id: str
    order: int
    name: str
    required_role: str
    can_reject: bool = True
    parallel: bool = False


class ApprovalWorkflowOut(BaseModel):
    id: str
    name: str
    report_type: str
    steps: list[ApprovalStepOut] = Field(default_factory=list)
    is_default: bool = False


class SubmitApprovalRequest(BaseModel):
    project_id: str
    chapter_ids: list[str] | None = None


class ApprovalActionRequest(BaseModel):
    project_id: str
    step_id: str
    chapter_id: str | None = None
    action: str  # approve / reject / comment
    comment: str | None = None


class ApprovalRecordOut(BaseModel):
    id: str
    project_id: str
    step_id: str
    chapter_id: str | None = None
    reviewer_id: str
    reviewer_name: str = ""
    action: str
    comment: str = ""
    acted_at: str


class ApprovalRecordListResponse(BaseModel):
    items: list[ApprovalRecordOut] = Field(default_factory=list)
