"""Deadline-based reminder trigger service.

Scans ProjectTimeline entries and milestones for approaching or overdue deadlines,
creates Notification rows for affected project members, respecting per-user
NotificationPreference.type_settings.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import Notification, NotificationPreference, ProjectMember, ReportProject
from app.extensions.workflow.models import ProjectTimeline

logger = logging.getLogger(__name__)

# How many days before deadline to trigger each urgency level
_URGENCY_WINDOWS = {
    "overdue": 0,  # past deadline
    "urgent": 1,  # due today or tomorrow
    "warning": 3,  # due within 3 days
    "notice": 7,  # due within 7 days
}

_URGENCY_LABELS = {
    "overdue": "已逾期",
    "urgent": "即将截止",
    "warning": "即将到期",
    "notice": "截止提醒",
}


def _classify_urgency(planned_end: date, remind_days: int) -> str | None:
    """Classify deadline urgency relative to today. Returns None if outside all windows."""
    today = date.today()
    delta = (planned_end - today).days

    if delta < 0:
        return "overdue"
    if delta == 0:
        return "urgent"
    if delta <= min(remind_days, 1):
        return "urgent"
    if delta <= min(remind_days, 3):
        return "warning"
    if delta <= remind_days:
        return "notice"
    return None


def _make_dedup_key(user_id: UUID, project_id: UUID, phase_node: str, deadline: date) -> str:
    """Build a dedup key for a reminder notification."""
    return f"deadline:{user_id}:{project_id}:{phase_node}:{deadline.isoformat()}"


async def check_deadline_reminders(db: AsyncSession) -> dict:
    """Scan timelines and milestones for approaching deadlines and create notifications.

    Returns {"checked": int, "created": int, "skipped": int}.
    """
    created = 0
    skipped = 0
    checked = 0

    # ── 1. Phase-level deadline checks (ProjectTimeline.planned_end) ──

    # Get all active timeline entries with planned_end set
    timeline_stmt = select(ProjectTimeline).where(
        ProjectTimeline.planned_end.isnot(None),
    )
    timeline_result = await db.execute(timeline_stmt)
    timelines = timeline_result.scalars().all()

    for tl in timelines:
        checked += 1
        if not tl.planned_end:
            continue

        # Get project and its members
        proj_stmt = select(ReportProject).where(ReportProject.id == tl.project_id)
        proj_result = await db.execute(proj_stmt)
        project = proj_result.scalar_one_or_none()
        if not project or project.status not in ("in_progress", "active"):
            continue

        # Get phase label from workflow graph
        phase_label = tl.phase_node
        if project.workflow_id:
            from app.extensions.workflow.models import WorkflowDefinition

            defn = await db.get(WorkflowDefinition, project.workflow_id)
            if defn and defn.graph_json:
                for node in defn.graph_json.get("nodes", []):
                    if node["id"] == tl.phase_node:
                        phase_label = node.get("data", {}).get("label", tl.phase_node)
                        break

        # Get affected users: phase owner + project members
        affected_user_ids: set[UUID] = set()
        if tl.owner_id:
            affected_user_ids.add(tl.owner_id)

        member_stmt = select(ProjectMember.user_id).where(ProjectMember.project_id == tl.project_id)
        member_result = await db.execute(member_stmt)
        for row in member_result.all():
            affected_user_ids.add(row[0])

        for user_id in affected_user_ids:
            # Check user's preference for deadline notifications
            pref = await _get_prefs(db, user_id)
            if not pref.type_settings.get("deadline", True):
                skipped += 1
                continue

            urgency = _classify_urgency(tl.planned_end, pref.deadline_remind_days)
            if urgency is None:
                continue

            # Dedup: check if we already created this reminder today
            dedup_key = _make_dedup_key(user_id, tl.project_id, tl.phase_node, tl.planned_end)
            existing = await _find_existing_reminder(db, user_id, tl.project_id, dedup_key)
            if existing:
                skipped += 1
                continue

            # Create notification
            urgency_label = _URGENCY_LABELS.get(urgency, "")
            title = f"{urgency_label}: {project.name} — {phase_label}"
            body = f"该阶段计划完成日期为 {tl.planned_end.isoformat()}"
            if urgency == "overdue":
                days_over = (date.today() - tl.planned_end).days
                body = f"该阶段已逾期 {days_over} 天（计划完成: {tl.planned_end.isoformat()}）"

            notif = Notification(
                user_id=user_id,
                type="deadline",
                title=title,
                body=body,
                project_id=tl.project_id,
                link=f"/projects/{tl.project_id}?tab=workflow",
            )
            # Store dedup key in notification for future checks
            notif.body = f"{body}\n_dedup:{dedup_key}"
            db.add(notif)
            created += 1

    # ── 2. Milestone deadline checks ──

    for tl in timelines:
        if not tl.milestones:
            continue

        # Get project
        proj_stmt = select(ReportProject).where(ReportProject.id == tl.project_id)
        proj_result = await db.execute(proj_stmt)
        project = proj_result.scalar_one_or_none()
        if not project or project.status not in ("in_progress", "active"):
            continue

        for i, ms in enumerate(tl.milestones):
            target_str = ms.get("target_date")
            ms_label = ms.get("label", f"里程碑 {i + 1}")
            if not target_str:
                continue

            try:
                target_date = date.fromisoformat(target_str) if isinstance(target_str, str) else target_str
            except (ValueError, TypeError):
                continue

            # Only notify the phase owner for milestones
            if not tl.owner_id:
                continue

            pref = await _get_prefs(db, tl.owner_id)
            if not pref.type_settings.get("deadline", True):
                continue

            urgency = _classify_urgency(target_date, pref.deadline_remind_days)
            if urgency is None:
                continue

            dedup_key = f"milestone:{tl.owner_id}:{tl.project_id}:{tl.phase_node}:{i}:{target_date.isoformat()}"
            existing = await _find_existing_reminder(db, tl.owner_id, tl.project_id, dedup_key)
            if existing:
                skipped += 1
                continue

            urgency_label = _URGENCY_LABELS.get(urgency, "")
            notif = Notification(
                user_id=tl.owner_id,
                type="deadline",
                title=f"{urgency_label}: {project.name} — {ms_label}",
                body=f"里程碑「{ms_label}」目标日期为 {target_date.isoformat()}",
                project_id=tl.project_id,
                link=f"/projects/{tl.project_id}?tab=workflow",
            )
            notif.body = f"{notif.body}\n_dedup:{dedup_key}"
            db.add(notif)
            created += 1

    if created > 0:
        await db.commit()

    return {"checked": checked, "created": created, "skipped": skipped}


async def _get_prefs(db: AsyncSession, user_id: UUID) -> NotificationPreference:
    """Get or create notification preferences for a user."""
    stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    result = await db.execute(stmt)
    pref = result.scalar_one_or_none()

    if pref is None:
        pref = NotificationPreference(
            user_id=user_id,
            type_settings={
                "deadline": True,
                "review_pending": True,
                "phase_start": True,
                "mention": True,
                "assignment": True,
                "workflow_complete": True,
            },
        )
        db.add(pref)
        await db.flush()

    return pref


async def _find_existing_reminder(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    dedup_key: str,
) -> bool:
    """Check if a reminder with this dedup key already exists (created today)."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id,
        Notification.project_id == project_id,
        Notification.type == "deadline",
        Notification.created_at >= today_start,
        Notification.body.contains(dedup_key),
    )
    count = (await db.execute(stmt)).scalar_one()
    return count > 0
