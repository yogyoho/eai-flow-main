"""Writing Context activities — AI chapter generation, source parsing.

These activities implement the Writing Context bounded context from the
four-module redesign spec.  They are re-exported by ``activities.py`` so
existing callers (workflows, tests) are unaffected.
"""

import asyncio
import logging
import uuid

from sqlalchemy import select
from temporalio import activity

from app.extensions.writing.generation_strategy import select_strategy, GenerationStrategy
from app.extensions.writing.dependency_graph import topological_order
from app.extensions.writing.state_machine import validate_chapter_transition

logger = logging.getLogger(__name__)

# ── Helpers ─────────────────────────────────────────────────────────────────

# Refusal patterns — when the LLM declines to generate content.
_REFUSAL_KEYWORDS: list[str] = [
    "i cannot", "i can't", "i apologize", "i'm unable", "i am unable",
    "无法", "不能", "抱歉", "对不起", "我无法", "我不能",
    "as an ai", "as a language model",
]


def _validate_generated_content(content: str | None) -> str | None:
    """Validate AI-generated content; return an error_code string or None if valid."""
    if not content or not content.strip():
        return "empty_error"
    content_lower = content.strip().lower()
    for kw in _REFUSAL_KEYWORDS:
        if content_lower.startswith(kw):
            return "refusal_error"
    # Heuristic: a refusal is often short (< 200 chars) and starts with an apology
    if len(content_lower) < 200 and any(
        content_lower.startswith(kw) for kw in _REFUSAL_KEYWORDS
    ):
        return "refusal_error"
    return None


def _sanitize_log_msg(exc: Exception) -> str:
    """Truncate and sanitize an exception message for safe logging.

    Caps at 200 characters and strips common credential patterns so that
    API keys and tokens do not leak into log output.
    """
    import re
    msg = str(exc)
    # Strip common key/token patterns
    for pattern in ("key=", "api_key=", "token=", "secret=", "authorization="):
        msg = re.sub(
            rf"{pattern}[^\s,;)]+",
            f"{pattern}***",
            msg,
            flags=re.IGNORECASE,
        )
    return msg[:200]


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


async def _generate_content(prompt: str, *, timeout: float = 60.0, retries: int = 1) -> tuple[str | None, str | None]:
    """Call the default LLM to generate content with timeout and retry.

    Validates the response before returning: empty content, refusal patterns,
    and obviously bad output are rejected with a specific error_code.
    Returns (content, error_code).  error_code is None on success.
    """
    from langchain_core.messages import HumanMessage

    for attempt in range(retries + 1):
        try:
            from deerflow.models import create_chat_model

            model = create_chat_model()  # default (first) configured model
            response = await asyncio.wait_for(
                model.ainvoke([HumanMessage(content=prompt)]),
                timeout=timeout,
            )
            content = response.content
            validation_error = _validate_generated_content(content)
            if validation_error:
                logger.warning(
                    "AI content validation failed: %s (attempt %d/%d)",
                    validation_error, attempt + 1, retries + 1,
                )
                if attempt == retries:
                    return None, validation_error
                await asyncio.sleep(3)
                continue
            return content, None
        except asyncio.TimeoutError:
            logger.warning("AI content generation timed out (attempt %d/%d, timeout=%.0fs)", attempt + 1, retries + 1, timeout)
            if attempt == retries:
                return None, "timeout"
            await asyncio.sleep(3)
        except Exception as exc:
            exc_msg = str(exc).lower()
            if "auth" in exc_msg or "401" in exc_msg or "403" in exc_msg or "api_key" in exc_msg:
                logger.error("AI content generation auth error: %s", _sanitize_log_msg(exc))
                return None, "auth_error"
            if "quota" in exc_msg or "429" in exc_msg or "rate" in exc_msg:
                logger.error("AI content generation quota error: %s", _sanitize_log_msg(exc))
                return None, "quota_error"
            logger.exception("AI content generation failed (attempt %d/%d)", attempt + 1, retries + 1)
            if attempt == retries:
                return None, "generation_error"
            await asyncio.sleep(3)
    return None, "generation_error"


