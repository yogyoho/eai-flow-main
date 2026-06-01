"""Pydantic schemas for project timeline."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel


class TimelineEntryBase(BaseModel):
    phase_node: str
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    depends_on: list[str] | None = None
    milestones: list[dict] | None = None
    progress_pct: int = 0
    owner_id: UUID | None = None


class TimelineEntryCreate(TimelineEntryBase):
    pass


class TimelineEntryUpdate(BaseModel):
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    depends_on: list[str] | None = None
    milestones: list[dict] | None = None
    progress_pct: int | None = None
    owner_id: UUID | None = None


class TimelineEntryOut(TimelineEntryBase):
    id: UUID
    project_id: UUID

    model_config = {"from_attributes": True}


class TimelineListResponse(BaseModel):
    entries: list[TimelineEntryOut]


class MilestoneCreate(BaseModel):
    label: str
    target_date: date | None = None
    status: str = "pending"


class MilestoneUpdate(BaseModel):
    label: str | None = None
    target_date: date | None = None
    status: str | None = None
