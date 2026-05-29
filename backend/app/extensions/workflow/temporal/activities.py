"""Stub activity implementations for the workflow engine.

Each activity is a placeholder that logs its invocation and returns a
status dict.  Real implementations will be filled in as the workflow
engine matures.
"""

import logging

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def init_phase(phase_id: str, project_id: str, config: dict | None = None) -> dict:
    """Initialise a workflow phase (create records, prepare state, etc.)."""
    logger.info("activity:init_phase phase_id=%s project_id=%s", phase_id, project_id)
    return {"status": "ok", "phase_id": phase_id, "project_id": project_id}


@activity.defn
async def advance_phase(phase_id: str, project_id: str) -> dict:
    """Mark a phase as advanced / transitioned to the next stage."""
    logger.info("activity:advance_phase phase_id=%s project_id=%s", phase_id, project_id)
    return {"status": "ok", "phase_id": phase_id}


@activity.defn
async def create_review_assignments(
    node_id: str,
    project_id: str,
    reviewers: list[str] | None = None,
) -> dict:
    """Create review assignments for a review gate node."""
    logger.info(
        "activity:create_review_assignments node_id=%s project_id=%s reviewers=%s",
        node_id,
        project_id,
        reviewers,
    )
    return {"status": "ok", "node_id": node_id, "assignment_count": len(reviewers or [])}


@activity.defn
async def notify_phase_start(phase_id: str, project_id: str) -> dict:
    """Send notification that a phase has started."""
    logger.info("activity:notify_phase_start phase_id=%s project_id=%s", phase_id, project_id)
    return {"status": "ok", "phase_id": phase_id}


@activity.defn
async def notify_review_pending(node_id: str, project_id: str) -> dict:
    """Send notification that a review is awaiting action."""
    logger.info(
        "activity:notify_review_pending node_id=%s project_id=%s", node_id, project_id
    )
    return {"status": "ok", "node_id": node_id}


@activity.defn
async def notify_workflow_complete(project_id: str) -> dict:
    """Send notification that the entire workflow has completed."""
    logger.info("activity:notify_workflow_complete project_id=%s", project_id)
    return {"status": "ok", "project_id": project_id}


@activity.defn
async def evaluate_condition(
    node_id: str,
    project_id: str,
    condition_expr: str | None = None,
) -> dict:
    """Evaluate a conditional expression and return the routing branch."""
    logger.info(
        "activity:evaluate_condition node_id=%s condition=%s", node_id, condition_expr
    )
    # Stub: always evaluates to the "true" branch.
    return {"status": "ok", "node_id": node_id, "branch": "true"}


ALL_ACTIVITIES = [
    init_phase,
    advance_phase,
    create_review_assignments,
    notify_phase_start,
    notify_review_pending,
    notify_workflow_complete,
    evaluate_condition,
]
