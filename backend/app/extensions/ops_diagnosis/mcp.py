"""Ops diagnosis MCP Server — read-only run/run-event queries for the agent.

EAI-CUSTOM (route-D, 2026-08): natural-language diagnosis of thread/run/skill
execution. Two tools: ops_list_thread_runs (run inventory + terminal state)
and ops_get_run_events (filtered event stream). Mirrors data_source/mcp.py
(raw mcp.server + stdio).

DB connection: resolves the harness application DB via
``get_app_config().database.app_sqlalchemy_url`` (the same DB where the
runs / run_events tables live — sqlite deerflow.db or postgres).
Optional override: OPS_DIAG_DB_URL.

TRUST BOUNDARY (v1, intranet ops model): the MCP stdio session carries no
caller identity, so an enabled server lets any agent read ANY user's thread
events. Default-off in shipped examples; enable only for admin/ops
deployments. See docs/superpowers/specs/2026-08-18-ops-diagnosis-skill-design.md §4.
"""

from __future__ import annotations

import asyncio
import json
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from app.extensions.ops_diagnosis import service


async def _resolve_db_url() -> str:
    if os.environ.get("OPS_DIAG_DB_URL"):
        return os.environ["OPS_DIAG_DB_URL"]
    from deerflow.config import get_app_config

    return get_app_config().database.app_sqlalchemy_url


async def _run_in_db(func):
    """Run func(session) against the harness app DB with a short-lived engine."""
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    url = await _resolve_db_url()
    engine = create_async_engine(url, pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            return await func(session)
    finally:
        await engine.dispose()


TOOLS = [
    Tool(
        name="ops_list_thread_runs",
        description="列出某线程的全部 run 清单: 状态(success/error/interrupted)、stop_reason(loop_capped/token_capped)、token 总量、LLM 调用数、事件数、起止时间。诊断第一步。",
        inputSchema={
            "type": "object",
            "properties": {"thread_id": {"type": "string", "description": "线程 ID (UUID)"}},
            "required": ["thread_id"],
        },
    ),
    Tool(
        name="ops_get_run_events",
        description="拉取线程/run 的执行事件流(run.start/llm.human.input/llm.ai.response/llm.tool.result/run.end 等)。支持 event_type 与 text_match(如 'Traceback'/'can't open file')服务端过滤,防大线程打爆上下文。返回按 seq 排序。",
        inputSchema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "线程 ID (UUID)"},
                "run_id": {"type": "string", "description": "可选,限定单个 run"},
                "event_type": {"type": "string", "description": "可选,如 llm.tool.result"},
                "text_match": {"type": "string", "description": "可选,内容子串过滤(错误特征检索)"},
                "limit": {"type": "integer", "description": "可选,默认 200,上限 1000"},
                "max_content_chars": {"type": "integer", "description": "可选,单事件内容截断长度,默认 2000"},
            },
            "required": ["thread_id"],
        },
    ),
]


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


async def _handle_list_thread_runs(arguments: dict) -> list[TextContent]:
    thread_id = arguments["thread_id"]

    async def _q(session):
        return await service.list_thread_runs(session, thread_id)

    try:
        runs = await _run_in_db(_q)
    except Exception as e:
        return _ok({"success": False, "message": f"{type(e).__name__}: {e}"})
    if not runs:
        return _ok({"success": True, "thread_id": thread_id, "runs": [], "note": "无 run 记录——run_events.backend 曾为 memory 或线程不存在"})
    return _ok({"success": True, "thread_id": thread_id, "run_count": len(runs), "runs": runs})


async def _handle_get_run_events(arguments: dict) -> list[TextContent]:
    kwargs = {
        "run_id": arguments.get("run_id"),
        "event_type": arguments.get("event_type"),
        "text_match": arguments.get("text_match"),
        "limit": int(arguments.get("limit") or service.DEFAULT_EVENT_LIMIT),
        "max_content_chars": int(arguments.get("max_content_chars") or service.DEFAULT_MAX_CONTENT_CHARS),
    }

    async def _q(session):
        return await service.get_run_events(session, arguments["thread_id"], **kwargs)

    try:
        result = await _run_in_db(_q)
    except Exception as e:
        return _ok({"success": False, "message": f"{type(e).__name__}: {e}"})
    return _ok({"success": True, "thread_id": arguments["thread_id"], **{k: v for k, v in kwargs.items() if v}, **result})


server = Server("ops_diagnosis")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handlers = {
        "ops_list_thread_runs": _handle_list_thread_runs,
        "ops_get_run_events": _handle_get_run_events,
    }
    handler = handlers.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments or {})


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
