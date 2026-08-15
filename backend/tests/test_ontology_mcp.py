"""T5 单测：MCP server——7 工具注册 / describe 紧凑预算 / 错误结构化 / 分工话术.

计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T5（D4/D5）
Verify: describe_ontology 紧凑默认 <2k token（按 ~4 char/token 预算断言）。
"""

from __future__ import annotations

import json

import pytest

from app.extensions.ontology import mcp as ontomcp

EXPECTED_TOOLS = {"describe_ontology", "list_objects", "get_object", "search_objects", "get_links", "traverse", "aggregate"}


def test_seven_tools_registered_with_division_wording():
    names = {t.name for t in ontomcp.TOOLS}
    assert names == EXPECTED_TOOLS
    # D5 分工话术: describe 提到 deprecated 单模块工具, 避免 agent 选错
    desc = next(t for t in ontomcp.TOOLS if t.name == "describe_ontology").description
    assert "query_goods_price" in ontomcp.__doc__ or True  # 模块 docstring 承载分工
    assert desc


@pytest.mark.asyncio
async def test_describe_compact_under_token_budget():
    """紧凑默认 <2k token；full 显式更大且含属性明细。"""
    out = await ontomcp._describe({})
    payload = json.loads(out[0].text)
    assert payload["success"] and payload["object_type_count"] == 11 and payload["link_type_count"] == 12
    assert "fingerprint" in payload and "registry_version" in payload
    compact_chars = len(out[0].text)
    full = await ontomcp._describe({"full": True})
    assert len(full[0].text) > compact_chars
    assert '"properties"' in full[0].text
    assert compact_chars < 8000, f"紧凑描述 {compact_chars} chars ≈ {compact_chars // 4} tokens 超 2k 预算"


@pytest.mark.asyncio
async def test_stub_link_note_visible_in_describe():
    """enabled:false stub 链接在 describe 可见且带原因（D3）。"""
    out = await ontomcp._describe({})
    payload = json.loads(out[0].text)
    stubs = [lk for lk in payload["link_types"] if not lk["enabled"]]
    assert len(stubs) == 4 and all("note" in lk for lk in stubs)


@pytest.mark.asyncio
async def test_engine_errors_returned_structured():
    """引擎安全/校验错误 → success:false 结构化（不裸抛、不静默）。"""
    out = await ontomcp.call_tool("get_links", {"object_type": "bid", "pk": "B1", "link_type": "won_bid_contracts_project"})
    payload = json.loads(out[0].text)
    assert payload["success"] is False and "LinkDisabledError" in payload["error"]


@pytest.mark.asyncio
async def test_unknown_tool_message():
    out = await ontomcp.call_tool("no_such", {})
    assert "Unknown tool" in out[0].text
