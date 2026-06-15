"""Real activity implementations for the workflow engine.

Orchestration activities (init_phase, init_task, advance_phase,
evaluate_condition, gather_phase_context) live here directly.

Writing, review, and notification activities are defined in bounded-context
sub-modules and re-exported below so existing callers (``workflows.py``,
tests) are unaffected.
"""

import logging
import uuid

from sqlalchemy import select, update
from temporalio import activity

# Ensure all ORM models are registered so SQLAlchemy can resolve FK references
# during flush. Without this, `get_db_context()` sessions fail with
# NoReferencedTableError for models not yet imported in the worker process.
import app.extensions.models  # noqa: F401
import app.extensions.knowledge_factory.models  # noqa: F401

# ── Re-export bounded-context activities ────────────────────────────────────

from .writing_activities import (  # noqa: E402, F401
    _build_writing_prompt,
    _generate_content,
    _get_member_duty,
    _REFUSAL_KEYWORDS,
    _resolve_writer_for_chapter,
    _sanitize_log_msg,
    _validate_generated_content,
    parse_sources,
    start_ai_writing,
    start_phase_ai_writing,
    store_sources,
    WRITING_ACTIVITIES,
)
from .review_activities import (  # noqa: E402, F401
    check_phase_completion,
    check_reviews_complete,
    create_review_assignments,
    handle_rejection,
    REVIEW_ACTIVITIES,
)
from .notification_activities import (  # noqa: E402, F401
    _sync_chapters_to_doc_space,
    NOTIFICATION_ACTIVITIES,
    notify_phase_start,
    notify_review_pending,
    notify_workflow_complete,
)

logger = logging.getLogger(__name__)


# ── Orchestration activities ────────────────────────────────────────────────


