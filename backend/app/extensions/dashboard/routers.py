"""Dashboard API routers — task console, projects, stats, calendar, notifications."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

from .schemas import (
    MyCalendarResponse,
    MyProjectsResponse,
    MyStatsResponse,
    MyTasksResponse,
    NotificationListResponse,
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
)
from .service import (
    get_my_calendar,
    get_my_projects,
    get_my_stats,
    get_my_tasks,
    get_notification_preferences,
    get_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    update_notification_preferences,
)
from .reminder_service import check_deadline_reminders

router = APIRouter(prefix="/api/extensions/dashboard", tags=["dashboard"])

DashboardUser = Annotated[CurrentUser, Depends(require_permission("system:access"))]


# ── Task Console ──


@router.get("/my-tasks", response_model=MyTasksResponse)
async def my_tasks_endpoint(
    user: DashboardUser,
    db: AsyncSession = Depends(get_db),
):
    """Get current user's actionable tasks across all projects."""
    return await get_my_tasks(db, user.id)


@router.get("/my-projects", response_model=MyProjectsResponse)
async def my_projects_endpoint(
    user: DashboardUser,
    db: AsyncSession = Depends(get_db),
):
    """Get current user's projects grouped by role."""
    return await get_my_projects(db, user.id)


@router.get("/my-stats", response_model=MyStatsResponse)
async def my_stats_endpoint(
    user: DashboardUser,
    db: AsyncSession = Depends(get_db),
):
    """Get current user's personal statistics."""
    return await get_my_stats(db, user.id)


@router.get("/my-calendar", response_model=MyCalendarResponse)
async def my_calendar_endpoint(
    user: DashboardUser,
    db: AsyncSession = Depends(get_db),
    start: datetime | None = Query(None, description="Start date (ISO 8601)"),
    end: datetime | None = Query(None, description="End date (ISO 8601)"),
):
    """Get calendar events for the current user."""
    events = await get_my_calendar(db, user.id, start, end)
    return MyCalendarResponse(events=events)


# ── Notifications ──


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    user: DashboardUser,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """Get current user's notifications."""
    return await get_notifications(db, user.id, skip, limit)


@router.patch("/notifications/{notification_id}/read")
async def read_notification(
    notification_id: UUID,
    user: DashboardUser,
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    ok = await mark_notification_read(db, notification_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "read"}


@router.post("/notifications/read-all")
async def read_all_notifications(
    user: DashboardUser,
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read."""
    count = await mark_all_notifications_read(db, user.id)
    return {"status": "all_read", "count": count}


# ── Notification Preferences ──


@router.get("/notification-preferences", response_model=NotificationPreferenceOut)
async def get_prefs(
    user: DashboardUser,
    db: AsyncSession = Depends(get_db),
):
    """Get current user's notification preferences (auto-created with defaults)."""
    return await get_notification_preferences(db, user.id)


@router.put("/notification-preferences", response_model=NotificationPreferenceOut)
async def update_prefs(
    body: NotificationPreferenceUpdate,
    user: DashboardUser,
    db: AsyncSession = Depends(get_db),
):
    """Update current user's notification preferences."""
    return await update_notification_preferences(db, user.id, body)


# ── Reminder Triggers (system/cron endpoint) ──


@router.post("/check-reminders")
async def trigger_reminder_check(
    user: DashboardUser,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger deadline reminder check. Creates Notification rows for approaching/overdue deadlines."""
    result = await check_deadline_reminders(db)
    return result
