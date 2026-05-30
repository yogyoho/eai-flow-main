"""Real activity implementations for the workflow engine."""

import logging
import uuid

from sqlalchemy import update
from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def init_phase(phase_id: str, project_id: str, config: dict | None = None) -> dict:
    """Initialise a workflow phase — set project current_phase_node."""
    from app.extensions.database import get_db_context
    from app.extensions.models import ReportProject

    async with get_db_context() as db:
        await db.execute(
            update(ReportProject)
            .where(ReportProject.id == uuid.UUID(project_id))
            .values(current_phase_node=phase_id)
        )
        await db.commit()

    logger.info("activity:init_phase phase_id=%s project_id=%s", phase_id, project_id)
    return {"status": "ok", "phase_id": phase_id, "project_id": project_id}


@activity.defn
async def advance_phase(phase_id: str, project_id: str) -> dict:
    """Mark a phase as advanced — update current_phase_node."""
    from app.extensions.database import get_db_context
    from app.extensions.models import ReportProject

    async with get_db_context() as db:
        await db.execute(
            update(ReportProject)
            .where(ReportProject.id == uuid.UUID(project_id))
            .values(current_phase_node=phase_id)
        )
        await db.commit()

    logger.info("activity:advance_phase phase_id=%s project_id=%s", phase_id, project_id)
    return {"status": "ok", "phase_id": phase_id}


@activity.defn
async def create_review_assignments(
    node_id: str,
    project_id: str,
    reviewers: list[str] | None = None,
) -> dict:
    """Create review assignments from DAG node config."""
    count = 0
    if reviewers:
        from app.extensions.database import get_db_context
        from app.extensions.workflow.models import PhaseReview

        async with get_db_context() as db:
            for reviewer_id in reviewers:
                review = PhaseReview(
                    project_id=uuid.UUID(project_id),
                    phase_node=node_id,
                    reviewer_id=uuid.UUID(reviewer_id),
                    review_type="chapter",
                    status="pending",
                )
                db.add(review)
                count += 1
            await db.commit()

    logger.info(
        "activity:create_review_assignments node_id=%s project_id=%s count=%d",
        node_id, project_id, count,
    )
    return {"status": "ok", "node_id": node_id, "assignment_count": count}


@activity.defn
async def notify_phase_start(phase_id: str, project_id: str) -> dict:
    """Log notification that a phase has started."""
    logger.info("activity:notify_phase_start phase_id=%s project_id=%s", phase_id, project_id)
    return {"status": "ok", "phase_id": phase_id}


@activity.defn
async def notify_review_pending(node_id: str, project_id: str) -> dict:
    """Log notification that a review is awaiting action."""
    logger.info("activity:notify_review_pending node_id=%s project_id=%s", node_id, project_id)
    return {"status": "ok", "node_id": node_id}


@activity.defn
async def notify_workflow_complete(project_id: str) -> dict:
    """Log notification that the entire workflow has completed. Updates project status."""
    from app.extensions.database import get_db_context
    from app.extensions.models import ReportProject

    async with get_db_context() as db:
        await db.execute(
            update(ReportProject)
            .where(ReportProject.id == uuid.UUID(project_id))
            .values(status="completed")
        )
        await db.commit()

    logger.info("activity:notify_workflow_complete project_id=%s", project_id)
    return {"status": "ok", "project_id": project_id}


@activity.defn
async def evaluate_condition(
    node_id: str,
    project_id: str,
    condition_expr: str | None = None,
) -> dict:
    """Evaluate a conditional expression from the DAG node config."""
    branch = "true"

    if condition_expr:
        expr = condition_expr.strip()
        if expr.lower() == "true":
            branch = "true"
        elif expr.lower() == "false":
            branch = "false"
        elif expr.startswith("report."):
            field_name = expr[len("report."):]
            from app.extensions.database import get_db_context
            from app.extensions.models import ReportProject

            async with get_db_context() as db:
                project = await db.get(ReportProject, uuid.UUID(project_id))
                if project:
                    val = getattr(project, field_name, None)
                    branch = str(val) if val is not None else "true"
        else:
            branch = expr

    logger.info("activity:evaluate_condition node_id=%s expr=%s branch=%s", node_id, condition_expr, branch)
    return {"status": "ok", "node_id": node_id, "branch": branch}


@activity.defn
async def start_ai_writing(node_id: str, project_id: str, chapter_id: str | None = None) -> dict:
    """Trigger AI writing for a chapter. Stub — logs and returns pending status.

    In production this would call DeerFlow Agent via run_agent() or similar.
    For now the caller sends ai_complete signal when AI finishes externally.
    """
    logger.info("activity:start_ai_writing node_id=%s project_id=%s chapter_id=%s", node_id, project_id, chapter_id)
    return {"status": "ok", "node_id": node_id, "chapter_id": chapter_id, "state": "writing"}


@activity.defn
async def parse_sources(chapter_id: str, content: str) -> dict:
    """Parse [source:type:ref] markers from AI-generated content."""
    from app.extensions.workflow.traceability import parse_source_markers

    parsed = parse_source_markers(content)
    logger.info("activity:parse_sources chapter_id=%s found=%d sources", chapter_id, len(parsed))
    return {
        "status": "ok",
        "chapter_id": chapter_id,
        "source_count": len(parsed),
        "sources": [
            {
                "block_index": s.block_index,
                "source_type": s.source_type,
                "source_ref": s.source_ref,
                "snippet": s.snippet,
            }
            for s in parsed
        ],
    }


@activity.defn
async def store_sources(chapter_id: str, sources: list[dict]) -> dict:
    """Persist parsed sources into the content_sources table."""
    from app.extensions.database import get_db_context
    from app.extensions.workflow.models import ContentSource

    count = 0
    async with get_db_context() as db:
        for s in sources:
            source = ContentSource(
                chapter_id=uuid.UUID(chapter_id),
                block_index=s["block_index"],
                source_type=s["source_type"],
                source_ref=s.get("source_ref"),
                snippet=s.get("snippet"),
            )
            db.add(source)
            count += 1
        await db.commit()

    logger.info("activity:store_sources chapter_id=%s stored=%d", chapter_id, count)
    return {"status": "ok", "chapter_id": chapter_id, "stored": count}


ALL_ACTIVITIES = [
    init_phase,
    advance_phase,
    create_review_assignments,
    start_ai_writing,
    parse_sources,
    store_sources,
    notify_phase_start,
    notify_review_pending,
    notify_workflow_complete,
    evaluate_condition,
]