def _get_member_duty(member, node_id: str) -> str | None:
    """Extract a member's role/duty string for a given workflow node.

    Reads the unified ``role`` key first (post-migration format), then falls
    back to the legacy ``duty`` key for backward compatibility.
    Returns ``None`` if the member has no duties for that node.
    """
    duties = getattr(member, "phase_duties", None) or {}
    entry = duties.get(node_id, {}) or {}
    return entry.get("role") or entry.get("duty")


async def _resolve_writer_for_chapter(
    db, project_id: str, chapter
) -> uuid.UUID | None:
    """Resolve a writer for a chapter from project members' phase_duties.

    Looks for members with ``duty="writer"`` for the chapter's ``phase_node``.
    If no phase-scoped writer is found, falls back to any member with role="writer".
    """
    from app.extensions.models import ProjectMember

    phase_node = getattr(chapter, "phase_node", None)

    member_result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == uuid.UUID(project_id),
        )
    )
    members = member_result.scalars().all()

    # Priority 1: phase-scoped writer
    if phase_node:
        for member in members:
            duty = _get_member_duty(member, phase_node)
            if duty in ("writer", "write"):
                return member.user_id

    # Priority 2: any member with role="writer"
    for member in members:
        if member.role == "writer":
            return member.user_id

    # Priority 3: first project owner
    for member in members:
        if member.role == "owner":
            return member.user_id

    return None


# ── Activities ──────────────────────────────────────────────────────────────


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
    from app.extensions.models import ProjectChapter, ProjectMember

    async with get_db_context() as db:
        chapter = await db.get(ProjectChapter, uuid.UUID(chapter_id))
        if not chapter:
            return {"status": "error", "node_id": node_id, "reason": "chapter not found"}

        # Ownership validation: chapter must belong to the given project
        if str(chapter.project_id) != project_id:
            logger.warning(
                "activity:start_ai_writing chapter %s does not belong to project %s",
                chapter_id, project_id,
            )
            return {"status": "error", "node_id": node_id, "chapter_id": chapter_id,
                    "reason": "chapter does not belong to this project"}

        # Auto-assign chapter to a writer if not already assigned
        if not chapter.assigned_to:
            writer_id = await _resolve_writer_for_chapter(db, project_id, chapter)
            if writer_id:
                chapter.assigned_to = writer_id

        # Validate chapter state transition
        if chapter:
            err = validate_chapter_transition(chapter.status, "draft")
            if err:
                logger.warning("activity:start_ai_writing invalid transition: %s", err)
                return {"status": "skipped", "node_id": node_id, "chapter_id": chapter_id, "reason": err}

        prompt = _build_writing_prompt(chapter)
        content, error_code = await _generate_content(prompt)

        if content:
            chapter.content = content
            chapter.status = "draft"
            await db.commit()
            from app.extensions.workflow.metrics import record_ai_generation_success
            record_ai_generation_success(project_id=project_id, chapter_id=chapter_id)
        else:
            # Record failure on the chapter so the UI can surface it
            chapter.status = "error"
            chapter.generation_hint = (chapter.generation_hint or "") + f"\n[AI generation failed: {error_code}]"
            await db.commit()
            from app.extensions.workflow.metrics import record_ai_generation_failure
            record_ai_generation_failure(project_id=project_id, chapter_id=chapter_id, error_code=error_code or "unknown")

        return {
            "status": "ok" if content else "error",
            "node_id": node_id,
            "chapter_id": chapter_id,
            "content": content or "",
            "error_code": error_code,
        }


