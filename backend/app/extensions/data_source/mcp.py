"""Data source MCP Server — exposes read-only data query tools to the agent.

DB connection: resolves the EXTENSIONS database URL via
``get_extensions_config().database.url`` (same DB where the data_sources table
lives). NEVER uses PROJECT_DB_URL — that is a different database.

Optional override: set DATA_SOURCE_DB_URL to point elsewhere.

KNOWN LIMITATIONS (MVP, documented for the operator):
- query_data_source enforces read-only via assert_readonly_select (keyword +
  multi-statement guard). It does NOT block side-effecting SQL functions
  (e.g. pg_terminate_backend) — restrict those via DB grants on the
  connecting role. It may over-block SELECTs whose string literals contain
  write verbs (fail-closed).
"""

from __future__ import annotations

import asyncio
import json
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


async def _resolve_db_url() -> str:
    if os.environ.get("DATA_SOURCE_DB_URL"):
        return os.environ["DATA_SOURCE_DB_URL"]
    from app.extensions.config import get_extensions_config

    return get_extensions_config().database.url


async def _run_in_db(func):
    """Run func(session) against the extensions DB with a short-lived engine."""
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
        name="list_data_sources",
        description="列出所有已配置的外部数据源(名称/类型/状态/最近同步时间)。",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_data_source_schema",
        description="获取某数据源的结构信息(database 返回表/字段概览,api 返回 url 与说明)。",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    ),
    Tool(
        name="query_data_source",
        description="从数据源取数。database 执行【只读】SQL(强制 SELECT/WITH,自动 LIMIT 200);api 发 GET。",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "params": {"type": "object", "description": "database: {sql}; api: {query, headers}"},
            },
            "required": ["name", "params"],
        },
    ),
    Tool(
        name="test_data_source",
        description="测试某数据源的连接。",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    ),
    Tool(
        name="list_datasets",
        description="列出某数据源下已标注的业务数据集(label/表/描述);无标注时自动列出源库的表名。",
        inputSchema={
            "type": "object",
            "properties": {"source_name": {"type": "string"}},
            "required": ["source_name"],
        },
    ),
    Tool(
        name="query_dataset",
        description="按业务名(label)查询某数据源的数据集:执行该数据集的 default_query(只读)。",
        inputSchema={
            "type": "object",
            "properties": {
                "source_name": {"type": "string"},
                "label": {"type": "string"},
            },
            "required": ["source_name", "label"],
        },
    ),
]


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


# ── handlers ──


async def _handle_list_data_sources(arguments: dict) -> list[TextContent]:
    from app.extensions.data_source.service import DataSourceService

    async def _q(session):
        rows = await DataSourceService.list(session)
        return [
            {
                "id": str(r.id),
                "name": r.name,
                "description": r.description,
                "type": r.type,
                "status": r.status,
                "last_sync_at": r.last_sync_at.isoformat() if r.last_sync_at else None,
            }
            for r in rows
        ]

    data = await _run_in_db(_q)
    return _ok({"success": True, "data_sources": data})


async def _handle_get_data_source_schema(arguments: dict) -> list[TextContent]:
    from app.extensions.data_source.service import DataSourceService

    name = arguments["name"]

    async def _q(session):
        return await DataSourceService.get_by_name(session, name)

    src = await _run_in_db(_q)
    if src is None:
        return _ok({"success": False, "message": f"数据源不存在: {name}"})
    if src.type == "database":
        try:
            tables = await DataSourceService.profile_tables(src)
            return _ok({"success": True, "name": name, "description": src.description, "type": "database", "tables": tables})
        except Exception as e:  # probe failure is non-fatal
            return _ok({"success": True, "name": name, "description": src.description, "type": "database", "tables": [], "probe_error": str(e)})
    return _ok({"success": True, "name": name, "description": src.description, "type": src.type, "connection_config_keys": list((src.connection_config or {}).keys())})


