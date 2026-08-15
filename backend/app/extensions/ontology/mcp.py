"""Ontology 语义层 MCP Server — 7 只读工具，把市场域对象/链接暴露给 agent.

设计: docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md §7
计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T5（D4/D5）

工具分工（D5）：
- 本 server 提供**跨模块语义导航**（对象/链接/遍历/聚合）——先 describe_ontology 看全景。
- query_goods_price / query_part_price 是单模块**取数**工具（1b 起标 deprecated）。
  单模块明细查询仍可用它们；跨模块问题一律走 ontology 工具。

D4 双进程一致性：registry 每次调用重读指纹（gateway/MCP 各自进程独立校验），
describe_ontology 返回 registry_version + 指纹前 8 位供对账。
"""

from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

_TOOLS_SPEC = [
    (
        "describe_ontology",
        "查看本体语义地图：对象类型(名称+一行描述)、链接(含 enabled:false stub 及原因)。紧凑默认；full=true 输出完整属性/列映射。先看这个再查询。",
        {"type": "object", "properties": {"full": {"type": "boolean", "description": "默认 false=紧凑(类型+描述)；true=含属性/键/过滤器"}}, "required": []},
    ),
    (
        "list_objects",
        "按对象类型列出实例：typed filter（声明列+eq/ne/gt/gte/lt/lte）、q 全文搜索、keyset 分页(next_cursor)、排序。跨模块导航入口。",
        {
            "type": "object",
            "properties": {
                "object_type": {"type": "string"},
                "filters": {"type": "array", "items": {"type": "object", "properties": {"column": {"type": "string"}, "op": {"type": "string"}, "value": {}}}},
                "q": {"type": "string"},
                "limit": {"type": "integer"},
                "cursor": {"type": "string"},
                "order": {"type": "string"},
                "desc": {"type": "boolean"},
            },
            "required": ["object_type"],
        },
    ),
    (
        "get_object",
        "取单个对象实例（按主键）。字段名用 api_name(camelCase)，hidden 列永不透出。",
        {"type": "object", "properties": {"object_type": {"type": "string"}, "pk": {"type": "string"}}, "required": ["object_type", "pk"]},
    ),
    (
        "search_objects",
        "全文搜索某对象类型（q 命中 searchable 列，ILIKE 绑定参数）。是 list_objects q 参数的便捷封装。",
        {"type": "object", "properties": {"object_type": {"type": "string"}, "q": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["object_type", "q"]},
    ),
    (
        "get_links",
        "取某实例沿一条链接的对侧行（如合同条目→所属货物簇）。enabled:false 的 stub 链接会被拒绝并给原因。",
        {"type": "object", "properties": {"object_type": {"type": "string"}, "pk": {"type": "string"}, "link_type": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["object_type", "pk", "link_type"]},
    ),
    (
        "traverse",
        "多跳遍历（≤5 跳）：如 ['item_in_cluster','part_cluster_matches_goods_cluster'] 回答'这批备件对应哪些合同条目'。每跳 fan-out ≤200。",
        {"type": "object", "properties": {"object_type": {"type": "string"}, "pk": {"type": "string"}, "steps": {"type": "array", "items": {"type": "string"}}, "limit": {"type": "integer"}}, "required": ["object_type", "pk", "steps"]},
    ),
    (
        "aggregate",
        "按声明列分组聚合（count/sum/avg/min/max；sum/avg/min/max 需 metric_column 数值列）。如按货物簇统计合同金额。",
        {
            "type": "object",
            "properties": {
                "object_type": {"type": "string"},
                "group_by": {"type": "string"},
                "metric": {"type": "string"},
                "metric_column": {"type": "string"},
                "filters": {"type": "array", "items": {"type": "object"}},
                "limit": {"type": "integer"},
            },
            "required": ["object_type", "group_by"],
        },
    ),
]

TOOLS = [Tool(name=n, description=d, inputSchema=s) for n, d, s in _TOOLS_SPEC]

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from app.extensions.ontology.connectors import OntologyConnectors
        from app.extensions.ontology.engine import Engine
        from app.extensions.ontology.registry import get_registry

        _engine = Engine(get_registry, OntologyConnectors())
    return _engine


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


def _err(e: Exception) -> list[TextContent]:
    return _ok({"success": False, "error": f"{type(e).__name__}: {e}"})


# ── handlers ──


async def _describe(arguments: dict) -> list[TextContent]:
    from app.extensions.ontology.registry import get_registry_store

    store = get_registry_store()
    reg = store.get()  # D4: 逐调用指纹校验（变更自动热重载/失败保旧快照）
    full = bool(arguments.get("full"))
    meta = {"registry_version": reg.registry_version, "fingerprint": store._agg(reg)[:8], "object_type_count": len(reg.object_types), "link_type_count": len(reg.link_types)}
    if not full:
        return _ok(
            {
                "success": True,
                **meta,
                "hint": "full=true 查看属性/列映射",
                "object_types": [{"name": o.api_name, "display": o.display_name, "description": o.description} for o in reg.object_types.values()],
                "link_types": [{"name": lt.api_name, "source": lt.source, "target": lt.target, "enabled": lt.enabled, **({"note": lt.note} if not lt.enabled and lt.note else {})} for lt in reg.link_types.values()],
            }
        )
    objects_full = [o.model_dump(exclude={"properties"}) | {"properties": [p.model_dump() for p in o.visible_properties()]} for o in reg.object_types.values()]
    links_full = [lt.model_dump() for lt in reg.link_types.values()]
    return _ok({"success": True, **meta, "object_types": objects_full, "link_types": links_full})


async def _list_objects(a: dict) -> list[TextContent]:
    out = await _get_engine().list_objects(a["object_type"], filters=a.get("filters"), q=a.get("q"), limit=a.get("limit", 50), cursor=a.get("cursor"), order=a.get("order"), desc=bool(a.get("desc")))
    return _ok({"success": True, **out})


async def _get_object(a: dict) -> list[TextContent]:
    obj = await _get_engine().get_object(a["object_type"], a["pk"])
    if obj is None:
        return _ok({"success": False, "message": f"未找到 {a['object_type']}#{a['pk']}"})
    return _ok({"success": True, "data": obj})


async def _search_objects(a: dict) -> list[TextContent]:
    out = await _get_engine().list_objects(a["object_type"], q=a["q"], limit=a.get("limit", 20))
    return _ok({"success": True, **out})


async def _get_links(a: dict) -> list[TextContent]:
    out = await _get_engine().get_links(a["object_type"], a["pk"], a["link_type"], limit=a.get("limit", 100))
    return _ok({"success": True, **out})


async def _traverse(a: dict) -> list[TextContent]:
    out = await _get_engine().traverse(a["object_type"], a["pk"], a["steps"], limit=a.get("limit", 100))
    return _ok({"success": True, **out})


async def _aggregate(a: dict) -> list[TextContent]:
    out = await _get_engine().aggregate(a["object_type"], a["group_by"], metric=a.get("metric", "count"), metric_column=a.get("metric_column"), filters=a.get("filters"), limit=a.get("limit", 100))
    return _ok({"success": True, **out})


server = Server("ontology")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handlers = {
        "describe_ontology": _describe,
        "list_objects": _list_objects,
        "get_object": _get_object,
        "search_objects": _search_objects,
        "get_links": _get_links,
        "traverse": _traverse,
        "aggregate": _aggregate,
    }
    handler = handlers.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        return await handler(arguments or {})
    except Exception as e:  # 引擎安全/校验错误以结构化错误返回 agent
        return _err(e)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