@activity.defn
async def init_phase(phase_id: str, project_id: str, config: dict | None = None) -> dict:
    """Initialise a workflow phase — set project current_phase_node and tag chapters with phase scope."""
    from app.extensions.database import get_db_context
    from app.extensions.models import ReportProject, ProjectChapter
    from sqlalchemy import select as sa_select

    async with get_db_context() as db:
        project = await db.get(ReportProject, uuid.UUID(project_id))
        if not project:
            logger.warning("activity:init_phase project not found: %s", project_id)
            return {"status": "error", "detail": "Project not found"}

        project.current_phase_node = phase_id

        # Tag chapters belonging to this phase using chapter_range from the workflow graph
        if project.workflow_id:
            from app.extensions.workflow.models import WorkflowDefinition
            defn = await db.get(WorkflowDefinition, project.workflow_id)
            if defn and defn.graph_json:
                _mg = defn.graph_json.get("mainGraph", defn.graph_json)
                for node in _mg.get("nodes", []):
                    if node["id"] == phase_id:
                        cr = node.get("data", {}).get("chapter_range")
                        if cr and len(cr) == 2:
                            all_stmt = sa_select(ProjectChapter).where(
                                ProjectChapter.project_id == uuid.UUID(project_id),
                            ).order_by(ProjectChapter.sort_order)
                            result = await db.execute(all_stmt)
                            all_chapters = result.scalars().all()
                            level1 = [c for c in all_chapters if c.level == 1]
                            start_idx, end_idx = cr
                            if 0 <= start_idx < len(level1) and 0 < end_idx <= len(level1):
                                selected_ids = {c.id for c in level1[start_idx:end_idx]}
                                for c in all_chapters:
                                    if c.id in selected_ids or c.parent_id in selected_ids:
                                        c.phase_node = phase_id
                        break

        await db.commit()

    logger.info("activity:init_phase phase_id=%s project_id=%s", phase_id, project_id)

    from app.extensions.workflow.metrics import record_workflow_phase_transition
    record_workflow_phase_transition(
        project_id=project_id,
        to_node=phase_id,
    )

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
async def init_task(node_id: str, project_id: str, config: dict | None = None) -> dict:
    """Initialize a task node — set current_phase_node and auto-assign required roles to project members.

    Reads ``requiredRoles`` from the workflow DAG node and maps each role to
    the first available project member who isn't already assigned to this phase.
    Updates ``ProjectMember.phase_duties`` for the assigned members.
    """
    from app.extensions.database import get_db_context
    from app.extensions.models import ProjectMember, ReportProject

    config = config or {}
    required_roles: list[dict] = config.get("requiredRoles", [])

    async with get_db_context() as db:
        project = await db.get(ReportProject, uuid.UUID(project_id))
        if not project:
            logger.warning("activity:init_task project not found: %s", project_id)
            return {"status": "error", "detail": "Project not found"}

        project.current_phase_node = node_id

        # Auto-assign required roles to project members
        assigned_count = 0
        if required_roles:
            member_result = await db.execute(
                select(ProjectMember).where(ProjectMember.project_id == uuid.UUID(project_id))
            )
            members = member_result.scalars().all()

            for role_spec in required_roles:
                role_key = role_spec.get("roleKey", role_spec.get("role_key", ""))
                needed = role_spec.get("count", 1)
                if not role_key or needed <= 0:
                    continue

                # Single-pass: count already-assigned and fill remaining slots
                remaining = needed
                for member in members:
                    if _get_member_duty(member, node_id) == role_key:
                        remaining -= 1

                for member in members:
                    if remaining <= 0:
                        break
                    if _get_member_duty(member, node_id) is None:
                        duties = member.phase_duties or {}
                        duties[node_id] = {"role": role_key}
                        member.phase_duties = duties
                        assigned_count += 1
                        remaining -= 1

                if remaining > 0:
                    logger.info(
                        "activity:init_task node_id=%s role=%s unfilled=%d",
                        node_id, role_key, remaining,
                    )

            # Distribute editable chapters among writer-duty members (DF-6):
            # gives each writer writing todos (chapter.assigned_to) + edit scope,
            # even for templates without phase/subflow nodes (chapters untagged).
            writer_ids = [
                m.user_id for m in members
                if _get_member_duty(m, node_id) in ("writer", "write")
            ]
            if writer_ids:
                from app.extensions.models import ProjectChapter

                ch_result = await db.execute(
                    select(ProjectChapter)
                    .where(ProjectChapter.project_id == uuid.UUID(project_id))
                    .where(ProjectChapter.assigned_to.is_(None))
                    .where(ProjectChapter.status.in_(("pending", "draft", "error")))
                    .order_by(ProjectChapter.sort_order)
                )
                for idx, ch in enumerate(ch_result.scalars().all()):
                    ch.assigned_to = writer_ids[idx % len(writer_ids)]

        await db.commit()

    logger.info(
        "activity:init_task node_id=%s project_id=%s assigned=%d roles=%d",
        node_id, project_id, assigned_count, len(required_roles),
    )
    return {
        "status": "ok",
        "node_id": node_id,
        "project_id": project_id,
        "assigned_count": assigned_count,
    }


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
async def gather_phase_context(phase_id: str, project_id: str) -> dict:
    """Collect project chapter data for context passing to downstream nodes.

    Returns chapter titles, content previews, and statuses.
    """
    from app.extensions.database import get_db_context
    from app.extensions.models import ProjectChapter

    async with get_db_context() as db:
        result = await db.execute(
            select(ProjectChapter)
            .where(ProjectChapter.project_id == uuid.UUID(project_id))
            .order_by(ProjectChapter.sort_order)
        )
        chapters = result.scalars().all()

        chapter_data = [
            {
                "chapter_id": str(ch.id),
                "title": ch.title,
                "status": ch.status,
                "content_preview": (ch.content or "")[:200],
                "word_count": ch.word_count_current,
            }
            for ch in chapters
        ]

    logger.info(
        "activity:gather_phase_context phase_id=%s chapters=%d",
        phase_id, len(chapter_data),
    )
    return {
        "status": "ok",
        "phase_id": phase_id,
        "project_id": project_id,
        "chapters": chapter_data,
    }


# ── Aggregate activity list ─────────────────────────────────────────────────

ALL_ACTIVITIES = [
    init_phase,
    init_task,
    advance_phase,
    evaluate_condition,
    gather_phase_context,
    *WRITING_ACTIVITIES,
    *REVIEW_ACTIVITIES,
    *NOTIFICATION_ACTIVITIES,
]
