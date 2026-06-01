"""Real activity implementations for the workflow engine."""

import logging
import uuid

from sqlalchemy import select, update
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
                    link=f"/project/{project_id}",
                )
            )
            count += 1
        await db.commit()

    logger.info("activity:notify_phase_start phase_id=%s project_id=%s notified=%d", phase_id, project_id, count)
    return {"status": "ok", "phase_id": phase_id, "notified": count}


@activity.defn
async def notify_review_pending(node_id: str, project_id: str) -> dict:
    """Notify reviewers that a review is awaiting their action."""
    from app.extensions.database import get_db_context
    from app.extensions.models import Notification
    from app.extensions.workflow.models import PhaseReview

    count = 0
    async with get_db_context() as db:
        result = await db.execute(
            select(PhaseReview.reviewer_id).where(
                PhaseReview.project_id == uuid.UUID(project_id),
                PhaseReview.phase_node == node_id,
                PhaseReview.status == "pending",
            )
        )
        reviewer_ids = [row[0] for row in result.all()]
        for reviewer_id in reviewer_ids:
            db.add(
                Notification(
                    user_id=reviewer_id,
                    type="review_pending",
                    title=f"Review pending for phase {node_id}",
                    body=f"A review at phase {node_id} is awaiting your action.",
                    project_id=uuid.UUID(project_id),
                    link=f"/project/{project_id}/review/{node_id}",
                )
            )
            count += 1
        await db.commit()

    logger.info("activity:notify_review_pending node_id=%s project_id=%s notified=%d", node_id, project_id, count)
    return {"status": "ok", "node_id": node_id, "notified": count}


@activity.defn
async def notify_workflow_complete(project_id: str) -> dict:
    """Notify project members that the workflow has completed. Updates project status."""
    from app.extensions.database import get_db_context
    from app.extensions.models import Notification, ProjectMember, ReportProject

    count = 0
    async with get_db_context() as db:
        await db.execute(
            update(ReportProject)
            .where(ReportProject.id == uuid.UUID(project_id))
            .values(status="completed")
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
                    link=f"/project/{project_id}",
                )
            )
            count += 1
        await db.commit()

    logger.info("activity:notify_workflow_complete project_id=%s notified=%d", project_id, count)
    return {"status": "ok", "project_id": project_id, "notified": count}


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
    """Generate AI content for a chapter using the configured LLM.

    Uses create_chat_model to get the default model, sends a writing prompt
    that instructs the model to include [N] source markers, writes the
    generated content to the chapter, and returns it for downstream
    parse_sources / store_sources.
    """
    logger.info("activity:start_ai_writing node_id=%s project_id=%s chapter_id=%s", node_id, project_id, chapter_id)

    if not chapter_id:
        return {"status": "skipped", "node_id": node_id, "reason": "no chapter_id"}

    from app.extensions.database import get_db_context
    from app.extensions.models import ProjectChapter

    async with get_db_context() as db:
        chapter = await db.get(ProjectChapter, uuid.UUID(chapter_id))
        if not chapter:
            return {"status": "error", "node_id": node_id, "reason": "chapter not found"}

        prompt = _build_writing_prompt(chapter)
        content = await _generate_content(prompt)

        if content:
            chapter.content = content
            chapter.status = "draft"
            await db.commit()

        return {
            "status": "ok",
            "node_id": node_id,
            "chapter_id": chapter_id,
            "content": content or "",
        }


