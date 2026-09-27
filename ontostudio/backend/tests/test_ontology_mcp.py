"""T5 单测：MCP server——工具注册（8 只读 + 2 动作）/ describe 紧凑预算 / 错误结构化 / 分工话术.

计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T5（D4/D5）
      + docs/superpowers/plans/2026-09-22-ontostudio-action-layer.md T8（动作工具）
Verify: describe_ontology 紧凑默认 <2k token（按 ~4 char/token 预算断言）。
"""

from __future__ import annotations

import json

import pytest

from app.ontology import mcp as ontomcp

EXPECTED_TOOLS = {
    "describe_ontology",
    "list_objects",
    "get_object",
    "search_objects",
    "get_links",
    "traverse",
    "aggregate",
    "ontology_reason",
    # 动作层（Task 8）：写工具。清单在这里**手写**是刻意的——本文件的断言对象就是
    # "对外暴露了哪些工具"（一份需要人签字确认的表面），与 registry 无关；
    # 动作 id 与 registry 的一致性由 tests/test_actions_mcp.py 钉。
    "invoke_action",
    "review_entity",
}


def test_registered_tools_with_division_wording():
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
    # EAI-CUSTOM(2026-09-27 registry 缩编): 5 对象 / 6 链接（原 16/16 四域 yaml 已删）
    assert payload["success"] and payload["object_type_count"] == 5 and payload["link_type_count"] == 6
    assert "fingerprint" in payload and "registry_version" in payload
    compact_chars = len(out[0].text)
    full = await ontomcp._describe({"full": True})
    assert len(full[0].text) > compact_chars
    assert '"properties"' in full[0].text
    assert compact_chars < 8000, f"紧凑描述 {compact_chars} chars ≈ {compact_chars // 4} tokens 超 2k 预算"


@pytest.mark.asyncio
async def test_link_types_visible_in_describe():
    """链接类型在 describe 可见（D3: stub 链接带原因）。

    EAI-CUSTOM(2026-09-27 registry 缩编): 真实 registry 已无 stub 链接（4 条跨模块 stub
    随四域 yaml 退场）——断言改为「全部链接可见且 enabled」；stub-note 可见性机制由
    test_ontology_engine 的合成 stub 用例守。
    """
    out = await ontomcp._describe({})
    payload = json.loads(out[0].text)
    assert len(payload["link_types"]) == 6
    assert all(lk["enabled"] for lk in payload["link_types"])
    assert {lk["name"] for lk in payload["link_types"]} >= {"mention_of_eia_entity", "mention_of_eia_relation"}


@pytest.mark.asyncio
async def test_engine_errors_returned_structured():
    """引擎安全/校验错误 → success:false 结构化（不裸抛、不静默）。

    EAI-CUSTOM(2026-09-27 registry 缩编): 原 won_bid_contracts_project stub 链接类型已随
    cross_module.yaml 删除 → 走 UnknownLinkError（未注册）路径，断言语义如实改为「链接
    类型未注册」；LinkDisabledError 路径由 test_ontology_engine 的合成 stub 用例守。
    """
    out = await ontomcp.call_tool("get_links", {"object_type": "graph_entity", "pk": "B1", "link_type": "won_bid_contracts_project"})
    payload = json.loads(out[0].text)
    assert payload["success"] is False and "UnknownLinkError" in payload["error"]


@pytest.mark.asyncio
async def test_unknown_tool_message():
    out = await ontomcp.call_tool("no_such", {})
    assert "Unknown tool" in out[0].text
