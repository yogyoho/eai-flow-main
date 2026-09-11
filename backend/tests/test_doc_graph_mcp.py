"""doc_graph MCP server 测试——工具注册与分发（不启动 stdio）."""

import asyncio

from mcp.types import TextContent

from app.extensions.ontology.doc_graph.mcp import _HANDLERS, TOOLS, call_tool


def test_four_tools_registered():
    names = {t.name for t in TOOLS}
    assert names == {"ingest_extraction", "list_pending_review", "merge_entities", "unmerge"}


def test_handlers_cover_tools():
    assert set(_HANDLERS) == {t.name for t in TOOLS}


def test_unknown_tool_returns_text_error():
    out = asyncio.run(call_tool("nope", {}))
    assert isinstance(out[0], TextContent) and "Unknown tool" in out[0].text


def test_ingest_validation_error_is_structured():
    out = asyncio.run(call_tool("ingest_extraction", {"domain": "bid", "entities": [], "extra": 1}))
    assert isinstance(out[0], TextContent)
    assert "schema 校验失败" in out[0].text and '"success": false' in out[0].text