@activity.defn
async def start_phase_ai_writing(phase_id: str, project_id: str) -> dict:
    """Batch AI generation for all chapters in a phase (simple report path).

    For complex reports, generates chapters in dependency order.
    For simple reports, parallel batch generation.
    """
    from app.extensions.database import get_db_context
    from app.extensions.models import ProjectChapter, ReportProject

    async with get_db_context() as db:
        project = await db.get(ReportProject, uuid.UUID(project_id))
        if not project or not project.template_id:
            return {"status": "error", "reason": "no template"}

        # Fetch template sections for dependency derivation
        from app.extensions.knowledge_factory.models import ExtractionTemplate
        tmpl = await db.get(ExtractionTemplate, project.template_id)
        sections = (tmpl.root_sections_json or {}).get("sections", []) if tmpl else []

        # Get chapters in this phase, ordered
        chapters_result = await db.execute(
            select(ProjectChapter)
            .where(ProjectChapter.project_id == uuid.UUID(project_id))
            .where(ProjectChapter.phase_node == phase_id)
            .order_by(ProjectChapter.sort_order)
        )
        chapters = chapters_result.scalars().all()

        if not chapters:
            # No chapters tagged to this phase node — templates without
            # phase/subflow nodes leave ProjectChapter.phase_node NULL. Fall back
            # to ALL chapters in the project so a top-level "AI编写初稿" node still
            # generates the initial report content.
            all_result = await db.execute(
                select(ProjectChapter)
                .where(ProjectChapter.project_id == uuid.UUID(project_id))
                .order_by(ProjectChapter.sort_order)
            )
            chapters = all_result.scalars().all()
            if not chapters:
                return {"status": "ok", "phase_id": phase_id, "results": [], "reason": "no chapters"}

        # Determine strategy
        strategy = select_strategy(
            sections,
            project.report_type,
            manual_override=None,  # Can be extended to read from node config
        )

        results = []
        if strategy == GenerationStrategy.BATCH:
            # Parallel generation for all chapters (simple reports)
            for ch in chapters:
                if ch.status not in ("pending", "error"):
                    results.append({"chapter_id": str(ch.id), "status": ch.status, "reason": "skipped"})
                    continue
                content, error_code = await _generate_content(_build_writing_prompt(ch))
                if content:
                    ch.content = content
                    ch.status = "draft"
                    ch.word_count_current = len(content)
                else:
                    ch.status = "error"
                    ch.generation_hint = (ch.generation_hint or "") + f"\n[AI failed: {error_code}]"
                results.append({"chapter_id": str(ch.id), "status": ch.status})
            await db.commit()
        else:
            # Sequential — respect dependency order (complex reports)
            if sections:
                batches = topological_order(sections)
                for batch in batches:
                    batch_chapters = [c for c in chapters if c.title in batch]
                    for ch in batch_chapters:
                        if ch.status not in ("pending", "error"):
                            results.append({"chapter_id": str(ch.id), "status": ch.status, "reason": "skipped"})
                            continue
                        content, error_code = await _generate_content(_build_writing_prompt(ch))
                        if content:
                            ch.content = content
                            ch.status = "draft"
                            ch.word_count_current = len(content)
                        else:
                            ch.status = "error"
                            ch.generation_hint = (ch.generation_hint or "") + f"\n[AI failed: {error_code}]"
                        results.append({"chapter_id": str(ch.id), "status": ch.status})
                    await db.commit()  # Commit after each batch so subsequent batches see updated data
            else:
                # No template sections — fall back to simple sequential
                for ch in chapters:
                    if ch.status not in ("pending", "error"):
                        continue
                    content, error_code = await _generate_content(_build_writing_prompt(ch))
                    if content:
                        ch.content = content
                        ch.status = "draft"
                        ch.word_count_current = len(content)
                    else:
                        ch.status = "error"
                        ch.generation_hint = (ch.generation_hint or "") + f"\n[AI failed: {error_code}]"
                    results.append({"chapter_id": str(ch.id), "status": ch.status})
                await db.commit()

        logger.info(
            "activity:start_phase_ai_writing phase_id=%s strategy=%s chapters=%d",
            phase_id, strategy.value, len(results),
        )

        # Sync generated chapters to document space immediately after AI
        # draft is ready, so the project folder and report appear in /docmgr
        # and the editor tab while the workflow is still in progress.
        from .notification_activities import _sync_chapters_to_doc_space

        await _sync_chapters_to_doc_space(
            db, project_id, user_ids=None,
            chapter_count=len([r for r in results if r["status"] == "draft"]),
        )

        return {"status": "ok", "phase_id": phase_id, "strategy": strategy.value, "results": results}


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


WRITING_ACTIVITIES = [
    start_ai_writing,
    start_phase_ai_writing,
    parse_sources,
    store_sources,
]
