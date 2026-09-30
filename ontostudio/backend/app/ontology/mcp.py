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

# ---- EIA 图谱双库归属 scope 语义（子项目 3.5 §2；归属模型见 scripts/eia_scope_tag.py）----
# attrs.scope 三态: sample=样例类比素材(A 库, 现存语料主体) / domain_common=领域共性知识(B 库,
# 挂载点 etype=domain_pattern 已注册未填充) / project=项目工作本(C 库, 机制预留)。
# 有效归属规则: 未打标行按 sample 归属——现存语料定义上就是样例库，打标前旧数据不因缺标失联
# （kernel 需重载后 attr/scope 才入图，缺省规则让过滤在重载前后语义连续）。
_SCOPES = ("all", "sample", "project", "domain_common")
_DEFAULT_SCOPE = "sample"
_SCOPE_PARAM_SPEC = {
    "type": "string",
    "enum": list(_SCOPES),
    "description": "归属库过滤: all=不过滤(默认)；sample=样例类比素材；project=项目工作本；domain_common=领域共性知识。未打标行按 sample 归属。",
}

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
    # ---- EIA 校验规则 / 写作消费通道（子项目 3, spec 2026-09-30 §6；只读，走 sigma kernel 图）----
    (
        "query_entity",
        "按名称/实体类型查询环评（EIA）图实体并带邻域关系（出/入边+对端名）。写作取材与跨章节核对入口。etype 如 waste_stream/sensitive_point/emission_point；name 支持子串；scope 按图谱归属库过滤（样例素材/项目工作本/领域共性）。",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "实体名子串（与 etype 至少给一个）"},
                "etype": {"type": "string", "description": "实体类型（registry eia etype，如 pollution_source）"},
                "scope": _SCOPE_PARAM_SPEC,
                "limit": {"type": "integer", "description": "返回实体数上限（默认 10，最大 50）"},
            },
            "required": [],
        },
    ),
    (
        "check_consistency",
        "对 EIA 图全量跑 12 条校验规则（矸石闭合/敏感点防护/监测覆盖/限值适配等），返回各规则违规计数+样例消息+分级汇总；scope 可把体检限定在某个归属库（涉事节点后置过滤）。报告出稿前体检用。",
        {"type": "object", "properties": {"scope": _SCOPE_PARAM_SPEC}, "required": []},
    ),
    (
        "get_writing_context",
        "取某实体的写作上下文：实体+邻域关系+关联阈值/条款/标准等约束实体的 attrs。写章节前注入核心，防跨章节数据打架。",
        {"type": "object", "properties": {"entity_name": {"type": "string", "description": "实体名（精确优先，退化为子串）"}}, "required": ["entity_name"]},
    ),
    (
        "get_rule_violations",
        "取校验规则违规清单（完整变量绑定+message）。可按 severity=error|warn|info 或 rule_id 过滤；只返回有违规的规则。",
        {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["error", "warn", "info"]},
                "rule_id": {"type": "string", "description": "如 rule_gangue_closure"},
                "limit": {"type": "integer", "description": "每规则违规返回上限（默认 50，最大 1000）"},
            },
            "required": [],
        },
    ),
    (
        "query_analogy",
        "类比素材与领域规律查询（A 库样例 scope=sample + B 库领域共性 scope=domain_common；C 库 project 不入本通道，走 query_entity scope=project）：查实体+邻接关系，每条必带 source_report 可溯源到来源报告。"
        "etype=domain_pattern 查 B 库蒸馏规律条目（attrs 含 pattern_type/subject_name/object_name/support_count）。etype 或 label_contains 至少给一个。类比值引用须在写作侧标注 param_source=analog_mine+来源报告（纪律在技能侧）。",
        {
            "type": "object",
            "properties": {
                "etype": {"type": "string", "description": "实体类型（registry eia etype，如 waste_stream；domain_pattern=领域规律条目）"},
                "label_contains": {"type": "string", "description": "名称子串（与 etype 至少给一个）"},
                "limit": {"type": "integer", "description": "返回实体数上限（默认 10，最大 50）"},
            },
            "required": [],
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


# ── EIA 消费通道 handlers（子项目 3，只读，走 sigma kernel 图）──


def _kernel_store():
    from app.ontology.kernel.service import get_kernel

    return get_kernel().store


_EIA_NS = "https://ontology.eai-flow.com/eia#"
_ASSERTED = "graph:asserted"
# 写作上下文的约束类邻居（阈值/条款/标准/规划/措施规格——attrs 承载裁决数值）
_CONSTRAINT_ETYPES = ("standard_threshold", "regulation_clause", "emission_standard", "planning_scheme", "measure_spec")


def _etype_class_map_eia() -> dict[str, str]:
    """etype → 实体类 IRI（如 waste_stream → eia:WasteStream）。"""
    from app.ontology.kernel.compile import collect_vocabularies
    from app.ontology.kernel.loader import etype_class_map
    from app.ontology.registry import get_registry

    registry = get_registry()
    vocab = collect_vocabularies(registry)["eia"]
    return {etype: str(vocab.class_ref(cls)) for etype, cls in etype_class_map(registry, "eia").items()}


def _class_etype_map() -> dict[str, str]:
    return {cls: etype for etype, cls in _etype_class_map_eia().items()}


def _local(iri: str, ns: str) -> str:
    return iri[len(ns):] if iri.startswith(ns) else iri


def _names_for(store, iris: list[str]) -> dict[str, str]:  # noqa: ANN001 - OxStore
    """一批 IRI → norm_name（邻域对端名回填，单查询）。"""
    if not iris:
        return {}
    uniq = list(dict.fromkeys(iris))[:200]
    lst = ", ".join(f"<{i}>" for i in uniq)
    rows = store.query(f"SELECT ?e ?n WHERE {{ GRAPH <{_ASSERTED}> {{ ?e <{_EIA_NS}attr/norm_name> ?n . FILTER(?e IN ({lst})) }} }}")
    return {r["e"]: r["n"] for r in rows if r.get("n") is not None}


def _neighborhood(store, iri: str, cap: int = 20) -> dict:  # noqa: ANN001 - OxStore
    """实体出/入关系邻域（谓词取局部名，对端回填名）。"""
    pred_ns = _EIA_NS + "predicate/"
    out_rows = [r for r in store.query(f"SELECT ?p ?o WHERE {{ GRAPH <{_ASSERTED}> {{ <{iri}> ?p ?o }} }}") if isinstance(r.get("p"), str) and r["p"].startswith(pred_ns)][:cap]
    in_rows = [r for r in store.query(f"SELECT ?s ?p WHERE {{ GRAPH <{_ASSERTED}> {{ ?s ?p <{iri}> }} }}") if isinstance(r.get("p"), str) and r["p"].startswith(pred_ns)][:cap]
    names = _names_for(store, [r["o"] for r in out_rows] + [r["s"] for r in in_rows])
    return {
        "out": [{"predicate": _local(r["p"], pred_ns), "target": r["o"], "target_name": names.get(r["o"])} for r in out_rows],
        "in": [{"predicate": _local(r["p"], pred_ns), "source": r["s"], "source_name": names.get(r["s"])} for r in in_rows],
    }


def _resolve_entities(store, name: str, limit: int = 5) -> list[dict]:  # noqa: ANN001 - OxStore
    """按名解析实体：精确匹配优先，退化为子串。"""
    rows = store.query(
        f"SELECT ?e ?name WHERE {{ GRAPH <{_ASSERTED}> {{ ?e <{_EIA_NS}attr/norm_name> ?name . FILTER(CONTAINS(?name, {json.dumps(name, ensure_ascii=False)})) }} }} LIMIT {int(limit)}"
    )
    exact = [r for r in rows if r.get("name") == name]
    return exact + [r for r in rows if r.get("name") != name]


def _iri_bindings(row: dict) -> list[str]:
    """违规行里的 IRI 形绑定值（http/urn 前缀——名字/计数/消息不会撞上）。"""
    return [v for v in row.values() if isinstance(v, str) and v.startswith(("http://", "https://", "urn:"))]


def _validate_scope(a: dict) -> tuple[str | None, list[TextContent] | None]:
    """scope 参数解析：缺省 all；非法值 fail-closed 报错（不静默回落 all——静默回落会让
    以为在查项目库的调用方拿到样例数据，比报错危险）。"""
    scope = (a.get("scope") or "all").strip()
    if scope not in _SCOPES:
        return None, _err(ValueError(f"scope 须为 {_SCOPES} 之一，得: {scope!r}"))
    return scope, None


def _scope_filter_sparql(scope: str) -> str:
    """query_entity 的 scope 谓词片段（"all"=空）。FILTER 必须在 OPTIONAL 组**外**：放组内时
    「不满足过滤」的 OPTIONAL 解被弃、外层行以 ?sc unbound 存活，过滤形同虚设。"""
    if scope == "all":
        return ""
    if scope == "sample":
        return f'OPTIONAL {{ ?e <{_EIA_NS}attr/scope> ?sc }} FILTER(!BOUND(?sc) || ?sc = "{_DEFAULT_SCOPE}")'
    return f'?e <{_EIA_NS}attr/scope> "{scope}" .'


def _iris_in_scope(store, scope: str) -> set[str]:  # noqa: ANN001 - OxStore
    """归属库内的实体 IRI 集合（check_consistency 后置过滤用）。
    未打标按 sample 归属（与 _scope_filter_sparql 同一有效归属规则）；OPTIONAL 结果
    在 Python 侧判缺省，规避 SPARQL 组内 FILTER 的 LEFT JOIN 陷阱。"""
    if scope == "sample":
        rows = store.query(f"SELECT ?e ?sc WHERE {{ GRAPH <{_ASSERTED}> {{ ?e a ?cls . OPTIONAL {{ ?e <{_EIA_NS}attr/scope> ?sc }} }} }}")
        return {r["e"] for r in rows if (r.get("sc") or _DEFAULT_SCOPE) == scope}
    rows = store.query(f'SELECT ?e WHERE {{ GRAPH <{_ASSERTED}> {{ ?e <{_EIA_NS}attr/scope> "{scope}" }} }}')
    return {r["e"] for r in rows}


def _scopes_for(store, iris: list[str]) -> dict[str, str]:  # noqa: ANN001 - OxStore
    """一批实体 IRI → attrs.scope 原值（回填响应用；缺标不在此表，由调用方取缺省）。"""
    if not iris:
        return {}
    uniq = list(dict.fromkeys(iris))[:200]
    lst = ", ".join(f"<{i}>" for i in uniq)
    rows = store.query(f"SELECT ?e ?sc WHERE {{ GRAPH <{_ASSERTED}> {{ ?e <{_EIA_NS}attr/scope> ?sc . FILTER(?e IN ({lst})) }} }}")
    return {r["e"]: r["sc"] for r in rows if r.get("sc") is not None}


def _attrs_for(store, iris: list[str], chunk: int = 100) -> dict[str, dict]:  # noqa: ANN001 - OxStore
    """一批 IRI → attrs 投影（attr/* 三元组分块批量拉取，规避超长 IN 列表）。

    canonical_name/norm_name/scope/source_report 与业务属性同在此——JSONB attrs 在图内的
    唯一投影形态就是 attr/<key> 三元组（graph_ops.upsert_entity），批量一次拉回供响应组装。
    """
    out: dict[str, dict] = {}
    attr_ns_str = _EIA_NS + "attr/"
    uniq = list(dict.fromkeys(iris))
    for i in range(0, len(uniq), chunk):
        lst = ", ".join(f"<{u}>" for u in uniq[i : i + chunk])
        rows = store.query(f'SELECT ?e ?p ?o WHERE {{ GRAPH <{_ASSERTED}> {{ ?e ?p ?o . FILTER(?e IN ({lst}) && STRSTARTS(STR(?p), "{attr_ns_str}")) }} }}')
        for r in rows:
            out.setdefault(r["e"], {})[_local(r["p"], attr_ns_str)] = r["o"]
    return out


def _classes_for(store, iris: list[str], chunk: int = 100) -> dict[str, str]:  # noqa: ANN001 - OxStore
    """一批 IRI → rdf:type 类 IRI（对端 etype 回填用；断言图内实体恰一类，取首个）。"""
    out: dict[str, str] = {}
    uniq = list(dict.fromkeys(iris))
    for i in range(0, len(uniq), chunk):
        lst = ", ".join(f"<{u}>" for u in uniq[i : i + chunk])
        rows = store.query(f"SELECT ?e ?cls WHERE {{ GRAPH <{_ASSERTED}> {{ ?e a ?cls . FILTER(?e IN ({lst})) }} }}")
        for r in rows:
            out.setdefault(r["e"], r.get("cls") or "")
    return out


async def _query_entity(a: dict) -> list[TextContent]:
    name = (a.get("name") or "").strip()
    etype = (a.get("etype") or "").strip()
    if not name and not etype:
        return _err(ValueError("name 与 etype 至少给一个"))
    scope, bad = _validate_scope(a)
    if bad is not None:
        return bad
    limit = max(1, min(int(a.get("limit", 10)), 50))
    class_map = _etype_class_map_eia()
    type_filter = ""
    if etype:
        cls = class_map.get(etype)
        if cls is None:
            return _err(ValueError(f"未知 etype: {etype}（可用示例: {sorted(class_map)[:12]}…）"))
        type_filter = f"FILTER(?cls = <{cls}>)"
    name_filter = f"FILTER(CONTAINS(?name, {json.dumps(name, ensure_ascii=False)}))" if name else ""
    where = f"?e a ?cls ; <{_EIA_NS}attr/norm_name> ?name . {type_filter} {name_filter} {_scope_filter_sparql(scope)}".strip()
    rows = _kernel_store().query(f"SELECT DISTINCT ?e ?name ?cls WHERE {{ GRAPH <{_ASSERTED}> {{ {where} }} }} LIMIT {limit}")
    etype_of = _class_etype_map()
    store = _kernel_store()
    scope_of = _scopes_for(store, [r["e"] for r in rows])
    entities = []
    for r in rows:
        iri = r["e"]
        entities.append(
            {
                "iri": iri,
                "name": r.get("name"),
                "etype": etype_of.get(r.get("cls") or ""),
                "scope": scope_of.get(iri, _DEFAULT_SCOPE),
                "neighborhood": _neighborhood(store, iri),
            }
        )
    return _ok({"success": True, "count": len(entities), "scope": scope, "entities": entities})


async def _check_consistency(a: dict) -> list[TextContent]:
    """同 REST /rules/execute 全量执行，MCP 侧压缩为计数+样例（消息前 3 条/规则）。

    scope≠all 时按涉事节点后置过滤（§2）：规则先全量跑（SPARQL 不动），违规行只要
    任一 IRI 值绑定落在目标归属库即保留——违规关注的是该库节点本身，跨库边两侧任一
    在库即与本库出稿相关；无 IRI 绑定的行（按名分组规则如 rule_entity_naming）不可
    归属，任何视角都保留（fail-visible，过滤不静默隐藏无法归因的违规）。原始执行未
    截断时计数即精确数；原始已截断（>limit，如 sensitive_coverage 273>200）时过滤后
    计数只在截断集上成立，truncated 标记透传为 True 提示调用方。
    """
    from app.ontology.rules_executor import DEFAULT_VIOLATION_LIMIT, execute_rules

    scope, bad = _validate_scope(a)
    if bad is not None:
        return bad
    store = _kernel_store()
    out = execute_rules(store, limit=DEFAULT_VIOLATION_LIMIT)
    in_scope = _iris_in_scope(store, scope) if scope != "all" else None
    results = []
    for r in out["results"]:
        if in_scope is None:
            kept, count, truncated = r["violations"], r["violation_count"], r["truncated"]
        else:
            # 无 IRI 绑定的行不可归属任何库（如 rule_entity_naming 按归一名分组）→ 任何视角保留（fail-visible）
            kept = [v for v in r["violations"] if not (iris := _iri_bindings(v)) or any(i in in_scope for i in iris)]
            count, truncated = len(kept), r["truncated"]
        results.append({**r, "violations": kept, "violation_count": count, "truncated": truncated})
    by_severity: dict[str, int] = {}
    for r in results:
        by_severity[r["severity"]] = by_severity.get(r["severity"], 0) + r["violation_count"]
    return _ok(
        {
            "success": True,
            "executed_at": out["executed_at"],
            "scope": scope,
            "total_violations": sum(r["violation_count"] for r in results),
            "by_severity": by_severity,
            "results": [
                {"rule_id": r["rule_id"], "name": r["name"], "severity": r["severity"], "violation_count": r["violation_count"], "truncated": r["truncated"], "samples": [v["message"] for v in r["violations"][:3]]}
                for r in results
            ],
        }
    )


async def _get_writing_context(a: dict) -> list[TextContent]:
    entity_name = (a.get("entity_name") or "").strip()
    if not entity_name:
        return _err(ValueError("entity_name 必填"))
    store = _kernel_store()
    found = _resolve_entities(store, entity_name)
    if not found:
        return _ok({"success": False, "message": f"图中未找到实体「{entity_name}」"})
    iri = found[0]["e"]
    constraint_classes = [c for et, c in _etype_class_map_eia().items() if et in _CONSTRAINT_ETYPES]
    neighborhood = _neighborhood(store, iri, cap=30)
    nb_iris = [e["target"] for e in neighborhood["out"]] + [e["source"] for e in neighborhood["in"]]
    # 2 跳出边也纳入约束扫描（敏感点→措施→阈值：裁决数值常隔一层措施）
    hop2_iris: list[str] = []
    if nb_iris:
        pred_ns = _EIA_NS + "predicate/"
        lst = ", ".join(f"<{i}>" for i in list(dict.fromkeys(nb_iris))[:200])
        hop2_iris = [r["o"] for r in store.query(f"SELECT ?o WHERE {{ GRAPH <{_ASSERTED}> {{ ?n ?p ?o . FILTER(?n IN ({lst}) && STRSTARTS(STR(?p), \"{pred_ns}\")) }} }}") if r.get("o")][:100]
    all_iris = list(dict.fromkeys([iri, *nb_iris, *hop2_iris]))[:300]
    cls_rows = store.query("SELECT ?e ?cls WHERE { GRAPH <" + _ASSERTED + "> { ?e a ?cls . FILTER(?e IN (" + ", ".join(f"<{i}>" for i in all_iris) + ")) } }")
    cls_of = {r["e"]: r.get("cls") for r in cls_rows}
    etype_of = _class_etype_map()
    constraints = []
    for nb in dict.fromkeys(nb_iris + hop2_iris):
        if cls_of.get(nb) not in constraint_classes:
            continue
        attr_ns_str = _EIA_NS + "attr/"
        attr_rows = store.query(f'SELECT ?p ?o WHERE {{ GRAPH <{_ASSERTED}> {{ <{nb}> ?p ?o . FILTER(STRSTARTS(STR(?p), "{attr_ns_str}")) }} }}')
        attrs = {_local(r["p"], _EIA_NS + "attr/"): r["o"] for r in attr_rows}
        constraints.append({"iri": nb, "etype": etype_of.get(cls_of.get(nb) or ""), "attrs": attrs})
    names = _names_for(store, nb_iris)
    return _ok(
        {
            "success": True,
            "entity": {"iri": iri, "name": found[0].get("name"), "etype": etype_of.get(cls_of.get(iri) or "")},
            "aliases_considered": [r.get("name") for r in found[:5]],
            "neighborhood": neighborhood,
            "neighbor_names": names,
            "constraints": constraints,
            "hint": "写前核对 constraints 中的阈值/条款数值与邻域关系方向；跨章节同名实体先查 rule_entity_naming 违规。",
        }
    )


async def _get_rule_violations(a: dict) -> list[TextContent]:
    from app.ontology.rules_executor import execute_rules

    limit = max(1, min(int(a.get("limit", 50)), 1000))
    out = execute_rules(_kernel_store(), ids=[a["rule_id"]] if a.get("rule_id") else None, limit=limit)
    severity = a.get("severity")
    results = [r for r in out["results"] if r["violation_count"] > 0 and (not severity or r["severity"] == severity)]
    return _ok(
        {
            "success": True,
            "executed_at": out["executed_at"],
            "total_violations": out["total_violations"],
            "matching_violations": sum(r["violation_count"] for r in results),
            "results": results,
        }
    )


def _adjacency_peers(store, iri: str, cap: int = 20) -> dict[str, list[dict]]:  # noqa: ANN001 - OxStore
    """类比邻接边采集（只取谓词命名空间的出/入边；对端先留 IRI，调用方批量回填名/类/属性）。"""
    pred_ns = _EIA_NS + "predicate/"
    out_rows = [r for r in store.query(f"SELECT ?p ?o WHERE {{ GRAPH <{_ASSERTED}> {{ <{iri}> ?p ?o }} }}") if isinstance(r.get("p"), str) and r["p"].startswith(pred_ns)][:cap]
    in_rows = [r for r in store.query(f"SELECT ?s ?p WHERE {{ GRAPH <{_ASSERTED}> {{ ?s ?p <{iri}> }} }}") if isinstance(r.get("p"), str) and r["p"].startswith(pred_ns)][:cap]
    return {"out": [{"predicate": _local(r["p"], pred_ns), "peer": r["o"]} for r in out_rows], "in": [{"predicate": _local(r["p"], pred_ns), "peer": r["s"]} for r in in_rows]}


# 身份/归属属性单列（不混入业务 attrs——label/scope/source_report/source_reports 已在响应顶层）
_IDENTITY_ATTRS = ("canonical_name", "norm_name", "scope", "source_report", "source_reports")


async def _query_analogy(a: dict) -> list[TextContent]:
    """类比素材（A 库 sample）+ 领域规律（B 库 domain_common）查询——类比合规通道。

    子项目 4 spec §4 恒定 scope=sample；子项目 5 扩入 B 库 domain_common（etype=domain_pattern
    蒸馏规律条目可被 etype/名称过滤查到）——类比通道的消费语义就是「写作取材」，样例与领域
    规律同属取材面，C 库 project 工作本仍排除（走 query_entity scope=project）。
    出参每条必带 source_report（attrs.source_report；B 库 pattern 条目回退 attrs.source_reports
    「、」串；缺标 fallback "unknown"）——类比值溯源到"哪份报告"。邻接边给谓词+对端名+对端属性：
    裁决数值的载体在对端 attrs（阈值/措施规格），关系 attrs 不入图（loader 不装载 dg_relations.attrs）。
    未打标行按 sample 归属（与 _scope_filter_sparql 同一缺省规则，kernel 重载前后语义连续）。
    """
    etype = (a.get("etype") or "").strip()
    label = (a.get("label_contains") or "").strip()
    if not etype and not label:
        return _err(ValueError("etype 与 label_contains 至少给一个"))
    limit = max(1, min(int(a.get("limit", 10)), 50))
    class_map = _etype_class_map_eia()
    type_filter = ""
    if etype:
        cls = class_map.get(etype)
        if cls is None:
            return _err(ValueError(f"未知 etype: {etype}（可用示例: {sorted(class_map)[:12]}…）"))
        type_filter = f"FILTER(?cls = <{cls}>)"
    label_filter = f"FILTER(CONTAINS(?name, {json.dumps(label, ensure_ascii=False)}))" if label else ""
    # A+B 双库：未打标按 sample 缺省 + domain_common 精确命中（FILTER 在 OPTIONAL 组外，见 _scope_filter_sparql 注）
    scope_clause = f'OPTIONAL {{ ?e <{_EIA_NS}attr/scope> ?sc }} FILTER(!BOUND(?sc) || ?sc = "{_DEFAULT_SCOPE}" || ?sc = "domain_common")'
    where = f"?e a ?cls ; <{_EIA_NS}attr/norm_name> ?name . {type_filter} {label_filter} {scope_clause}".strip()
    store = _kernel_store()
    rows = store.query(f"SELECT DISTINCT ?e ?name ?cls WHERE {{ GRAPH <{_ASSERTED}> {{ {where} }} }} LIMIT {limit}")
    etype_of = _class_etype_map()
    adj_of = {r["e"]: _adjacency_peers(store, r["e"]) for r in rows}
    peers = [e["peer"] for adj in adj_of.values() for e in adj["out"] + adj["in"]]
    attrs_of = _attrs_for(store, [r["e"] for r in rows] + peers)
    cls_of = _classes_for(store, peers)

    def edge(e: dict) -> dict:
        peer_attrs = attrs_of.get(e["peer"], {})
        return {
            "predicate": e["predicate"],
            "peer": e["peer"],
            "peer_name": peer_attrs.get("canonical_name") or peer_attrs.get("norm_name"),
            "peer_etype": etype_of.get(cls_of.get(e["peer"]) or ""),
            "peer_attrs": {k: v for k, v in peer_attrs.items() if k not in _IDENTITY_ATTRS},
        }

    entities = []
    for r in rows:
        iri = r["e"]
        attrs = attrs_of.get(iri, {})
        entities.append(
            {
                "iri": iri,
                "label": attrs.get("canonical_name") or r.get("name"),
                "norm_name": r.get("name"),
                "etype": etype_of.get(r.get("cls") or ""),
                "scope": attrs.get("scope") or _DEFAULT_SCOPE,
                "source_report": attrs.get("source_report") or attrs.get("source_reports") or "unknown",
                "attrs": {k: v for k, v in attrs.items() if k not in _IDENTITY_ATTRS},
                "adjacency": {"out": [edge(e) for e in adj_of[iri]["out"]], "in": [edge(e) for e in adj_of[iri]["in"]]},
            }
        )
    return _ok(
        {
            "success": True,
            "count": len(entities),
            "scope": "sample+domain_common",
            "entities": entities,
            "hint": "类比值仅作类比参考：引用须在 stage JSON 标注 param_source=analog_mine + 来源报告名（source_report）；未经本通道的样例实体禁入。domain_pattern 条目引用时标注规律条目 pattern_id 与 support_count。",
        }
    )


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
        "query_entity": _query_entity,
        "check_consistency": _check_consistency,
        "get_writing_context": _get_writing_context,
        "get_rule_violations": _get_rule_violations,
        "query_analogy": _query_analogy,
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
