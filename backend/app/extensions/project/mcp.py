"""Project MCP Server — exposes chapter read/write tools to DeerFlow lead_agent.

Environment variables:
  PROJECT_DB_URL — PostgreSQL connection string (required)
"""

from __future__ import annotations

import asyncio
import json
import os
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


async def _run_in_db(func):
    """Run an async function with a database session, return its result.

    Creates a short-lived engine + session, ensuring engine.dispose() is
    called even if func raises, so connections are never leaked.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

    db_url = os.environ.get("PROJECT_DB_URL", "")
    if not db_url:
        raise RuntimeError("PROJECT_DB_URL environment variable is required")

    engine = create_async_engine(db_url, pool_size=2, max_overflow=0)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            return await func(session)
    finally:
        await engine.dispose()


# ── Tool definitions ──

TOOLS = [
    Tool(
        name="read_chapter",
        description="Read a chapter's current content, status, and metadata.",
        inputSchema={
            "type": "object",
            "properties": {
                "chapter_id": {"type": "string", "description": "UUID of the chapter"},
            },
            "required": ["chapter_id"],
        },
    ),
    Tool(
        name="write_chapter",
        description="Write content to a chapter and optionally update its status. Automatically calculates word count.",
        inputSchema={
            "type": "object",
            "properties": {
                "chapter_id": {"type": "string", "description": "UUID of the chapter"},
                "content": {"type": "string", "description": "The chapter content to write"},
                "status": {"type": "string", "description": "Optional new status: draft, editing, completed", "enum": ["draft", "editing", "completed"]},
            },
            "required": ["chapter_id", "content"],
        },
    ),
    Tool(
        name="list_chapters",
        description="List all chapters in a project with their titles, statuses, and word counts.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "UUID of the project"},
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="get_project",
        description="Get project metadata: name, report type, current stage, and status.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "UUID of the project"},
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="get_chapter_spec",
        description="Get the full writing specification for a chapter: purpose, content_contract, RAG sources, example snippet, compliance rules, and neighbor context. This is the primary context source for report writing.",
        inputSchema={
            "type": "object",
            "properties": {
                "chapter_id": {"type": "string", "description": "UUID of the chapter"},
            },
            "required": ["chapter_id"],
        },
    ),
]


# ── Tool handlers ──


async def _handle_read_chapter(arguments: dict) -> list[TextContent]:
    from app.extensions.project.service import _get_chapter_or_404, _get_assigned_names

    chapter_id = arguments["chapter_id"]

    async def _query(db):
        chapter = await _get_chapter_or_404(db, chapter_id)
        names = await _get_assigned_names(db, [chapter])
        return {
            "chapter_id": str(chapter.id),
            "title": chapter.title,
            "level": chapter.level,
            "status": chapter.status,
            "content": chapter.content,
            "word_count_target": chapter.word_count_target,
            "word_count_current": chapter.word_count_current,
            "assigned_to": str(chapter.assigned_to) if chapter.assigned_to else None,
            "assigned_name": names.get(chapter.assigned_to),
            "purpose": chapter.purpose,
            "generation_hint": chapter.generation_hint,
        }

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def _handle_write_chapter(arguments: dict) -> list[TextContent]:
    from app.extensions.project.service import update_chapter

    chapter_id = arguments["chapter_id"]
    content = arguments["content"]
    status = arguments.get("status")

    word_count = len(content) if content else 0

    async def _query(db):
        updates = {"content": content, "word_count_current": word_count}
        if status:
            updates["status"] = status
        result = await update_chapter(db, chapter_id, **updates)
        if not result:
            raise ValueError("Chapter not found")
        return {"chapter_id": str(result.id), "status": result.status, "word_count_current": result.word_count_current}

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def _handle_list_chapters(arguments: dict) -> list[TextContent]:
    from app.extensions.project.service import get_outline_tree

    project_id = arguments["project_id"]

    async def _query(db):
        tree = await get_outline_tree(db, project_id)

        def _flatten(chapters):
            items = []
            for c in chapters:
                items.append({
                    "chapter_id": str(c.id),
                    "title": c.title,
                    "level": c.level,
                    "status": c.status,
                    "word_count_target": c.word_count_target,
                    "word_count_current": c.word_count_current,
                    "assigned_name": c.assigned_name,
                })
                items.extend(_flatten(c.children))
            return items

        return _flatten(tree)

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def _handle_get_project(arguments: dict) -> list[TextContent]:
    from app.extensions.project.service import get_project

    project_id = arguments["project_id"]

    async def _query(db):
        p = await get_project(db, project_id)
        if not p:
            raise ValueError("Project not found")
        return {
            "project_id": str(p.id),
            "name": p.name,
            "report_type": p.report_type,
            "status": p.status,
            "current_stage": p.current_stage,
            "chapter_count": p.chapter_count,
        }

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def _handle_get_chapter_spec(arguments: dict) -> list[TextContent]:
    """Get the full writing spec for a chapter, merging project data with template data."""
    from app.extensions.project.service import _get_chapter_or_404, _get_project_or_404, _get_assigned_names
    from sqlalchemy import select
    from app.extensions.models import ProjectChapter
    from app.extensions.knowledge_factory.models import ExtractionTemplate

    chapter_id = arguments["chapter_id"]

    async def _query(db):
        chapter = await _get_chapter_or_404(db, chapter_id)
        project = await _get_project_or_404(db, chapter.project_id)
        names = await _get_assigned_names(db, [chapter])

        spec = {
            "chapter_id": str(chapter.id),
            "title": chapter.title,
            "level": chapter.level,
            "sort_order": chapter.sort_order,
            "current_content": chapter.content,
            "word_count_target": chapter.word_count_target,
            "word_count_current": chapter.word_count_current,
            "status": chapter.status,
            "assigned_name": names.get(chapter.assigned_to),
        }

        if project.template_id:
            template = await db.get(ExtractionTemplate, project.template_id)
            if template and template.root_sections_json:
                sections = template.root_sections_json.get("sections", [])
                _match_section_to_spec(spec, sections, chapter.title)

        all_chapters_stmt = (
            select(ProjectChapter)
            .where(ProjectChapter.project_id == chapter.project_id, ProjectChapter.parent_id == chapter.parent_id)
            .order_by(ProjectChapter.sort_order)
        )
        all_result = await db.execute(all_chapters_stmt)
        siblings = list(all_result.scalars().all())

        for i, sib in enumerate(siblings):
            if sib.id == chapter.id:
                if i > 0:
                    prev = siblings[i - 1]
                    spec.setdefault("neighbors", {})["previous"] = {
                        "title": prev.title,
                        "status": prev.status,
                        "summary": (prev.content[:200] if prev.content else ""),
                    }
                if i < len(siblings) - 1:
                    nxt = siblings[i + 1]
                    spec.setdefault("neighbors", {})["next"] = {
                        "title": nxt.title,
                        "status": nxt.status,
                        "summary": (nxt.content[:200] if nxt.content else ""),
                    }
                break

        return spec

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


def _match_section_to_spec(spec: dict, sections: list, chapter_title: str) -> None:
    """Find the matching template section by title and merge its spec."""
    for sec in sections:
        if sec.get("title") == chapter_title:
            spec["purpose"] = sec.get("purpose", spec.get("purpose"))
            spec["generation_hint"] = sec.get("generation_hint", spec.get("generation_hint"))
            if "content_contract" in sec and isinstance(sec["content_contract"], dict):
                spec["content_contract"] = sec["content_contract"]
            if "compliance_rules" in sec:
                spec["compliance_rules"] = sec["compliance_rules"]
            if "rag_sources" in sec:
                spec["rag_sources"] = sec["rag_sources"]
            if "example_snippet" in sec:
                spec["example_snippet"] = sec["example_snippet"]
            return
        if "children" in sec:
            _match_section_to_spec(spec, sec["children"], chapter_title)


# ── Server setup ──

server = Server("project")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handlers = {
        "read_chapter": _handle_read_chapter,
        "write_chapter": _handle_write_chapter,
        "list_chapters": _handle_list_chapters,
        "get_project": _handle_get_project,
        "get_chapter_spec": _handle_get_chapter_spec,
    }
    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
