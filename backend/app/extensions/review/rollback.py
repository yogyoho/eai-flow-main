"""Rejection rollback — resets reviews + chapters + project phase node."""
from __future__ import annotations

import uuid

from sqlalchemy import update as sa_update


def build_rollback_plan(
    project_id: str,
    review_node_id: str,
    rollback_target: str,
    affected_chapter_ids: list[str],
    rejected_reviewer_ids: list[str],
) -> dict:
    """Build a rollback plan describing what to reset.

    Returns a dict describing what to reset — caller executes with DB session.
    """
    return {
        "project_id": project_id,
        "target_phase": rollback_target,
        "chapters_to_reset": affected_chapter_ids,
        "reviews_to_reset": rejected_reviewer_ids,
    }


async def execute_rollback(db, plan: dict):
    """Execute a rollback plan against the database."""
    from app.extensions.models import ProjectChapter, ReportProject
    from app.extensions.review.models import ReviewAssignment

    project_id = uuid.UUID(plan["project_id"])

    # 1. Reset rejected reviews to pending
    if plan.get("reviews_to_reset"):
        await db.execute(
            sa_update(ReviewAssignment)
            .where(ReviewAssignment.project_id == project_id)
            .where(ReviewAssignment.reviewer_id.in_(
                uuid.UUID(rid) for rid in plan["reviews_to_reset"]
            ))
            .values(status="pending")
        )

    # 2. Reset chapters in the rollback phase
    if plan.get("chapters_to_reset"):
        await db.execute(
            sa_update(ProjectChapter)
            .where(ProjectChapter.project_id == project_id)
            .where(ProjectChapter.id.in_(
                uuid.UUID(cid) for cid in plan["chapters_to_reset"]
            ))
            .where(ProjectChapter.status.in_(("completed", "approved", "reviewed")))
            .values(status="pending")
        )

    # 3. Move project to rollback target
    await db.execute(
        sa_update(ReportProject)
        .where(ReportProject.id == project_id)
        .values(current_phase_node=plan["target_phase"])
    )

    await db.commit()