def _build_writing_prompt(chapter) -> str:
    """Build the LLM prompt for chapter writing with source marker instructions."""
    parts = [
        "你是一位专业的报告撰写专家。请根据以下章节信息撰写完整的章节内容。",
        "",
        "要求：",
        "1. 内容专业、准确、逻辑清晰",
        "2. 所有数据引用、法规引用、文献引用必须标注来源",
        "3. 引用格式：正文中使用 [N] 标记，文末附脚注",
        '4. 脚注格式：[N] source:type:ref（type: rag_retrieval/regulation/knowledge_base/ai/human）',
        "5. 如果没有具体来源，使用合理的占位标记",
        "",
        f"章节标题: {chapter.title or '未命名章节'}",
    ]
    if chapter.purpose:
        parts.append(f"章节目的: {chapter.purpose}")
    if chapter.generation_hint:
        parts.append(f"撰写提示: {chapter.generation_hint}")
    if chapter.word_count_target and chapter.word_count_target > 0:
        parts.append(f"目标字数: 约{chapter.word_count_target}字")

    parts.append("")
    parts.append("示例格式：")
    parts.append("该区域 SO₂ 日均浓度为 0.045mg/m³[1]，低于国家标准限值 0.15mg/m³[2]。")
    parts.append("")
    parts.append("[1] source:rag_retrieval:知识库「监测数据库」→「2024年度监测报告」p.23")
    parts.append('[2] source:regulation:GB 3095-2012《环境空气质量标准》表2')

    return "\n".join(parts)


async def _generate_content(prompt: str) -> str | None:
    """Call the default LLM to generate content."""
    try:
        from deerflow.models import create_chat_model

        model = create_chat_model("ai-writing")
        from langchain_core.messages import HumanMessage

        response = await model.ainvoke([HumanMessage(content=prompt)])
        return response.content
    except Exception:
        logger.exception("AI content generation failed")
        return None


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


@activity.defn
async def check_reviews_complete(node_id: str, project_id: str) -> dict:
    """Query phase_reviews for a review node and return aggregate status."""
    from app.extensions.database import get_db_context
    from app.extensions.workflow.models import PhaseReview

    async with get_db_context() as db:
        result = await db.execute(
            select(PhaseReview)
            .where(PhaseReview.project_id == uuid.UUID(project_id))
            .where(PhaseReview.phase_node == node_id)
        )
        reviews = result.scalars().all()

    approved = sum(1 for r in reviews if r.status == "approved")
    rejected = sum(1 for r in reviews if r.status == "rejected")
    pending = sum(1 for r in reviews if r.status == "pending")
    all_done = all(r.status in ("approved", "rejected") for r in reviews)
    all_approved = len(reviews) > 0 and approved == len(reviews)

    logger.info(
        "activity:check_reviews_complete node_id=%s total=%d approved=%d "
        "rejected=%d pending=%d all_done=%s",
        node_id, len(reviews), approved, rejected, pending, all_done,
    )
    return {
        "status": "ok",
        "node_id": node_id,
        "total": len(reviews),
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "all_done": all_done,
        "all_approved": all_approved,
    }


@activity.defn
async def handle_rejection(
    node_id: str,
    project_id: str,
    rollback_to: str,
) -> dict:
    """Handle review rejection: update project current_phase_node and reset reviews.

    Resets rejected reviews back to 'pending' and moves the project to the
    rollback target phase node.
    """
    from app.extensions.database import get_db_context
    from app.extensions.workflow.models import PhaseReview

    async with get_db_context() as db:
        # Reset rejected reviews to pending for the review node
        await db.execute(
            update(PhaseReview)
            .where(PhaseReview.project_id == uuid.UUID(project_id))
            .where(PhaseReview.phase_node == node_id)
            .where(PhaseReview.status == "rejected")
            .values(status="pending")
        )

        # Update project current_phase_node to rollback target
        from app.extensions.models import ReportProject

        await db.execute(
            update(ReportProject)
            .where(ReportProject.id == uuid.UUID(project_id))
            .values(current_phase_node=rollback_to)
        )

        await db.commit()

    logger.info(
        "activity:handle_rejection node_id=%s rollback_to=%s",
        node_id, rollback_to,
    )
    return {"status": "ok", "node_id": node_id, "rollback_to": rollback_to}


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


ALL_ACTIVITIES = [
    init_phase,
    advance_phase,
    create_review_assignments,
    check_reviews_complete,
    handle_rejection,
    gather_phase_context,
    start_ai_writing,
    parse_sources,
    store_sources,
    notify_phase_start,
    notify_review_pending,
    notify_workflow_complete,
    evaluate_condition,
]
