"""doc_graph MCP server 测试——工具注册与分发（不启动 stdio）."""

import asyncio

from mcp.types import TextContent

from app.extensions.ontology.doc_graph.mcp import _HANDLERS, TOOLS, call_tool


def test_five_tools_registered():
    names = {t.name for t in TOOLS}
    assert names == {"ingest_extraction", "list_pending_review", "merge_entities", "unmerge", "evaluate_rules"}


def test_handlers_cover_tools():
    assert set(_HANDLERS) == {t.name for t in TOOLS}


def test_unknown_tool_returns_text_error():
    out = asyncio.run(call_tool("nope", {}))
    assert isinstance(out[0], TextContent) and "Unknown tool" in out[0].text


def test_ingest_validation_error_is_structured():
    out = asyncio.run(call_tool("ingest_extraction", {"domain": "bid", "entities": [], "extra": 1}))
    assert isinstance(out[0], TextContent)
    assert "schema 校验失败" in out[0].text and '"success": false' in out[0].text


def test_list_pending_review_sql_asyncpg_safe():
    """asyncpg 不能推断裸 :etype 的类型(AmbiguousParameterError)——必须 CAST(:etype AS text)。

    EAI-CUSTOM: SQL 已抽至 service.py(REST/MCP 共用), 检查对象随之迁移, 契约不变。
    """
    import inspect

    from app.extensions.ontology.doc_graph import service

    src = inspect.getsource(service.list_pending_review)
    assert "CAST(:etype AS text)" in src
    assert ":etype IS NULL" not in src
