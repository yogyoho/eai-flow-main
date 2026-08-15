"""Review Context activities — assignment, gate evaluation, rejection rollback.

These activities implement the Review Context bounded context.  They query
``ReviewAssignment`` (the unified review model) and evaluate gate strategies
via ``evaluate_gate()``.  Re-exported by ``activities.py``.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from temporalio import activity

from app.extensions.review.gate import GateMode, evaluate_gate
from app.extensions.review.models import ReviewAssignment

logger = logging.getLogger(__name__)

# Default review deadline — 48 hours from assignment.
DEFAULT_REVIEW_DEADLINE_HOURS = 48


def _get_member_duty(member, node_id: str) -> str | None:
    """Extract a member's role/duty string for a given workflow node.

    Reads the unified ``role`` key first (post-migration format), then falls
    back to the legacy ``duty`` key for backward compatibility.
    Returns ``None`` if the member has no duties for that node.
    """
    duties = getattr(member, "phase_duties", None) or {}
    entry = duties.get(node_id, {}) or {}
    return entry.get("role") or entry.get("duty")


# ── Activities ──────────────────────────────────────────────────────────────


@activity.defn
async def create_review_assignments(
    node_id: str,
    project_id: str,
    reviewers: list[str] | None = None,
) -> dict:
    """Create review assignments from DAG node config.

    When *reviewers* is empty or None, auto-resolves reviewers from project
    members whose ``phase_duties`` for the current phase include duty="reviewer".
    Falls back to phase lead, then project owner.
    Existing assignments for the same (project, node, reviewer) are skipped
    to avoid duplicates on workflow restart.
    """
    from app.extensions.database import get_db_context
    from app.extensions.models import ProjectMember

    count = 0

    async with get_db_context() as db:
        # Gather explicit or auto-resolved reviewer user IDs
        resolved: list[str] = list(reviewers) if reviewers else []

        if not resolved:
            member_result = await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == uuid.UUID(project_id),
                )
            )
            members = member_result.scalars().all()

            # Priority 1: explicit "reviewer" duty for this phase
            for member in members:
                if _get_member_duty(member, node_id) == "reviewer":
                    resolved.append(str(member.user_id))

            # Priority 2: fall back to phase lead
            if not resolved:
                for member in members:
                    if _get_member_duty(member, node_id) == "lead":
                        resolved.append(str(member.user_id))

            # Priority 2.5: fall back to dept head
            if not resolved:
                from app.extensions.models import Role, User

                for member in members:
                    if member.role == "owner":
                        owner = await db.get(User, member.user_id)
                        if owner and owner.dept_id:
                            dh_r = await db.execute(
                                select(User.id)
                                .join(Role, User.role_id == Role.id)
                                .where(
                                    User.dept_id == owner.dept_id,
                                    Role.name == "部门负责人",
                                    User.is_deleted.is_(False),
                                )
                                .limit(1)
                            )
                            dh_row = dh_r.first()
                            if dh_row:
                                resolved.append(str(dh_row[0]))
                                break

            # Priority 3: fall back to project owner
            if not resolved:
                for member in members:
                    if member.role == "owner":
                        resolved.append(str(member.user_id))

            logger.info(
                "activity:create_review_assignments auto-resolved %d reviewers (phase=%s)",
                len(resolved),
                node_id,
            )

        # Create ReviewAssignment rows, skipping existing duplicates
        if resolved:
            pid = uuid.UUID(project_id)
            for reviewer_id in resolved:
                rid = uuid.UUID(reviewer_id)
                existing = await db.execute(
                    select(ReviewAssignment).where(
                        ReviewAssignment.project_id == pid,
                        ReviewAssignment.phase_node == node_id,
                        ReviewAssignment.reviewer_id == rid,
                    )
                )
                if existing.scalar_one_or_none() is None:
                    db.add(
                        ReviewAssignment(
                            project_id=pid,
                            phase_node=node_id,
                            reviewer_id=rid,
                            reviewer_role="reviewer",
                            status="pending",
                            # EAI-CUSTOM (bug-1150): column is `DateTime` = TIMESTAMP
                            # WITHOUT TIME ZONE (naive). Passing an offset-aware
                            # datetime makes asyncpg's naive-epoch encode subtract
                            # aware-naive → DataError → activity retries forever.
                            deadline_at=(datetime.now(UTC).replace(tzinfo=None)) + timedelta(hours=DEFAULT_REVIEW_DEADLINE_HOURS),
                        )
                    )
                    count += 1

            await db.commit()

    logger.info(
        "activity:create_review_assignments node_id=%s project_id=%s count=%d",
        node_id,
        project_id,
        count,
    )
    return {"status": "ok", "node_id": node_id, "assignment_count": count}


@activity.defn
async def check_phase_completion(phase_id: str, project_id: str, chapter_range: list[int] | None = None) -> dict:
    """Check whether all chapters in the current phase are completed.

    Validates that every chapter within the phase's scope has status
    'completed' or 'approved'. Returns a summary of completion status.
    If chapter_range is provided, only chapters in that range are checked.
    """
    from app.extensions.database import get_db_context
    from app.extensions.models import ProjectChapter

    async with get_db_context() as db:
        result = await db.execute(select(ProjectChapter).where(ProjectChapter.project_id == uuid.UUID(project_id)).where(ProjectChapter.level == 1).order_by(ProjectChapter.sort_order))
        all_level1 = result.scalars().all()

        # Filter by chapter_range if provided
        if chapter_range and len(chapter_range) == 2:
            start_idx, end_idx = chapter_range
            scoped = all_level1[start_idx:end_idx]
        else:
            scoped = all_level1

        # Collect all scoped chapter IDs (including children)
        scoped_ids: set[uuid.UUID] = set()
        for ch in scoped:
            scoped_ids.add(ch.id)
        # Also include children of scoped chapters
        if scoped_ids:
            child_result = await db.execute(select(ProjectChapter.id).where(ProjectChapter.project_id == uuid.UUID(project_id)).where(ProjectChapter.parent_id.in_(scoped_ids)))
            for row in child_result.all():
                scoped_ids.add(row[0])

        if not scoped_ids:
            return {"status": "ok", "phase_id": phase_id, "ready": True, "total": 0, "completed": 0, "pending": 0}

        # Check status of all scoped chapters — single batch query with title
        status_result = await db.execute(select(ProjectChapter.id, ProjectChapter.status, ProjectChapter.title).where(ProjectChapter.id.in_(scoped_ids)))
        total = 0
        completed = 0
        pending = 0
        incomplete_chapters: list[str] = []
        for ch_id, ch_status, ch_title in status_result.all():
            total += 1
            if ch_status in ("reviewing", "approved"):  # EAI-CUSTOM: canonical (ADR 2026-08-02)
                completed += 1
            else:
                pending += 1
                incomplete_chapters.append(f"{ch_title or ch_id} ({ch_status})")

        ready = total > 0 and pending == 0

    logger.info(
        "activity:check_phase_completion phase_id=%s total=%d completed=%d pending=%d ready=%s",
        phase_id,
        total,
        completed,
        pending,
        ready,
    )
    return {
        "status": "ok",
        "phase_id": phase_id,
        "ready": ready,
        "total": total,
        "completed": completed,
        "pending": pending,
        "incomplete_chapters": incomplete_chapters,
    }


@activity.defn
async def check_reviews_complete(node_id: str, project_id: str) -> dict:
    """Query review_assignments for a review node and return aggregate status.

    Uses the configured gate mode from the workflow DAG node (defaults to
    ALL_MUST_APPROVE).  Returns PASS / REJECT / WAITING per the gate strategy,
    plus per-reviewer detail for the UI.
    """
    from app.extensions.database import get_db_context

    async with get_db_context() as db:
        result = await db.execute(select(ReviewAssignment).where(ReviewAssignment.project_id == uuid.UUID(project_id)).where(ReviewAssignment.phase_node == node_id))
        reviews = result.scalars().all()

    # Build judgments list for gate evaluation
    judgments: list[dict] = []
    for r in reviews:
        if r.status in ("approved", "rejected"):
            judgments.append({"reviewer_id": str(r.reviewer_id), "status": r.status})

    total = len(reviews)
    approved = sum(1 for j in judgments if j["status"] == "approved")
    rejected = sum(1 for j in judgments if j["status"] == "rejected")
    pending = total - len(judgments)

    # Default gate mode: all_must_approve.  Can be overridden per-node via
    # DAG node.data.review_policy.mode in the future.
    gate_mode = GateMode.ALL_MUST_APPROVE
    gate_result = evaluate_gate(gate_mode, total, judgments)

    all_done = pending == 0
    all_approved = total > 0 and approved == total

    logger.info(
        "activity:check_reviews_complete node_id=%s total=%d approved=%d rejected=%d pending=%d gate=%s all_done=%s",
        node_id,
        total,
        approved,
        rejected,
        pending,
        gate_result.value,
        all_done,
    )

    # Record metrics for each submitted review judgment
    from app.extensions.workflow.metrics import record_review_action

    for j in judgments:
        record_review_action(
            project_id=project_id,
            node_id=node_id,
            reviewer_id=j["reviewer_id"],
            status=j["status"],
        )

    return {
        "status": "ok",
        "node_id": node_id,
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "all_done": all_done,
        "all_approved": all_approved,
        "gate_result": gate_result.value,
    }


@activity.defn
async def handle_rejection(
    node_id: str,
    project_id: str,
    rollback_to: str,
) -> dict:
    """Handle review rejection: update project current_phase_node and reset reviews.

    Resets rejected reviews back to 'pending' and moves the project to the
    rollback target phase node.  Also resets chapter statuses in the rollback
    phase back to 'pending' so the writing team can re-edit them.
    """
    from app.extensions.database import get_db_context

    async with get_db_context() as db:
        # Reset rejected reviews to pending for the review node
        await db.execute(update(ReviewAssignment).where(ReviewAssignment.project_id == uuid.UUID(project_id)).where(ReviewAssignment.phase_node == node_id).where(ReviewAssignment.status == "rejected").values(status="pending"))

        # Update project current_phase_node to rollback target
        from app.extensions.models import ReportProject

        await db.execute(update(ReportProject).where(ReportProject.id == uuid.UUID(project_id)).values(current_phase_node=rollback_to))

        # Reset chapter statuses in the rollback phase back to 'pending'
        from app.extensions.models import ProjectChapter

        await db.execute(
            update(ProjectChapter)
            .where(ProjectChapter.project_id == uuid.UUID(project_id))
            .where(ProjectChapter.phase_node == rollback_to)
            .where(ProjectChapter.status.in_(("reviewing", "approved")))  # EAI-CUSTOM: canonical (ADR 2026-08-02)
            .values(status="pending")
        )

        await db.commit()

    logger.info(
        "activity:handle_rejection node_id=%s rollback_to=%s",
        node_id,
        rollback_to,
    )
    return {"status": "ok", "node_id": node_id, "rollback_to": rollback_to}


REVIEW_ACTIVITIES = [
    create_review_assignments,
    check_phase_completion,
    check_reviews_complete,
    handle_rejection,
]
