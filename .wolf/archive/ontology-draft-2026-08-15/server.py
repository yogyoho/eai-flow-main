"""Unified ontology MCP server — read-only semantic query/navigation tools for the agent.

One semantic layer over the market/analysis modules (mother spec §7). Read-only
by construction. Registered in extensions_config.json (stdio), env overrides:
ONTOLOGY_DB_URL (extensions DB) — see bug-698 (MCP subprocess env not inherited,
write it explicitly in the server registration).
"""

from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from app.extensions.ontology.engine.query import QueryEngine
from app.extensions.ontology.registry import RegistryCache

_cache = RegistryCache()
_engine: QueryEngine | None = None


def _get_engine() -> QueryEngine:
    global _engine
    if _engine is None:
        from app.extensions.ontology.connectors import data_source as ds
        from app.extensions.ontology.connectors import postgres_ext as pg

        _engine = QueryEngine(_cache.get(), pg_connector=pg, ds_connector=ds)
    return _engine


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


TOOLS = [
    Tool(
        name="describe_ontology",
        description="描述 ontology 注册表:对象类型/链接/属性(含描述/单位/枚举,隐藏敏感字段)。可选 object_type 只看单个。",
        inputSchema={"type": "object", "properties": {"object_type": {"type": "string", "description": "对象类型 api_name,省略则全部"}}},
    ),
    Tool(
        name="list_objects",
        description="查询对象列表:typed filter(eq/ne/gt/gte/lt/lte/in/between/and/or/not/is_null)+排序+keyset 分页。",
        inputSchema={
            "type": "object",
            "properties": {
                "object_type": {"type": "string"},
                "filter": {"type": "object"},
                "order_by": {"type": "string"},
                "limit": {"type": "integer", "maximum": 200},
                "cursor": {"type": "string"},
                "include_properties": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["object_type"],
        },
    ),
    Tool(
        name="get_object",
        description="按主键取单个对象。",
        inputSchema={"type": "object", "properties": {"object_type": {"type": "string"}, "primary_key": {}, "include_properties": {"type": "array", "items": {"type": "string"}}}, "required": ["object_type", "primary_key"]},
    ),
    Tool(
        name="search_objects",
        description="在 searchable 文本属性上模糊搜索对象。",
        inputSchema={"type": "object", "properties": {"object_type": {"type": "string"}, "term": {"type": "string"}, "limit": {"type": "integer", "maximum": 50}}, "required": ["object_type", "term"]},
    ),
    Tool(
        name="get_links",
        description="沿链接类型获取关联对象(正向或反向自动解析,跨模块链接可跨库)。",
        inputSchema={
            "type": "object",
            "properties": {"object_type": {"type": "string"}, "primary_key": {}, "link_type": {"type": "string"}, "limit": {"type": "integer", "maximum": 200}, "cursor": {"type": "string"}},
            "required": ["object_type", "primary_key", "link_type"],
        },
    ),
    Tool(
        name="traverse_path",
        description="沿点分链接路径多跳遍历(如 item_in_cluster.part_cluster_matches_goods_cluster),跨模块可参与。",
        inputSchema={"type": "object", "properties": {"object_type": {"type": "string"}, "primary_key": {}, "path": {"type": "string"}, "limit": {"type": "integer", "maximum": 200}}, "required": ["object_type", "primary_key", "path"]},
    ),
    Tool(
        name="aggregate_objects",
        description="对象集合级聚合(group_by + count/sum/avg/min/max/percentile_cont),单查询不 N+1。",
        inputSchema={
            "type": "object",
            "properties": {
                "object_type": {"type": "string"},
                "group_by": {"type": "string"},
                "metric": {"type": "object", "description": "{field, fn, p?}"},
                "filter": {"type": "object"},
            },
            "required": ["object_type"],
        },
    ),
]


def _describe(engine: QueryEngine, object_type: str | None = None) -> dict:
    reg = _cache.get()
    if object_type:
        obj = reg.object_by_name(object_type)
        if obj is None:
            raise ValueError(f"unknown object type: {object_type}")
        objs = [obj]
    else:
        objs = [o for o in reg.object_types if o.enabled]
    links = [link for link in reg.link_types if link.enabled]
    return {
        "schema_version": reg.schema_version,
        "registry_version": reg.registry_version,
        "object_types": [
            {
                "api_name": o.api_name,
                "display_name": o.display_name,
                "description": o.description,
                "domain": o.domain,
                "icon": o.icon,
                "access": {"path": o.access.path, "table": o.access.table or o.access.table_name},
                "pk": o.pk.api_name,
                "properties": [
                    {"api_name": p.api_name, "type": p.type, "description": p.description, "format": p.format, "unit": p.unit, "enum": p.enum, "filterable": p.filterable, "searchable": p.searchable} for p in o.properties if not p.hidden
                ],
            }
            for o in objs
        ],
        "link_types": [
            {"api_name": link.api_name, "display_name": link.display_name, "source": link.source, "target": link.target, "cardinality": link.cardinality, "reverse": link.reverse, "cross_module": link.cross_module} for link in links
        ],
    }


async def _handle_describe(arguments: dict) -> list[TextContent]:
    try:
        return _ok({"success": True, **_describe(_get_engine(), arguments.get("object_type"))})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


async def _handle_list(arguments: dict) -> list[TextContent]:
    try:
        data = await _get_engine().list(
            arguments["object_type"],
            arguments.get("filter"),
            arguments.get("order_by"),
            arguments.get("limit", 50),
            arguments.get("cursor"),
            arguments.get("include_properties"),
        )
        return _ok({"success": True, **data})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


async def _handle_get(arguments: dict) -> list[TextContent]:
    try:
        obj = await _get_engine().get(arguments["object_type"], arguments["primary_key"])
        return _ok({"success": True, "object": obj})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


async def _handle_search(arguments: dict) -> list[TextContent]:
    try:
        data = await _get_engine().search(arguments["object_type"], arguments["term"], arguments.get("limit", 20))
        return _ok({"success": True, **data})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


async def _handle_links(arguments: dict) -> list[TextContent]:
    try:
        data = await _get_engine().get_links(
            arguments["object_type"],
            arguments["primary_key"],
            arguments["link_type"],
            arguments.get("limit", 50),
            arguments.get("cursor"),
        )
        return _ok({"success": True, **data})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


async def _handle_traverse(arguments: dict) -> list[TextContent]:
    try:
        data = await _get_engine().traverse_path(arguments["object_type"], arguments["primary_key"], arguments["path"], arguments.get("limit", 50))
        return _ok({"success": True, **data})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


async def _handle_aggregate(arguments: dict) -> list[TextContent]:
    try:
        data = await _get_engine().aggregate(arguments["object_type"], arguments.get("group_by"), arguments.get("metric"), arguments.get("filter"))
        return _ok({"success": True, "rows": data})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


TOOL_HANDLERS = {
    "describe_ontology": _handle_describe,
    "list_objects": _handle_list,
    "get_object": _handle_get,
    "search_objects": _handle_search,
    "get_links": _handle_links,
    "traverse_path": _handle_traverse,
    "aggregate_objects": _handle_aggregate,
}

server = Server("ontology")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
