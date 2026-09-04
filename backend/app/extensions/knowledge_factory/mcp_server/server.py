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
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
    Tool(
        name="kf_extract_template",
        description=(
            "从 Word/PDF 报告文件中提取报告模板。传入文件路径列表，"
            "运行 5 阶段抽取流水线（文档解析→章节推断→元数据抽取→模板融合→合规校验），"
            "返回完整的章节结构、内容契约和富元数据（表格/公式/脚本/剖面）。"
            "提取的模板可通过 kf_resolve_template 消费。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "source_report_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "知识库中已上传文档的 UUID 列表（主要输入方式）",
                },
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "服务器上 Word/PDF 文件的绝对路径（未来直接解析路径，当前仅 .md/.txt 可用）",
                },
                "domain": {
                    "type": "string",
                    "description": "领域标识，如 'environmental_impact_assessment'，默认 'default'",
                    "default": "default",
                },
                "industry": {
                    "type": "string",
                    "description": "行业分类，如 'coal'、'chemical'",
                },
                "report_type": {
                    "type": "string",
                    "description": "报告类型，如 '环评报告'、'水保方案'",
                },
                "template_name": {
                    "type": "string",
                    "description": "模板名称，默认自动生成",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "最大章节嵌套深度（1-6），默认 4",
                    "default": 4,
                },
                "llm_model": {
                    "type": "string",
                    "description": "指定 LLM 模型，默认使用系统基本设置中的模型",
                },
            },
            "required": ["file_paths"],
        },
    ),
    Tool(
        name="kf_check_compliance",
        description=("对生成的章节内容执行合规性校验。传入章节全文 Markdown，自动匹配适用的合规规则（或指定 rule_ids），返回逐条规则的通过/不通过/警告结果，不通过项附带修改建议。"),
        inputSchema={
            "type": "object",
            "properties": {
                "chapter_content": {
                    "type": "string",
                    "description": "待校验的章节全文 Markdown 内容（必填）",
                },
                "rule_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "指定规则 ID 列表；为空或不填则自动匹配所有启用规则",
                },
                "chapter_number": {
                    "type": "integer",
                    "description": "章节编号（1-14），辅助规则匹配",
                },
                "report_type": {
                    "type": "string",
                    "description": "报告类型，如 '环评报告'",
                },
                "industry": {
                    "type": "string",
                    "description": "行业分类，如 '煤炭'",
                },
            },
            "required": ["chapter_content"],
        },
    ),
    Tool(
        name="kf_search_knowledge",
        description=(
            "本地知识库全文检索（RAGFlow 向量+关键词混合）——查标准/规范/法规/行业标准的首选工具，"
            "优先于 web_search。凡用户提到 标准编号（GB/DZ/HG/DL/TB…）、规范、法规、行业标准、"
            "历史报告、样例报告、项目资料、合同条款，必须先用本工具检索本地知识库，"
            "本地无命中或需要最新官方发布信息时才改用 web_search。"
            "默认检索所有已同步知识库，可用 kb_name 模糊过滤。"
            "返回命中文档块（所属知识库/文档名/相似度/原文内容）。"
            "可选 filters 按文档元数据收窄范围（行业领域/标准号/关键词/生效日期区间），"
            "行业领域取值参考业务字典的业务领域（如 环境评价/地质勘查）。"
            "注意：本地知识库文档没有网页 URL，引用时禁止编造链接（如 knowledge-factory.internal 等），"
            "来源只写 知识库名 + 文档名（可加相似度），不带 url 字段。"
            "检索不到时换关键词重试或降低 similarity_threshold。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索问题或关键词（必填）",
                },
                "kb_name": {
                    "type": "string",
                    "description": "知识库名称模糊过滤；不填 = 检索全部知识库",
                },
                "filters": {
                    "type": "object",
                    "description": "按文档元数据过滤（可选）：{sector: 行业领域, law_number: 标准号, keywords: [关键词], effective_date_from/to: 生效日期区间}；均为 AND 语义",
                    "properties": {
                        "sector": {"type": "string", "description": "行业领域精确匹配"},
                        "law_number": {"type": "string", "description": "标准号精确匹配"},
                        "keywords": {"type": "array", "items": {"type": "string"}, "description": "关键词包含匹配"},
                        "effective_date_from": {"type": "string", "description": "生效日期下限 YYYY-MM-DD"},
                        "effective_date_to": {"type": "string", "description": "生效日期上限 YYYY-MM-DD"},
                    },
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回块数上限，默认 5",
                },
                "similarity_threshold": {
                    "type": "number",
                    "description": "相似度阈值，默认 0.2；命中过少时可降低",
                },
            },
            "required": ["query"],
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


async def _handle_extract_template(arguments: dict) -> list[TextContent]:
    from app.extensions.knowledge_factory.mcp_server.tools.template_tools import handle_kf_extract_template

    return await handle_kf_extract_template(arguments, _run_in_db)


async def _handle_check_compliance(arguments: dict) -> list[TextContent]:
    from app.extensions.knowledge_factory.mcp_server.tools.compliance_tools import handle_kf_check_compliance

    return await handle_kf_check_compliance(arguments, _run_in_db)


async def _handle_search_knowledge(arguments: dict) -> list[TextContent]:
    from app.extensions.knowledge_factory.mcp_server.tools.search_tools import handle_kf_search_knowledge

    return await handle_kf_search_knowledge(arguments, _run_in_db)


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
        "kf_check_compliance": _handle_check_compliance,
        "kf_extract_template": _handle_extract_template,
        "kf_search_knowledge": _handle_search_knowledge,
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
