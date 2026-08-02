"""Notification activities — phase start, review pending, workflow complete.

These activities are pure side-effects (notifications, document space sync).
They are re-exported by ``activities.py``.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def notify_phase_start(phase_id: str, project_id: str) -> dict:
    """Notify project members that a new phase has started."""
    from app.extensions.database import get_db_context
    from app.extensions.models import Notification, ProjectMember

    count = 0
    async with get_db_context() as db:
        result = await db.execute(
            select(ProjectMember.user_id).where(
                ProjectMember.project_id == uuid.UUID(project_id),
            )
        )
        user_ids = [row[0] for row in result.all()]
        for user_id in user_ids:
            db.add(
                Notification(
                    user_id=user_id,
                    type="phase_start",
                    title=f"Phase {phase_id} started",
                    body=f"Workflow phase {phase_id} has started for this project.",
                    project_id=uuid.UUID(project_id),
                    link=f"/projects/{project_id}",
                )
            )
            count += 1
        await db.commit()

    logger.info("activity:notify_phase_start phase_id=%s project_id=%s notified=%d", phase_id, project_id, count)
    return {"status": "ok", "phase_id": phase_id, "notified": count}


@activity.defn
async def notify_review_pending(node_id: str, project_id: str) -> dict:
    """Notify reviewers that a review is awaiting their action.

    Escalation timeline (per the four-module spec §5.5):
    - 0h:   assignment created with 48h deadline
    - ~24h: warning — "review due in 24h"
    - 48h+: overdue — notify phase_lead
    - 72h+: auto-escalate — notify project owner
    """
    from app.extensions.database import get_db_context
    from app.extensions.models import Notification, ProjectMember, User
    from app.extensions.review.models import ReviewAssignment

    count = 0
    escalated = 0
    now = datetime.now(timezone.utc)

    async with get_db_context() as db:
        # Fetch full ReviewAssignment rows (not just reviewer_id) for deadline checks
        assignments_result = await db.execute(
            select(ReviewAssignment).where(
                ReviewAssignment.project_id == uuid.UUID(project_id),
                ReviewAssignment.phase_node == node_id,
                ReviewAssignment.status == "pending",
            )
        )
        assignments = assignments_result.scalars().all()

        for ra in assignments:
            deadline = getattr(ra, "deadline_at", None)

            # Determine escalation level
            if deadline is not None:
                hours_until_deadline = (deadline - now).total_seconds() / 3600
                hours_past_deadline = -hours_until_deadline
            else:
                hours_until_deadline = None
                hours_past_deadline = 0

            # Level 0: standard notification to reviewer
            db.add(
                Notification(
                    user_id=ra.reviewer_id,
                    type="review_pending",
                    title=f"审核待处理 — 阶段 {node_id}",
                    body=f"阶段 {node_id} 有待审核任务需要您处理。"
                         + (f" 截止时间: {deadline.strftime('%m-%d %H:%M')} (UTC)" if deadline else ""),
                    project_id=uuid.UUID(project_id),
                    link=f"/projects/{project_id}?tab=review",
                )
            )
            count += 1

            # Level 1: overdue (>48h) → notify phase_lead
            if hours_past_deadline > 0:
                lead_ids = await _resolve_phase_lead_ids(db, project_id, node_id)
                for lead_id in lead_ids:
                    db.add(
                        Notification(
                            user_id=lead_id,
                            type="review_overdue",
                            title=f"审核已超时 — 阶段 {node_id}",
                            body=f"阶段 {node_id} 的审核已超时 {hours_past_deadline:.0f} 小时，请关注。",
                            project_id=uuid.UUID(project_id),
                            link=f"/projects/{project_id}?tab=review",
                        )
                    )
                    escalated += 1

            # Level 2: severely overdue (>72h) → notify owner
            if hours_past_deadline > 24:  # 48h deadline + 24h grace = 72h total
                owner_ids = await _resolve_owner_ids(db, project_id)
                for owner_id in owner_ids:
                    db.add(
                        Notification(
                            user_id=owner_id,
                            type="review_escalated",
                            title=f"审核严重超时 — 阶段 {node_id}",
                            body=f"阶段 {node_id} 的审核已超时 {hours_past_deadline:.0f} 小时，已自动升级至项目负责人。",
                            project_id=uuid.UUID(project_id),
                            link=f"/projects/{project_id}?tab=review",
                        )
                    )
                    escalated += 1

        await db.commit()

    logger.info(
        "activity:notify_review_pending node_id=%s notified=%d escalated=%d",
        node_id, count, escalated,
    )
    return {"status": "ok", "node_id": node_id, "notified": count, "escalated": escalated}


async def _resolve_phase_lead_ids(db, project_id: str, node_id: str) -> list[uuid.UUID]:
    """Find user IDs of phase leads for a given project phase node."""
    from app.extensions.models import ProjectMember

    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == uuid.UUID(project_id),
        )
    )
    members = result.scalars().all()
    lead_ids: list[uuid.UUID] = []
    for m in members:
        duties = getattr(m, "phase_duties", None) or {}
        entry = duties.get(node_id, {}) or {}
        role = entry.get("role") or entry.get("duty")
        if role in ("phase_lead", "lead", "leader"):
            lead_ids.append(m.user_id)
    # Fallback: project-level phase_lead role
    if not lead_ids:
        for m in members:
            if m.role == "phase_lead":
                lead_ids.append(m.user_id)
    return lead_ids


async def _resolve_owner_ids(db, project_id: str) -> list[uuid.UUID]:
    """Find user IDs of project owners."""
    from app.extensions.models import ProjectMember

    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == uuid.UUID(project_id),
            ProjectMember.role == "owner",
        )
    )
    return [m.user_id for m in result.scalars().all()]


async def _sync_chapters_to_doc_space(
    db, project_id: str, user_ids: list | None = None, chapter_count: int = 0,
) -> str | None:
    """Merge generated chapters into a report doc and sync to document space."""
    from sqlalchemy import func as _func
    from app.extensions.models import AIDocument, Folder, ProjectChapter, ReportProject

    if not chapter_count:
        return None

    # Resolve owner if caller didn't provide member list (e.g. AI-gen phase)
    if not user_ids:
        from app.extensions.models import ProjectMember as _PM
        _mr = await db.execute(
            select(_PM.user_id).where(_PM.project_id == uuid.UUID(project_id))
        )
        user_ids = [r[0] for r in _mr.all()]

    ch_result = await db.execute(
        select(ProjectChapter)
        .where(ProjectChapter.project_id == uuid.UUID(project_id))
        .where(ProjectChapter.status.in_(("draft", "reviewing", "approved")))  # EAI-CUSTOM: canonical (ADR 2026-08-02)
        .where(ProjectChapter.content.isnot(None))
        .where(_func.length(ProjectChapter.content) > 0)
        .order_by(ProjectChapter.sort_order)
    )
    chapters = ch_result.scalars().all()
    if not chapters:
        return None
    proj = await db.get(ReportProject, uuid.UUID(project_id))
    report_type_label = (getattr(proj, "report_type", None) or "报告")
    # Map report_type to a human-readable suffix
    _REPORT_TYPE_LABELS: dict[str, str] = {
        "safety_assessment": "安全评价报告",
        "environmental_impact": "环境影响报告",
        "fire_protection": "消防设计报告",
        "geological_report": "地质勘查报告",
        "coal_eia": "煤炭环评报告",
    }
    type_suffix = _REPORT_TYPE_LABELS.get(report_type_label, report_type_label)
    title = f"{proj.name if proj else '报告'}_{type_suffix}"
    parts = [f"# {title}\n\n"]
    for ch in chapters:
        parts.append(f"## {ch.title}\n\n{ch.content or ''}\n\n")
    merged = "".join(parts)
    owner_id = user_ids[0] if user_ids else uuid.UUID(int=0)
    proj_folder_id: uuid.UUID | None = None
    pfx_result = await db.execute(
        select(Folder.id)
        .where(Folder.project_id == uuid.UUID(project_id))
        .where(Folder.parent_id.is_(None))
        .limit(1)
    )
    pfx_row = pfx_result.first()
    if pfx_row:
        proj_folder_id = pfx_row[0]
    else:
        pfx = Folder(name=proj.name if proj else "项目报告", owner_id=owner_id,
                       project_id=uuid.UUID(project_id), parent_id=None)
        db.add(pfx); await db.flush()
        proj_folder_id = pfx.id
    doc = AIDocument(user_id=owner_id, project_id=uuid.UUID(project_id),
                     folder_id=proj_folder_id, title=title, content=merged,
                     folder="项目文件夹", doc_type="report", status="draft")
    db.add(doc)
    logger.info("sync: %d chapters → '%s' (folder_id=%s)", len(chapters), title, str(proj_folder_id))
    return title


@activity.defn
async def notify_workflow_complete(project_id: str) -> dict:
    """Notify project members that the workflow has completed. Updates project status."""
    from app.extensions.database import get_db_context
    from app.extensions.models import (
        AIDocument,
        Notification,
        ProjectChapter,
        ProjectMember,
        ReportProject,
    )

    count = 0
    async with get_db_context() as db:
        await db.execute(
            update(ReportProject)
            .where(ReportProject.id == uuid.UUID(project_id))
            .values(status="approved")  # EAI-CUSTOM: canonical (ADR 2026-08-02)
        )

        result = await db.execute(
            select(ProjectMember.user_id).where(
                ProjectMember.project_id == uuid.UUID(project_id),
            )
        )
        user_ids = [row[0] for row in result.all()]
        for user_id in user_ids:
            db.add(
                Notification(
                    user_id=user_id,
                    type="workflow_complete",
                    title="Workflow completed",
                    body="The workflow for this project has been completed successfully.",
                    project_id=uuid.UUID(project_id),
                    link=f"/projects/{project_id}",
                )
            )
            count += 1

        # Merge chapters into a doc-space report (also called at AI completion).
        try:
            await _sync_chapters_to_doc_space(db, project_id, user_ids,
                                                chapter_count=len(user_ids) * 6)
        except Exception:
            logger.exception("notify_workflow_complete: sync failed %s", project_id)

        await db.commit()

    logger.info("activity:notify_workflow_complete project_id=%s notified=%d", project_id, count)
    return {"status": "ok", "project_id": project_id, "notified": count}


NOTIFICATION_ACTIVITIES = [
    notify_phase_start,
    notify_review_pending,
    notify_workflow_complete,
]
