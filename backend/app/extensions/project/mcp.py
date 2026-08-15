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
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    db_url = os.environ.get("PROJECT_DB_URL", "")
    if not db_url:
        raise RuntimeError("PROJECT_DB_URL environment variable is required")

    engine = create_async_engine(db_url, pool_size=2, max_overflow=0)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await func(session)
            # EAI-CUSTOM: 桥修复（断点 3）——必须 commit，否则 AsyncSession.close() 回滚未提交事务，
            # project_write_chapter 每次写入被静默丢弃。expire_on_commit=False 保证返回对象属性仍可读。
            await session.commit()
            return result
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
                "status": {"type": "string", "description": "Optional new status: pending, draft, reviewing (canonical, ADR 2026-08-02)", "enum": ["pending", "draft", "reviewing"]},
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
    from app.extensions.project.service import _get_assigned_names, _get_chapter_or_404

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

    # EAI-CUSTOM: 桥修复（断点 4）+ 单状态集（ADR 2026-08-02 P3）——MCP 写边界集合成员校验，只在此处做。
    # 允许集 {pending, draft, reviewing}（agent 可发起写作、提交审阅；不含 approved 防 agent 自批）。
    # 不做"状态转移"校验：update_chapter 与前端 OverviewTab 共享，转移校验会拒绝前端合法写入。
    #
    # EAI-CUSTOM TODO(security): 桥修复后 MCP 工具连共享 agentflow 库，但 _run_in_db 无用户上下文，
    # 任意用户的 agent 可读写任意项目章节（交叉租户提权）。Ship-Gate 已接受"记录风险+TODO"方案（Open Q1-A）。
    # 完整修复（thread→user 解析 + ProjectMember 成员校验）列为独立跟进项，写入桥上线前需项目方接受该风险。
    _VALID_WRITE_STATUSES = {"pending", "draft", "reviewing"}  # EAI-CUSTOM: canonical (ADR 2026-08-02 P3)
    if status is not None and status not in _VALID_WRITE_STATUSES:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {"error": f"非法 status: {status!r}，允许值: {sorted(_VALID_WRITE_STATUSES)}"},
                    ensure_ascii=False,
                ),
            )
        ]

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
                items.append(
                    {
                        "chapter_id": str(c.id),
                        "title": c.title,
                        "level": c.level,
                        "status": c.status,
                        "word_count_target": c.word_count_target,
                        "word_count_current": c.word_count_current,
                        "assigned_name": c.assigned_name,
                    }
                )
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
            "derived_stage": p.derived_stage,
            "chapter_count": p.chapter_count,
        }

    result = await _run_in_db(_query)
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def _handle_get_chapter_spec(arguments: dict) -> list[TextContent]:
    """Get the full writing spec for a chapter, merging project data with template data."""
    from sqlalchemy import select

    from app.extensions.knowledge_factory.models import ExtractionTemplate
    from app.extensions.models import ProjectChapter
    from app.extensions.project.service import _get_assigned_names, _get_chapter_or_404, _get_project_or_404

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

        all_chapters_stmt = select(ProjectChapter).where(ProjectChapter.project_id == chapter.project_id, ProjectChapter.parent_id == chapter.parent_id).order_by(ProjectChapter.sort_order)
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
