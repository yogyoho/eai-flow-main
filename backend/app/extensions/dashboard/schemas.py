"""Pydantic schemas for dashboard API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ── Task Items ──


class TaskItem(BaseModel):
    """A single task item in the user's task list."""

    id: str
    type: str  # "review" | "writing" | "phase_lead" | "ai_writing" | "rejection"
    priority_score: int
    project_id: UUID
    project_name: str
    phase_label: str | None = None
    phase_node: str | None = None
    chapter_id: UUID | None = None
    chapter_title: str | None = None
    due_date: datetime | None = None
    is_blocking: bool = False
    is_urgent: bool = False
    action_label: str
    action_url: str


class MyTasksResponse(BaseModel):
    """Response for the my-tasks endpoint."""

    tasks: list[TaskItem] = []
    urgent_count: int = 0
    total_count: int = 0


# ── My Projects ──


class MyProjectItem(BaseModel):
    """A single project in the user's project list."""

    project_id: UUID
    project_name: str
    report_type: str | None = None
    status: str = "setup"
    current_phase: str | None = None
    current_phase_node: str | None = None
    progress_pct: int = 0
    role_label: str  # "owner" | "phase_lead" | "reviewer" | "writer" | "viewer"
    pending_task_count: int = 0
    last_updated: datetime | None = None


class MyProjectsResponse(BaseModel):
    """Response for the my-projects endpoint, grouped by role."""

    groups: dict[str, list[MyProjectItem]] = {}
    total_count: int = 0


# ── My Stats ──


class MyStatsResponse(BaseModel):
    """User's personal statistics."""

    projects_count: int = 0
    pending_reviews: int = 0
    pending_writing: int = 0
    completed_this_week: int = 0
    overdue_count: int = 0


# ── My Calendar ──


class CalendarEvent(BaseModel):
    """A single calendar event."""

    id: str
    title: str
    date: datetime
    type: str  # "deadline" | "milestone" | "phase_start" | "personal"
    project_id: UUID | None = None
    project_name: str | None = None
    color: str = "blue"  # blue | yellow | green | red | purple


class MyCalendarResponse(BaseModel):
    """Response for the my-calendar endpoint."""

    events: list[CalendarEvent] = []


# ── Notifications ──


class NotificationOut(BaseModel):
    """A single notification."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    type: str
    title: str
    body: str | None = None
    project_id: UUID | None = None
    link: str | None = None
    is_read: bool = False
    created_at: datetime | None = None


class NotificationListResponse(BaseModel):
    """Paginated notification list."""

    notifications: list[NotificationOut] = []
    total: int = 0
    unread_count: int = 0


# ── Notification Preferences ──


# Default type settings — all enabled
_DEFAULT_TYPE_SETTINGS = {
    "deadline": True,
    "review_pending": True,
    "phase_start": True,
    "mention": True,
    "assignment": True,
    "workflow_complete": True,
}


class NotificationPreferenceOut(BaseModel):
    """User's notification preferences."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    channel_in_app: bool = True
    channel_email: bool = False
    type_settings: dict = {}
    digest_mode: str = "instant"  # instant | daily | off
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    deadline_remind_days: int = 3
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NotificationPreferenceUpdate(BaseModel):
    """Update notification preferences — all fields optional."""

    channel_in_app: bool | None = None
    channel_email: bool | None = None
    type_settings: dict | None = None
    digest_mode: str | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    deadline_remind_days: int | None = None
