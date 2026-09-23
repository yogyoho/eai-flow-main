"""Ontology 语义层 MCP Server — 8 只读工具 + 2 个动作工具，把市场域对象/链接暴露给 agent.

设计: docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md §7
计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T5（D4/D5）

工具分工（D5）：
- 本 server 提供**跨模块语义导航**（对象/链接/遍历/聚合）——先 describe_ontology 看全景。
- invoke_action / review_entity 是**写**工具（动作层，设计 §4）：经
  ``actions/executor.py::run_action_for_mcp`` → ``invoke_action_core`` 一条管线落库 + 记审计。
  review_entity 只是 review_entity.confirm/.reject 的具名薄包装，**不是第二条路径**。
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
    (
        "ontology_reason",
        "运行形式化推理：schema 重编→OWL 2 RL 闭包(graph:entailment)→CONSTRUCT 派生(graph:derived:*)。返回输入/物化三元组数与各规则派生计数（置信度门默认 0.7）。",
        {"type": "object", "properties": {"min_confidence": {"type": "number"}}, "required": []},
    ),
    (
        "invoke_action",
        "执行一个已声明的受治理动作（写回业务数据并记审计）。先用 describe_ontology 查看可用 action_id 清单与参数。写路径在服务端（事务/审计/身份标注）；本通道的授权在 MCP 配置层，不逐条校验动作声明的 required_permissions。",
        {
            "type": "object",
            "properties": {
                "action_id": {"type": "string", "description": "如 review_entity.confirm"},
                "pk": {"type": "string", "description": "目标对象主键(uuid)"},
                "params": {"type": "object", "description": "动作参数(按 describe_ontology 声明的形状)"},
            },
            "required": ["action_id", "pk"],
        },
    ),
    (
        "review_entity",
        "审核抽取实体的快捷入口（高频动作的具名包装，内部走同一条动作执行体）。decision=confirm 置 active，reject 置 rejected。",
        {
            "type": "object",
            "properties": {
                "pk": {"type": "string", "description": "实体主键(uuid)"},
                "decision": {"type": "string", "enum": ["confirm", "reject"]},
            },
            "required": ["pk", "decision"],
        },
    ),
]

TOOLS = [Tool(name=n, description=d, inputSchema=s) for n, d, s in _TOOLS_SPEC]

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from app.ontology.connectors import OntologyConnectors
        from app.ontology.engine import Engine
        from app.ontology.registry import get_registry

        _engine = Engine(get_registry, OntologyConnectors())
    return _engine


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


def _err(e: Exception) -> list[TextContent]:
    return _ok({"success": False, "error": f"{type(e).__name__}: {e}"})


# ── handlers ──


async def _describe(arguments: dict) -> list[TextContent]:
    from app.ontology.registry import get_registry_store

    store = get_registry_store()
    reg = store.get()  # D4: 逐调用指纹校验（变更自动热重载/失败保旧快照）
    full = bool(arguments.get("full"))
    meta = {"registry_version": reg.registry_version, "fingerprint": store._agg(reg)[:8], "object_type_count": len(reg.object_types), "link_type_count": len(reg.link_types)}
    # 可用动作清单（计划 Task 8 Step 5）：agent 靠它发现 action_id 与参数形状——
    # invoke_action 只收 action_id，没有清单就只能猜 id（猜错得到的是 404，不是提示）。
    # 两个分支都带：full=true 是在要**更多**细节，不是要更少的写入口。
    actions_payload = [
        {
            "id": a.id,
            "display_name": a.display_name,
            "description": a.description,
            "target": a.target,
            "required_permissions": a.required_permissions,
            "preconditions": [c.model_dump() for c in a.preconditions],
            "postconditions": [c.model_dump() for c in a.postconditions],
        }
        for a in reg.actions.values()
    ]
    if not full:
        return _ok(
            {
                "success": True,
                **meta,
                "hint": "full=true 查看属性/列映射",
                "object_types": [{"name": o.api_name, "display": o.display_name, "description": o.description} for o in reg.object_types.values()],
                "link_types": [{"name": lt.api_name, "source": lt.source, "target": lt.target, "enabled": lt.enabled, **({"note": lt.note} if not lt.enabled and lt.note else {})} for lt in reg.link_types.values()],
                "actions": actions_payload,
            }
        )
    objects_full = [o.model_dump(exclude={"properties"}) | {"properties": [p.model_dump() for p in o.visible_properties()]} for o in reg.object_types.values()]
    links_full = [lt.model_dump() for lt in reg.link_types.values()]
    return _ok({"success": True, **meta, "object_types": objects_full, "link_types": links_full, "actions": actions_payload})


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


async def _ontology_reason(a: dict) -> list[TextContent]:
    from app.ontology.kernel.service import get_kernel

    stats = get_kernel().refresh(min_confidence=a.get("min_confidence", 0.7))
    return _ok(
        {
            "success": True,
            "input_triples": stats.input_triples,
            "entailment_triples": stats.entailment_triples,
            "filtered_low_confidence": stats.filtered_low_confidence,
            "rule_counts": stats.rule_counts,
            "duration_ms": stats.duration_ms,
            "errors": stats.errors,
        }
    )


async def _aggregate(a: dict) -> list[TextContent]:
    out = await _get_engine().aggregate(a["object_type"], a["group_by"], metric=a.get("metric", "count"), metric_column=a.get("metric_column"), filters=a.get("filters"), limit=a.get("limit", 100))
    return _ok({"success": True, **out})


async def _invoke_action(arguments: dict) -> list[TextContent]:
    """写工具：动作层的通用入口（与 REST 共用 ``run_action_for_mcp`` → ``invoke_action_core``）。

    默认值用 ``""`` 而非缺失即抛：工具 schema 已把 action_id/pk 标成 required（合规的
    调用方一定给），但 agent 传空值/漏传时应当拿到一条**说明白**的结构化错误，
    而不是一个 KeyError（``""`` 会在 ``_resolve`` 处以 404 被拒，见 executor）。

    ``success: True`` 是**加**上去的（``invoke_action_core`` 的返回体里没有这个键，它按
    REST 的约定写成 HTTP 200 即成功）：MCP 没有状态码，``success`` 是本 server 唯一的成败
    信号——而它的错误侧（``_err``）一直写 ``success: false``。不加则成功与错误在形状上
    不对称：调用方只能靠"没有 error 键"来推断成功。
    """
    from app.ontology.actions.executor import ActionError, run_action_for_mcp

    try:
        return _ok({"success": True, **(await run_action_for_mcp(arguments.get("action_id", ""), arguments.get("pk", ""), "mcp"))})
    except ActionError as e:
        return _err(e)


async def _review_entity(arguments: dict) -> list[TextContent]:
    """``review_entity.confirm`` / ``.reject`` 的具名薄包装——**映射之后就没有第二条路径了**。

    ``decision`` 不在枚举内时不猜测、不落到默认分支（映射表缺失即拒）：猜错方向的
    审核动作（把 reject 当 confirm）比报错严重得多。
    """
    from app.ontology.actions.executor import ActionError, run_action_for_mcp

    mapping = {"confirm": "review_entity.confirm", "reject": "review_entity.reject"}
    action_id = mapping.get(arguments.get("decision"))
    if action_id is None:
        return _err(ValueError(f"decision must be one of {sorted(mapping)}"))
    try:
        return _ok({"success": True, **(await run_action_for_mcp(action_id, arguments.get("pk", ""), "mcp"))})
    except ActionError as e:
        return _err(e)


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
        "ontology_reason": _ontology_reason,
        "invoke_action": _invoke_action,
        "review_entity": _review_entity,
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
