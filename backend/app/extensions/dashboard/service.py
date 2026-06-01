"""Dashboard service — aggregates tasks, projects, stats, and calendar events for a user."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.extensions.models import (
    Notification,
    ProjectChapter,
    ProjectMember,
    ReportProject,
)
from app.extensions.workflow.models import PhaseReview

from .schemas import (
    CalendarEvent,
    MyProjectItem,
    MyProjectsResponse,
    MyStatsResponse,
    MyTasksResponse,
    NotificationListResponse,
    NotificationOut,
    TaskItem,
)

logger = logging.getLogger(__name__)


# ── Task Priorities ──

_BASE_SCORE = {
    "approval": 40,
    "review": 30,
    "writing": 20,
    "phase_lead": 15,
    "rejection": 35,
}

_URGENCY_DELTA = {
    "overdue": 30,
    "today": 25,
    "tomorrow": 20,
    "this_week": 10,
    "none": 0,
}


def _compute_urgency(due_date: datetime | None) -> str:
    if due_date is None:
        return "none"
    now = datetime.now(timezone.utc)
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)
    delta = due_date - now
    if delta.total_seconds() < 0:
        return "overdue"
    if delta.days == 0:
        return "today"
    if delta.days == 1:
        return "tomorrow"
    if delta.days <= 7:
        return "this_week"
    return "none"


def _compute_priority(task_type: str, due_date: datetime | None, is_blocking: bool = False) -> int:
    base = _BASE_SCORE.get(task_type, 10)
    urgency = _URGENCY_DELTA.get(_compute_urgency(due_date), 0)
    blocking = 25 if is_blocking else 0
    return base + urgency + blocking


# ── Task Aggregation ──


async def get_my_tasks(db: AsyncSession, user_id: UUID) -> MyTasksResponse:
    """Aggregate all actionable tasks for a user across their projects."""
    tasks: list[TaskItem] = []

    # 1. Pending reviews assigned to this user
    review_stmt = (
        select(PhaseReview, ReportProject.name.label("project_name"))
        .join(ReportProject, PhaseReview.project_id == ReportProject.id)
        .where(PhaseReview.reviewer_id == user_id, PhaseReview.status == "pending")
    )
    review_result = await db.execute(review_stmt)
    for review, proj_name in review_result.all():
        tasks.append(
            TaskItem(
                id=f"review-{review.id}",
                type="review",
                priority_score=_compute_priority("review", review.created_at),
                project_id=review.project_id,
                project_name=proj_name,
                phase_node=review.phase_node,
                chapter_id=review.chapter_id,
                action_label="开始审核",
                action_url=f"/projects/{review.project_id}?tab=review",
            )
        )

    # 2. Writing tasks — chapters assigned to this user in draft/writing status
    member_stmt = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
    member_result = await db.execute(member_stmt)
    project_ids = [row[0] for row in member_result.all()]

    for pid in project_ids:
        chapter_stmt = (
            select(ProjectChapter)
            .where(
                ProjectChapter.project_id == pid,
                ProjectChapter.assigned_to == user_id,
                ProjectChapter.status.in_(["draft", "writing"]),
            )
        )
        chapter_result = await db.execute(chapter_stmt)
        for ch in chapter_result.scalars().all():
            tasks.append(
                TaskItem(
                    id=f"writing-{ch.id}",
                    type="writing",
                    priority_score=_compute_priority("writing", None),
                    project_id=pid,
                    project_name="",  # filled below
                    chapter_id=ch.id,
                    chapter_title=ch.title,
                    action_label="继续编写",
                    action_url=f"/projects/{pid}?tab=editor&chapter={ch.id}",
                )
            )

    # 3. Phase lead tasks — user is phase_lead for the current phase that hasn't started
    duties_stmt = select(ProjectMember).where(
        ProjectMember.user_id == user_id,
        ProjectMember.phase_duties.isnot(None),
    )
    duties_result = await db.execute(duties_stmt)
    for member in duties_result.scalars().all():
        if not member.phase_duties:
            continue
        for phase_key, duty_info in member.phase_duties.items():
            if duty_info.get("duty") != "lead":
                continue
            # Check if this phase is the current one and needs action
            proj_stmt = select(ReportProject).where(ReportProject.id == member.project_id)
            proj_result = await db.execute(proj_stmt)
            proj = proj_result.scalar_one_or_none()
            if not proj or proj.status not in ("in_progress",):
                continue
            phase_node = phase_key.replace("phase-", "phase-")
            if proj.current_phase_node == phase_node:
                tasks.append(
                    TaskItem(
                        id=f"lead-{member.project_id}-{phase_key}",
                        type="phase_lead",
                        priority_score=_compute_priority("phase_lead", None, is_blocking=True),
                        project_id=member.project_id,
                        project_name=proj.name,
                        phase_node=phase_node,
                        action_label="进入项目",
                        action_url=f"/projects/{member.project_id}?tab=workflow",
                    )
                )

    # Fill project names for writing tasks
    proj_names: dict[UUID, str] = {}
    for task in tasks:
        if task.project_name == "" and task.project_id not in proj_names:
            proj_stmt = select(ReportProject.name).where(ReportProject.id == task.project_id)
            result = await db.execute(proj_stmt)
            name = result.scalar_one_or_none()
            proj_names[task.project_id] = name or ""
        if task.project_name == "":
            task.project_name = proj_names.get(task.project_id, "")

    # Sort by priority descending
    tasks.sort(key=lambda t: t.priority_score, reverse=True)

    urgent_count = sum(1 for t in tasks if t.priority_score >= 50)

    return MyTasksResponse(
        tasks=tasks,
        urgent_count=urgent_count,
        total_count=len(tasks),
    )


# ── My Projects (grouped by role) ──


async def get_my_projects(db: AsyncSession, user_id: UUID) -> MyProjectsResponse:
    """Get user's projects grouped by their primary role in each."""
    stmt = (
        select(ProjectMember, ReportProject)
        .join(ReportProject, ProjectMember.project_id == ReportProject.id)
        .where(ProjectMember.user_id == user_id)
        .order_by(ReportProject.updated_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    groups: dict[str, list[MyProjectItem]] = {
        "owner": [],
        "phase_lead": [],
        "reviewer": [],
        "writer": [],
        "viewer": [],
    }

    for member, project in rows:
        # Determine primary role
        role_label = _classify_project_role(member, project)

        # Count pending tasks for this user in this project
        pending = await _count_pending_tasks(db, user_id, project.id)

        # Compute phase label
        phase_label = await _get_phase_label(db, project)

        # Compute progress
        progress = await _compute_project_progress(db, project.id)

        item = MyProjectItem(
            project_id=project.id,
            project_name=project.name,
            report_type=project.report_type,
            status=project.status,
            current_phase=phase_label,
            current_phase_node=project.current_phase_node,
            progress_pct=progress,
            role_label=role_label,
            pending_task_count=pending,
            last_updated=project.updated_at,
        )
        groups.setdefault(role_label, []).append(item)

    # Remove empty groups
    groups = {k: v for k, v in groups.items() if v}
    total = sum(len(v) for v in groups.values())

    return MyProjectsResponse(groups=groups, total_count=total)


def _classify_project_role(member: ProjectMember, project: ReportProject) -> str:
    """Classify user's primary role in a project."""
    if member.role == "owner":
        return "owner"

    duties = member.phase_duties or {}
    for _key, info in duties.items():
        if info.get("duty") == "lead":
            return "phase_lead"
    for _key, info in duties.items():
        if info.get("duty") == "reviewer":
            return "reviewer"
    for _key, info in duties.items():
        if info.get("duty") == "writer":
            return "writer"

    return "viewer"


async def _count_pending_tasks(db: AsyncSession, user_id: UUID, project_id: UUID) -> int:
    """Count pending tasks for a user in a specific project."""
    # Pending reviews
    review_count_stmt = select(func.count()).select_from(PhaseReview).where(
        PhaseReview.project_id == project_id,
        PhaseReview.reviewer_id == user_id,
        PhaseReview.status == "pending",
    )
    review_count = (await db.execute(review_count_stmt)).scalar_one()

    # Writing chapters
    chapter_count_stmt = select(func.count()).select_from(ProjectChapter).where(
        ProjectChapter.project_id == project_id,
        ProjectChapter.assigned_to == user_id,
        ProjectChapter.status.in_(["draft", "writing"]),
    )
    chapter_count = (await db.execute(chapter_count_stmt)).scalar_one()

    return review_count + chapter_count


async def _get_phase_label(db: AsyncSession, project: ReportProject) -> str | None:
    """Get the human-readable label for the current phase."""
    if not project.workflow_id or not project.current_phase_node:
        return None
    from app.extensions.workflow.models import WorkflowDefinition

    defn = await db.get(WorkflowDefinition, project.workflow_id)
    if not defn or not defn.graph_json:
        return None
    for node in defn.graph_json.get("nodes", []):
        if node["id"] == project.current_phase_node:
            return node.get("data", {}).get("label", project.current_phase_node)
    return project.current_phase_node


async def _compute_project_progress(db: AsyncSession, project_id: UUID) -> int:
    """Compute overall project progress as percentage of completed chapters."""
    total_stmt = select(func.count()).select_from(ProjectChapter).where(
        ProjectChapter.project_id == project_id,
    )
    total = (await db.execute(total_stmt)).scalar_one()
    if total == 0:
        return 0

    done_stmt = select(func.count()).select_from(ProjectChapter).where(
        ProjectChapter.project_id == project_id,
        ProjectChapter.status == "completed",
    )
    done = (await db.execute(done_stmt)).scalar_one()

    return int((done / total) * 100)


# ── My Stats ──


async def get_my_stats(db: AsyncSession, user_id: UUID) -> MyStatsResponse:
    """Get user's personal statistics."""
    # Projects count
    proj_count_stmt = select(func.count()).select_from(ProjectMember).where(
        ProjectMember.user_id == user_id,
    )
    projects_count = (await db.execute(proj_count_stmt)).scalar_one()

    # Pending reviews
    review_count_stmt = select(func.count()).select_from(PhaseReview).where(
        PhaseReview.reviewer_id == user_id,
        PhaseReview.status == "pending",
    )
    pending_reviews = (await db.execute(review_count_stmt)).scalar_one()

    # Pending writing
    member_stmt = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
    member_result = await db.execute(member_stmt)
    project_ids = [row[0] for row in member_result.all()]

    pending_writing = 0
    if project_ids:
        writing_stmt = select(func.count()).select_from(ProjectChapter).where(
            ProjectChapter.project_id.in_(project_ids),
            ProjectChapter.assigned_to == user_id,
            ProjectChapter.status.in_(["draft", "writing"]),
        )
        pending_writing = (await db.execute(writing_stmt)).scalar_one()

    # Completed this week
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    completed_reviews_stmt = select(func.count()).select_from(PhaseReview).where(
        PhaseReview.reviewer_id == user_id,
        PhaseReview.status.in_(["approved", "rejected"]),
        PhaseReview.updated_at >= week_ago,
    )
    completed_this_week = (await db.execute(completed_reviews_stmt)).scalar_one()

    # Overdue (placeholder — would need due_date tracking)
    overdue_count = 0

    return MyStatsResponse(
        projects_count=projects_count,
        pending_reviews=pending_reviews,
        pending_writing=pending_writing,
        completed_this_week=completed_this_week,
        overdue_count=overdue_count,
    )


# ── My Calendar ──


async def get_my_calendar(
    db: AsyncSession,
    user_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[CalendarEvent]:
    """Get calendar events for a user (deadlines, milestones, phase starts)."""
    events: list[CalendarEvent] = []

    # Default: next 30 days
    now = datetime.now(timezone.utc)
    if start_date is None:
        start_date = now
    if end_date is None:
        end_date = now + timedelta(days=30)

    # 1. Pending review assignments as deadline events
    review_stmt = (
        select(PhaseReview, ReportProject.name.label("project_name"))
        .join(ReportProject, PhaseReview.project_id == ReportProject.id)
        .where(PhaseReview.reviewer_id == user_id, PhaseReview.status == "pending")
    )
    review_result = await db.execute(review_stmt)
    for review, proj_name in review_result.all():
        events.append(
            CalendarEvent(
                id=f"review-{review.id}",
                title=f"审核: {proj_name}",
                date=review.created_at or now,
                type="deadline",
                project_id=review.project_id,
                project_name=proj_name,
                color="blue",
            )
        )

    # 2. Timeline milestones from project_timeline
    member_stmt = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
    member_result = await db.execute(member_stmt)
    project_ids = [row[0] for row in member_result.all()]

    if project_ids:
        from app.extensions.workflow.models import ProjectTimeline

        timeline_stmt = select(ProjectTimeline).where(
            ProjectTimeline.project_id.in_(project_ids),
        )
        timeline_result = await db.execute(timeline_stmt)
        for tl in timeline_result.scalars().all():
            for i, ms in enumerate(tl.milestones or []):
                target = ms.get("target_date")
                if not target:
                    continue
                if isinstance(target, str):
                    target = datetime.fromisoformat(target).replace(tzinfo=timezone.utc)
                if start_date <= target <= end_date:
                    # Get project name
                    proj_stmt = select(ReportProject.name).where(ReportProject.id == tl.project_id)
                    proj_result = await db.execute(proj_stmt)
                    proj_name = proj_result.scalar_one_or_none() or ""

                    events.append(
                        CalendarEvent(
                            id=f"milestone-{tl.id}-{i}",
                            title=f"里程碑: {ms.get('label', '未命名')}",
                            date=target,
                            type="milestone",
                            project_id=tl.project_id,
                            project_name=proj_name,
                            color="purple",
                        )
                    )

    return events


# ── Notifications ──


async def get_notifications(
    db: AsyncSession,
    user_id: UUID,
    skip: int = 0,
    limit: int = 20,
) -> NotificationListResponse:
    """Get user's notifications, newest first."""
    # Total count
    count_stmt = select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id,
    )
    total = (await db.execute(count_stmt)).scalar_one()

    # Unread count
    unread_stmt = select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id,
        Notification.is_read == False,  # noqa: E712
    )
    unread_count = (await db.execute(unread_stmt)).scalar_one()

    # Paginated list
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    notifications = result.scalars().all()

    return NotificationListResponse(
        notifications=[NotificationOut.model_validate(n) for n in notifications],
        total=total,
        unread_count=unread_count,
    )


async def mark_notification_read(db: AsyncSession, notification_id: UUID, user_id: UUID) -> bool:
    """Mark a notification as read. Returns True if found and updated."""
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.user_id == user_id,
    )
    result = await db.execute(stmt)
    notification = result.scalar_one_or_none()
    if not notification:
        return False
    notification.is_read = True
    await db.commit()
    return True


async def mark_all_notifications_read(db: AsyncSession, user_id: UUID) -> int:
    """Mark all notifications as read for a user. Returns count updated."""
    stmt = select(Notification).where(
        Notification.user_id == user_id,
        Notification.is_read == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    notifications = result.scalars().all()
    count = 0
    for n in notifications:
        n.is_read = True
        count += 1
    await db.commit()
    return count
