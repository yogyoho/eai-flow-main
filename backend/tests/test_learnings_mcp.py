"""learnings MCP server 测试 — 注册/分发/身份绑定(fail-closed), 不启动 stdio.

房屋模式参照 backend/tests/test_doc_graph_mcp.py.
"""

import asyncio

from mcp.types import TextContent

from app.extensions.learnings.mcp import (
    _HANDLERS,
    TOOLS,
    call_tool,
    parse_identity,
)

WIN_CWD = "D:\\eai\\backend\\.deer-flow\\users\\06824890\\threads\\f1b400ba\\user-data\\workspace"
UX_CWD = "/app/backend/.deer-flow/users/06824890/threads/f1b400ba/user-data/workspace"
ANON_CWD = "/app/backend/.deer-flow/threads/f1b400ba/user-data/workspace"


def test_four_tools_registered():
    assert {t.name for t in TOOLS} == {"surface", "log_learning", "stats", "resolve"}


def test_handlers_cover_tools():
    assert set(_HANDLERS) == {t.name for t in TOOLS}


def test_unknown_tool_returns_text_error():
    out = asyncio.run(call_tool("nope", {}))
    assert isinstance(out[0], TextContent) and "Unknown tool" in out[0].text


def test_parse_identity_posix_and_windows():
    assert parse_identity(UX_CWD) == ("06824890", "f1b400ba")
    assert parse_identity(WIN_CWD) == ("06824890", "f1b400ba")


def test_parse_identity_fails_closed_on_anonymous_layout():
    """无 users/ 段(匿名 thread) -> None -> 工具拒绝写(fail-closed, D5/OV2)."""
    assert parse_identity(ANON_CWD) is None
    assert parse_identity("/app/backend") is None


def test_tool_rejects_when_identity_unavailable(monkeypatch):
    """身份推导失败 -> 所有工具结构化拒绝, 绝不落库."""
    monkeypatch.setattr("app.extensions.learnings.mcp.parse_identity", lambda cwd=None: None)
    out = asyncio.run(call_tool("log_learning", {"summary": "s", "kind": "error", "area": "runtime"}))
    payload = out[0].text
    assert "identity-unavailable" in payload and '"success": false' in payload


def test_tool_rejects_mismatched_thread_id(monkeypatch):
    """模型供错 thread_id(跨用户写穿向量) -> 拒绝."""
    monkeypatch.setattr(
        "app.extensions.learnings.mcp.parse_identity", lambda cwd=None: ("u-real", "t-real")
    )
    out = asyncio.run(call_tool("surface", {"thread_id": "t-foreign"}))
    assert "thread-id-mismatch" in out[0].text


def test_validation_error_is_structured(monkeypatch):
    monkeypatch.setattr(
        "app.extensions.learnings.mcp.parse_identity", lambda cwd=None: ("u-real", "t-real")
    )
    out = asyncio.run(call_tool("log_learning", {"summary": "s", "kind": "not-a-kind", "area": "runtime"}))
    assert '"success": false' in out[0].text and "kind" in out[0].text