async def _handle_query_data_source(arguments: dict) -> list[TextContent]:
    from app.extensions.data_source.service import DataSourceService, assert_readonly_select

    name = arguments["name"]
    params = arguments.get("params") or {}

    async def _lookup(session):
        return await DataSourceService.get_by_name(session, name)

    src = await _run_in_db(_lookup)
    if src is None:
        return _ok({"success": False, "message": f"数据源不存在: {name}"})

    if src.type == "database":
        sql = params.get("sql", "")
        try:
            safe_sql = assert_readonly_select(sql)
        except ValueError as e:
            return _ok({"success": False, "message": str(e)})
        try:
            rows = await DataSourceService.run_readonly_query(src, safe_sql)
            return _ok({"success": True, "name": name, "sql": safe_sql, "row_count": len(rows), "rows": rows})
        except Exception as e:
            return _ok({"success": False, "message": f"{type(e).__name__}: {e}"})

    if src.type == "api":
        import httpx

        url = (src.connection_config or {}).get("url", "")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params.get("query"), headers=params.get("headers"))
            return _ok({"success": True, "name": name, "status_code": resp.status_code, "text": resp.text[:4000]})
        except Exception as e:
            return _ok({"success": False, "message": f"{type(e).__name__}: {e}"})

    return _ok({"success": False, "message": f"该类型({src.type})不支持 query,请用 get_data_source_schema"})


async def _handle_test_data_source(arguments: dict) -> list[TextContent]:
    from app.extensions.data_source.service import DataSourceService

    name = arguments["name"]

    async def _q(session):
        src = await DataSourceService.get_by_name(session, name)
        if src is None:
            return None
        return await DataSourceService.test_connection(src)

    result = await _run_in_db(_q)
    if result is None:
        return _ok({"success": False, "message": f"数据源不存在: {name}"})
    return _ok({"success": result.success, "message": result.message, "metadata": result.metadata})


# ── server ──

async def _handle_list_datasets(arguments: dict) -> list[TextContent]:
    from app.extensions.data_source.service import DataSourceService

    source_name = arguments["source_name"]

    async def _q(session):
        src = await DataSourceService.get_by_name(session, source_name)
        if src is None:
            return None
        datasets = await DataSourceService.list_datasets(session, src.id)
        return (src, datasets)

    result = await _run_in_db(_q)
    if result is None:
        return _ok({"success": False, "message": f"数据源不存在: {source_name}"})
    src, datasets = result
    if datasets:
        return _ok({
            "success": True,
            "source": source_name,
            "datasets": [
                {
                    "label": d.label,
                    "table_name": d.table_name,
                    "description": d.description,
                    "key_columns": d.key_columns,
                    "has_default_query": bool(d.default_query),
                }
                for d in datasets
            ],
        })
    # D fallback: no curated datasets -> auto-list tables from the source's own DB
    try:
        tables = await DataSourceService.profile_tables(src)
        return _ok({
            "success": True,
            "source": source_name,
            "auto": True,
            "note": "未标注数据集,自动列出源库的表与列",
            "datasets": [{"label": t["name"], "table_name": t["name"], "columns": t["columns"]} for t in tables],
        })
    except Exception as e:
        return _ok({"success": True, "source": source_name, "auto": True, "datasets": [], "note": f"无标注数据集,且自动列出失败: {e}"})


async def _handle_query_dataset(arguments: dict) -> list[TextContent]:
    from app.extensions.data_source.service import DataSourceService, assert_readonly_select

    source_name = arguments["source_name"]
    label = arguments["label"]

    async def _lookup(session):
        src = await DataSourceService.get_by_name(session, source_name)
        if src is None:
            return (None, None)
        ds = await DataSourceService.resolve_dataset(session, src.id, label)
        return (src, ds)

    src, ds = await _run_in_db(_lookup)
    if src is None:
        return _ok({"success": False, "message": f"数据源不存在: {source_name}"})
    if ds is None:
        return _ok({"success": False, "message": f"数据集不存在: {label};用 list_datasets 查看"})
    if not ds.default_query:
        return _ok({"success": False, "message": f"数据集'{label}'未配置 default_query;请用 query_data_source 编写 SQL"})
    try:
        safe_sql = assert_readonly_select(ds.default_query)
    except ValueError as e:
        return _ok({"success": False, "message": str(e)})
    try:
        rows = await DataSourceService.run_readonly_query(src, safe_sql)
        return _ok({"success": True, "source": source_name, "dataset": label, "sql": safe_sql, "row_count": len(rows), "rows": rows})
    except Exception as e:
        return _ok({"success": False, "message": f"{type(e).__name__}: {e}"})


server = Server("data_sources")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handlers = {
        "list_data_sources": _handle_list_data_sources,
        "get_data_source_schema": _handle_get_data_source_schema,
        "query_data_source": _handle_query_data_source,
        "test_data_source": _handle_test_data_source,
        "list_datasets": _handle_list_datasets,
        "query_dataset": _handle_query_dataset,
    }
    handler = handlers.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
