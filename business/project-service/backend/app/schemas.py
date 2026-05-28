"""Pydantic Schema 定义"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Project ────────────────────────────────────────────────────────────────────

class ProjectBase(BaseModel):
    project_no: str = Field(..., max_length=50)
    name: str = Field(..., max_length=300)
    project_type: str = Field(..., max_length=50)
    dept_id: Optional[str] = Field(None, max_length=100)
    dept_name: Optional[str] = Field(None, max_length=200)
    manager_id: Optional[str] = Field(None, max_length=100)
    manager_name: Optional[str] = Field(None, max_length=100)
    budget: Optional[Decimal] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    priority: str = "normal"
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=300)
    project_type: Optional[str] = Field(None, max_length=50)
    dept_id: Optional[str] = Field(None, max_length=100)
    dept_name: Optional[str] = Field(None, max_length=200)
    manager_id: Optional[str] = Field(None, max_length=100)
    manager_name: Optional[str] = Field(None, max_length=100)
    budget: Optional[Decimal] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    actual_end_date: Optional[datetime] = None
    progress: Optional[float] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    description: Optional[str] = None


class ProjectResponse(ProjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actual_end_date: Optional[datetime]
    progress: float
    status: str
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int


# ── Milestone ─────────────────────────────────────────────────────────────────

class MilestoneCreate(BaseModel):
    project_id: UUID
    name: str = Field(..., max_length=300)
    description: Optional[str] = None
    due_date: Optional[datetime] = None


class MilestoneUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    status: Optional[str] = None


class MilestoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    name: str
    description: Optional[str]
    due_date: Optional[datetime]
    completed_date: Optional[datetime]
    status: str
    created_at: datetime


class MilestoneListResponse(BaseModel):
    milestones: list[MilestoneResponse]
    total: int


# ── Task ───────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    project_id: UUID
    milestone_id: Optional[UUID] = None
    name: str = Field(..., max_length=300)
    description: Optional[str] = None
    assignee_id: Optional[str] = Field(None, max_length=100)
    assignee_name: Optional[str] = Field(None, max_length=100)
    priority: str = "normal"
    due_date: Optional[datetime] = None


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    assignee_id: Optional[str] = Field(None, max_length=100)
    assignee_name: Optional[str] = Field(None, max_length=100)
    priority: Optional[str] = None
    due_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    progress: Optional[float] = None
    status: Optional[str] = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    milestone_id: Optional[UUID]
    name: str
    description: Optional[str]
    assignee_id: Optional[str]
    assignee_name: Optional[str]
    priority: str
    due_date: Optional[datetime]
    completed_date: Optional[datetime]
    progress: float
    status: str
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int


# ── Resource ───────────────────────────────────────────────────────────────────

class ResourceCreate(BaseModel):
    project_id: UUID
    resource_type: str = Field(..., max_length=30)
    resource_name: str = Field(..., max_length=200)
    quantity: int = 1
    unit_cost: Optional[Decimal] = None
    remark: Optional[str] = None


class ResourceUpdate(BaseModel):
    resource_type: Optional[str] = Field(None, max_length=30)
    resource_name: Optional[str] = Field(None, max_length=200)
    quantity: Optional[int] = None
    unit_cost: Optional[Decimal] = None
    remark: Optional[str] = None


class ResourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    resource_type: str
    resource_name: str
    quantity: int
    unit_cost: Optional[Decimal]
    total_cost: Optional[Decimal]
    remark: Optional[str]
    created_at: datetime


class ResourceListResponse(BaseModel):
    resources: list[ResourceResponse]
    total: int


# ── Risk ───────────────────────────────────────────────────────────────────────

class RiskCreate(BaseModel):
    project_id: UUID
    title: str = Field(..., max_length=300)
    risk_type: str = Field(..., max_length=50)
    severity: str = "medium"
    probability: str = "medium"
    impact: Optional[str] = Field(None, max_length=20)
    mitigation: Optional[str] = None


class RiskUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    risk_type: Optional[str] = Field(None, max_length=50)
    severity: Optional[str] = None
    probability: Optional[str] = None
    impact: Optional[str] = Field(None, max_length=20)
    mitigation: Optional[str] = None
    status: Optional[str] = None


class RiskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    title: str
    risk_type: str
    severity: str
    probability: str
    impact: Optional[str]
    mitigation: Optional[str]
    status: str
    identified_by: Optional[str]
    identified_date: Optional[datetime]
    resolved_date: Optional[datetime]
    created_at: datetime


class RiskListResponse(BaseModel):
    risks: list[RiskResponse]
    total: int


# ── Document ───────────────────────────────────────────────────────────────────

class DocumentCreate(BaseModel):
    project_id: UUID
    title: str = Field(..., max_length=300)
    doc_type: str = Field(..., max_length=50)
    file_url: Optional[str] = Field(None, max_length=500)
    version: str = "1.0"
    remark: Optional[str] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    doc_type: Optional[str] = Field(None, max_length=50)
    file_url: Optional[str] = Field(None, max_length=500)
    version: Optional[str] = Field(None, max_length=20)
    remark: Optional[str] = None


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    title: str
    doc_type: str
    file_url: Optional[str]
    uploaded_by: Optional[str]
    version: str
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


# ── Dashboard ──────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_projects: int
    draft_count: int
    ongoing_count: int
    completed_count: int
    suspended_count: int
    total_budget: Decimal
    total_tasks: int
    pending_tasks: int
    overdue_tasks: int
    high_risks: int
