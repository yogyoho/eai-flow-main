"""Knowledge Factory MCP Server — exposes template, domain, and knowledge tools to DeerFlow lead_agent.

Environment variables:
    KF_DATABASE_URL — PostgreSQL connection string (required)
"""

from __future__ import annotations

import asyncio
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ── Database helpers ──


async def _run_in_db(func):
    """Run an async function with a database session, return its result.

    Creates a short-lived engine + session, ensuring engine.dispose() is
    called even if func raises, so connections are never leaked.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

    db_url = os.environ.get("KF_DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("KF_DATABASE_URL environment variable is required")

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
        name="kf_resolve_template",
        description=(
            "智能匹配并返回最适合的报告模板。按领域关键词、行业和报告类型查找，"
            "使用三层匹配策略（精确匹配→关键词匹配→宽松匹配）自动选择最佳模板。"
            "返回完整的章节结构、生成提示、合规规则和内容契约。"
            "当模板不可用时返回 found=false，调用方应回退到内置参考文档。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "domain_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "报告领域关键词列表，如 ['消防设计专篇', '消防设计报告']",
                },
                "industry": {
                    "type": "string",
                    "description": "行业分类，如 '化工'、'石化'、'建筑'",
                },
                "report_type": {
                    "type": "string",
                    "description": "报告类型精确匹配，如 '消防设计'",
                },
                "min_completeness_score": {
                    "type": "integer",
                    "description": "最低完整度评分阈值（0-100），低于此值的模板将被过滤",
                    "default": 0,
                },
            },
            "required": ["domain_keywords"],
        },
    ),
    Tool(
        name="kf_get_template",
        description="按模板 ID 获取完整模板内容，包含所有章节的详细元数据。",
        inputSchema={
            "type": "object",
            "properties": {
                "template_id": {"type": "string", "description": "模板 UUID"},
            },
            "required": ["template_id"],
        },
    ),
    Tool(
        name="kf_query_templates",
        description="按领域、名称关键词和状态搜索模板列表（分页）。",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "领域 ID 过滤"},
                "name": {"type": "string", "description": "按模板名称模糊搜索"},
                "status": {"type": "string", "description": "状态过滤，默认 'published'"},
                "limit": {"type": "integer", "description": "返回数量上限，默认 10"},
            },
        },
    ),
    Tool(
        name="kf_list_domains",
        description="列出所有可用的知识提取领域，可按行业过滤。用于发现系统支持哪些报告类型。",
        inputSchema={
            "type": "object",
            "properties": {
                "industry": {"type": "string", "description": "按行业分类过滤，如 '化工'"},
            },
        },
    ),
]


# ── Tool handlers ──

# Import tool handlers lazily to avoid circular imports at module level


async def _handle_resolve_template(arguments: dict) -> list[TextContent]:
    from app.extensions.knowledge_factory.mcp_server.tools.template_tools import handle_kf_resolve_template
    return await handle_kf_resolve_template(arguments, _run_in_db)


async def _handle_get_template(arguments: dict) -> list[TextContent]:
    from app.extensions.knowledge_factory.mcp_server.tools.template_tools import handle_kf_get_template
    return await handle_kf_get_template(arguments, _run_in_db)


async def _handle_query_templates(arguments: dict) -> list[TextContent]:
    from app.extensions.knowledge_factory.mcp_server.tools.template_tools import handle_kf_query_templates
    return await handle_kf_query_templates(arguments, _run_in_db)


async def _handle_list_domains(arguments: dict) -> list[TextContent]:
    from app.extensions.knowledge_factory.mcp_server.tools.domain_tools import handle_kf_list_domains
    return await handle_kf_list_domains(arguments, _run_in_db)


# ── Server setup ──

server = Server("knowledge-factory")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handlers = {
        "kf_resolve_template": _handle_resolve_template,
        "kf_get_template": _handle_get_template,
        "kf_query_templates": _handle_query_templates,
        "kf_list_domains": _handle_list_domains,
    }
    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments)


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
