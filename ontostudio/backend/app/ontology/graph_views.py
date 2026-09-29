"""Ontology 语义地图图投影 — 全部 enabled 对象/链接统一为 Semantica Explorer 方言的 nodes/edges.

EAI-CUSTOM(2026-09-12, plan Task1): 设计 docs/superpowers/specs/2026-09-12-ontology-semantic-map-ui-design.md §4，
计划 docs/superpowers/plans/2026-09-12-ontology-semantic-map-ui.md Step 1.3/1.4（内部实现为重写版，契约见测试）。

方言与契约:
- 游标 = base64(urlsafe, 严格校验) JSON {"type_idx", "offset"}；type_idx 为 api_name 升序排序后的
  对象类型（或链接类型）序号，offset 为该类型内已发出的行数。损坏/越界游标: decode 返回 None（按从头开始）。
- 节点 = {"id", "type", "label", "properties"}；id = "<api_name>:<pk>"，label = 首个非空 searchable
  属性值，回退 pk 值。properties 直接透出 engine 序列化行（hidden 列已在引擎层剔除）。
- 边 = {"source", "target", "type", "label"}；stub（enabled:false）链接不产生边。
- 排水: 逐类型翻页取尽后原地前进，同一响应内跨类型衔接；末页 next_cursor=None。

实现要点（对计划草稿的重写，理由见各函数 docstring）:
- nodes 经 engine.list_objects（keyset 游标、单次 ≤200 行钳制）；对外 offset 游标以「keyset 行走跳过」实现——
  精确不漏，代价是续页时重扫已发行（数据量 ≤ 万级，可接受）。
- edges 的配对: engine._follow/_follow_same_connector 的 SELECT 仅投影远侧列、不含近侧 pk，
  批量调用无法配对 → 同 connector 链接自建单条「两侧 pk」只读 JOIN（仍经 engine._resolver.fetch，
  保留 assert_readonly_select 单一真源与断连显式抛错），JOIN/GUARD/归一化语义逐条对齐 engine.py:253-286；
  跨 connector 链接回退逐源实例 engine.get_links（调用域即配对域；当前注册表无此类 enabled 链接，仅预留）。
"""

from __future__ import annotations

import base64
import json
from typing import Any

# 跨 connector 回退路径的逐实例 fan-out 上限（engine.get_links 内部同样受 MAX_LIMIT=200 钳制）
# TODO(语义地图v2): fan-out>=200 时按 traverse CHUNK 惯例 raise，防静默丢边
_CROSS_FANOUT = 200
# 跨 connector 回退路径枚举源实例的 keyset 步长（engine.list_objects 单次 ≤200 行钳制）
_CROSS_SOURCE_PAGE = 200
# 对外游标 offset 上限: 防敌意游标触发无界 SQL OFFSET 行走（edges 每链接一次全表 OFFSET 扫描）
_MAX_OFFSET = 10_000_000
# EAI-CUSTOM(2026-09-29): mention 溯源类型不进本体浏览窗口。mention（label=uuid 的证据行，
# 经 DetailPanel 懒加载查看）批量入图后行数远超实体行——默认投影会把实体/关系节点挤出
# limit 窗口（实测 dg_mentions 5050 行灌满 /graph/nodes?limit=500，画布成"提及点汤"）。
# nodes/edges 默认同规则排除（节点不在场则边成孤端）；include=mentions opt-in 恢复全集。
_MENTION_TYPES: frozenset[str] = frozenset({"graph_mention"})


# ---------- 游标编解码（nodes/edges 共用; type_idx 语义由调用方解释） ----------


def encode_cursor(type_idx: int, offset: int) -> str:
    """{"type_idx", "offset"} → urlsafe base64 字符串。"""
    return base64.urlsafe_b64encode(json.dumps({"type_idx": type_idx, "offset": offset}).encode()).decode()


def decode_cursor(cursor: str | None) -> dict[str, int] | None:
    """游标 → {"type_idx", "offset"}；None/空 → 从头开始；损坏/形状非法/负值/offset 超上限 → None（fail 明示，不猜）。"""
    if not cursor:
        return {"type_idx": 0, "offset": 0}
    try:
        raw = base64.b64decode(cursor, altchars=b"-_", validate=True)
        d = json.loads(raw)
        if not isinstance(d, dict):
            return None
        type_idx, offset = int(d["type_idx"]), int(d["offset"])
        if type_idx < 0 or offset < 0 or offset > _MAX_OFFSET:  # 巨型 offset = 敌意游标，按垃圾处理
            return None
        return {"type_idx": type_idx, "offset": offset}
    except Exception:
        return None


# ---------- 节点投影 ----------


def projection_order(reg: Any) -> tuple[list[Any], set[str]]:
    """启用对象类型投影序 + 让位透镜集合（EAI-CUSTOM 2026-09-27 双透镜去重）。

    同一物理表被多个对象类型投影时（全域透镜 graph_entity 与域过滤透镜 eia_entity/eia_relation
    共享 dg_entities/dg_relations），图面只保留一个节点/行——否则同一实体渲染为两个节点、边翻倍。
    保留优先级（信号强→弱）：
    1. **被链接类型引用次数**（多者胜：graph_relation 被 relation_subject/object + mention 链引用，
       结构地位高于只被 1 条 mention 链指向的 eia_relation）；
    2. **动作宿主**（review_entity 的 target graph_entity）；
    3. api_name 字母序兜底。
    让位透镜仍可经 /objects REST 域过滤使用，只是不进图。
    """
    link_ref_count: dict[str, int] = {}
    for lt in reg.link_types.values():
        for name in (lt.source, lt.target):
            link_ref_count[name] = link_ref_count.get(name, 0) + 1
    action_hosts: set[str] = set()
    for spec in (getattr(reg, "actions", None) or {}).values():
        action_hosts.add(spec.target)
    ordered = sorted(
        (o for o in reg.object_types.values() if o.enabled),
        key=lambda o: (
            -link_ref_count.get(o.api_name, 0),
            o.api_name not in action_hosts,
            o.api_name,
        ),
    )
    lens: set[str] = set()
    seen_tables: set[str] = set()
    kept: list[Any] = []
    for o in ordered:
        table = str(getattr(getattr(o, "access", None), "table", o.api_name))
        if table in seen_tables:
            lens.add(o.api_name)
            continue
        seen_tables.add(table)
        kept.append(o)
    return kept, lens


def searchable_api_names(obj: Any) -> list[str]:
    """对象类型的 searchable 属性 api_name 列表（label 候选，按声明序）。"""
    props = obj.visible_properties() if hasattr(obj, "visible_properties") else obj.properties
    return [p.api_name for p in props if getattr(p, "searchable", False)]


def domain_property(obj: Any) -> Any | None:
    """对象类型声明的 filterable ``domain`` 属性（EAI-CUSTOM 2026-09-29 图谱投影域过滤）。

    没有则返回 None——该类型的物理表无域列（dg_relations/dg_mentions），**不参与域裁剪**：
    域过滤语义是「实体类型行按 domain 列过滤」（任务口径），关系/证据行无域可裁，作为
    脚手架保持原样（与前端既有透明化行为一致：空域属性节点在域过滤下保持可见）。
    """
    props = obj.visible_properties() if hasattr(obj, "visible_properties") else obj.properties
    for p in props:
        if getattr(p, "name", "") == "domain" and getattr(p, "filterable", False):
            return p
    return None


def _domain_filter(obj: Any, domain: str | None) -> list[dict[str, Any]] | None:
    """域过滤激活时该类型的引擎行过滤片段（``[{column, op, value}]``）；不参与域裁剪 → None。"""
    if not domain:
        return None
    prop = domain_property(obj)
    if prop is None:
        return None
    return [{"column": getattr(prop, "api_name", "") or prop.name, "op": "eq", "value": domain}]


def project_node(obj: Any, row: dict[str, Any], searchable: list[str]) -> dict[str, Any]:
    """engine 序列化行 → Explorer 节点。label 取首个非空 searchable 值，回退 pk 值。"""
    pk_val = row.get(obj.pk.api_name)
    label = next((row[a] for a in searchable if row.get(a) not in (None, "")), str(pk_val))
    return {"id": f"{obj.api_name}:{pk_val}", "type": obj.api_name, "label": str(label), "properties": row}


async def nodes_page(reg: Any, engine: Any, cursor: str | None, limit: int, include_mentions: bool = False, domain: str | None = None) -> dict[str, Any]:
    """全部 enabled 对象类型实例统一投影（逐类型排水，跨类型同页衔接）。

    排水实现: 对外 offset 游标通过「每次响应从类型头重取 + keyset 行走跳过 offset 行」落地——
    引擎 keyset 游标是类型内方言且无法跳行，这样换取精确不重不漏；每个响应至多重扫已发行一次。

    EAI-CUSTOM(2026-09-29): _MENTION_TYPES 类型默认不投影（实体/关系窗口优先）；include_mentions=True 恢复全集。
    EAI-CUSTOM(2026-09-29 图谱投影域过滤): domain 非 None 时，声明了 filterable domain 属性的
    类型经引擎行过滤（filters 走与 /objects 同一条引擎路径，filterable 校验在引擎侧）；
    无域列的类型（关系/证据）不裁剪。缺省（None）行为逐字节不变。
    """
    pos = decode_cursor(cursor)
    if pos is None:
        pos = {"type_idx": 0, "offset": 0}
    ordered, _lens = projection_order(reg)
    if not include_mentions:
        ordered = [o for o in ordered if o.api_name not in _MENTION_TYPES]
    out: list[dict[str, Any]] = []
    type_idx, offset = pos["type_idx"], pos["offset"]
    while type_idx < len(ordered) and len(out) < limit:
        obj = ordered[type_idx]
        searchable = searchable_api_names(obj)
        filters = _domain_filter(obj, domain)
        keyset: str | None = None  # 类型内 engine keyset 游标（引擎方言，与对外游标无关）
        skip = offset  # 本类型已发出的行数 → 本次重取时跳过（跳过行不计入本次 offset）
        exhausted = False
        while len(out) < limit and not exhausted:
            page = await engine.list_objects(obj.api_name, filters=filters, limit=limit - len(out) + skip, cursor=keyset)
            rows = page["data"]
            if skip:
                skipped = min(skip, len(rows))
                rows = rows[skipped:]
                skip -= skipped
            take = rows[: limit - len(out)]
            out.extend(project_node(obj, r, searchable) for r in take)
            offset += len(take)
            keyset = page.get("next_cursor")
            if not keyset or not page["data"]:
                exhausted = True  # next_cursor 为空 ⟺ 类型取尽（引擎契约: has_more 必有数据）
        if exhausted:
            type_idx += 1
            offset = 0
    return {"nodes": out, "next_cursor": encode_cursor(type_idx, offset) if type_idx < len(ordered) else None}


# ---------- 边投影 ----------


async def edges_page(reg: Any, engine: Any, cursor: str | None, limit: int, include_mentions: bool = False, domain: str | None = None) -> dict[str, Any]:
    """全部 enabled 链接实例投影（逐链接排水；stub 不进入迭代，天然不产生边）。

    游标复用同款编解码，type_idx 表链接序号、offset 表该链接内已发出的边数。每次对当前链接
    以 LIMIT capacity+1 OFFSET offset 探测：有富余 → 停留本链接并推进 offset；无富余 → 取尽并前进。
    SQL 固定 ORDER BY 两侧 pk，保证 OFFSET 切片跨响应稳定。

    EAI-CUSTOM(2026-09-29 图谱投影域过滤): domain 非 None 时，链接两端声明了 filterable
    domain 属性的一侧加 ``表.domain = :gd`` 行域守卫（如 relation_subject 的实体端
    dg_entities 有域列、关系端 dg_relations 无域列则只守实体端）——与节点侧"有域列才裁剪"
    同一语义。缺省（None）行为逐字节不变。
    """
    pos = decode_cursor(cursor)
    if pos is None:
        pos = {"type_idx": 0, "offset": 0}
    # EAI-CUSTOM(2026-09-27 双透镜去重): 指向让位透镜的链接不产生边（同一 FK 的域透镜
    # 版本）；同 FK 签名的链接只保留 api_name 序首个——边与节点同规则去重。
    # EAI-CUSTOM(2026-09-29): 与 nodes 同规则排除 mention 链接——mention 节点默认不在场，
    # 保留 mention 边会成孤端；include_mentions=True 与节点同步恢复全集。
    _, lens = projection_order(reg)
    mentions = frozenset() if include_mentions else _MENTION_TYPES
    ordered_raw = sorted(
        (lt for lt in reg.link_types.values() if lt.enabled and lt.source not in lens and lt.target not in lens and lt.source not in mentions and lt.target not in mentions),
        key=lambda lt: lt.api_name,
    )
    ordered: list[Any] = []
    seen_sig: set[tuple[str, str, str, str, str]] = set()
    for lt in ordered_raw:
        src_obj = reg.object_types[lt.source]
        tgt_obj = reg.object_types[lt.target]
        sig = (
            str(getattr(getattr(src_obj, "access", None), "table", lt.source)),
            str(getattr(lt.join, "source_column", "") or ""),
            str(getattr(getattr(tgt_obj, "access", None), "table", lt.target)),
            str(getattr(lt.join, "target_column", "") or ""),
            str(lt.join.type),
        )
        if sig in seen_sig:
            continue
        seen_sig.add(sig)
        ordered.append(lt)
    out: list[dict[str, Any]] = []
    link_idx, offset = pos["type_idx"], pos["offset"]
    while link_idx < len(ordered) and len(out) < limit:
        lt = ordered[link_idx]
        capacity = limit - len(out)
        rows = await _link_rows(reg, engine, lt, capacity + 1, offset, domain=domain)
        take = rows[:capacity]
        out.extend(_project_edge(lt, r) for r in take)
        if len(rows) <= len(take):
            link_idx += 1  # 探针无富余: 本链接取尽
            offset = 0
        else:
            offset += len(take)
    return {"edges": out, "next_cursor": encode_cursor(link_idx, offset) if link_idx < len(ordered) else None}


def _project_edge(lt: Any, row: dict[str, Any]) -> dict[str, Any]:
    """配对行（__src_pk/__tgt_pk）→ Explorer 边。"""
    return {"source": f"{lt.source}:{row.get('__src_pk')}", "target": f"{lt.target}:{row.get('__tgt_pk')}", "type": lt.api_name, "label": lt.display_name}


async def _link_rows(reg: Any, engine: Any, lt: Any, capacity: int, offset: int, domain: str | None = None) -> list[dict[str, Any]]:
    """单个链接类型的配对行（同时含两侧 pk，键 __src_pk/__tgt_pk）。capacity 含 +1 探针余量。"""
    src_obj = reg.object_types[lt.source]
    tgt_obj = reg.object_types[lt.target]
    if engine._resolver.same(src_obj.access, tgt_obj.access):
        return await _same_connector_link_rows(engine, lt, src_obj, tgt_obj, capacity, offset, domain=domain)
    return await _cross_connector_link_rows(reg, engine, lt, src_obj, tgt_obj, capacity, offset, domain=domain)


async def _same_connector_link_rows(engine: Any, lt: Any, src_obj: Any, tgt_obj: Any, capacity: int, offset: int, domain: str | None = None) -> list[dict[str, Any]]:
    """同 connector: 单条只读 JOIN 同时取两侧 pk。

    计划草稿经 engine.get_links 批量 pks 不可行——_follow_same_connector 的 SELECT 只投影远侧列
    （engine.py:256-257），近侧 pk 不在结果中，行无法归属到源实例。此处自建 SQL，
    join 条件/归一化/守卫/source_filter 逐条对齐 engine.py:262-286 的语义，仍经
    engine._resolver.fetch 执行（assert_readonly_select 安全单一真源 + 断连显式抛错）。

    EAI-CUSTOM(2026-09-29 图谱投影域过滤): domain 激活时，声明了 filterable domain 属性的
    一端加 ``端别名."域列" = :gd_*`` 守卫（物理列名 = 属性 name，与引擎 filters 同列）；
    无域列的一端不守卫——与节点侧"有域列才裁剪、无域列保持脚手架"同一语义。
    gd_src/gd_tgt 命名空间独立，与 source_filter 的 sf_* 键绝无冲突。
    """
    j = lt.join
    params: dict[str, Any] = {}
    select = f'SELECT s."{src_obj.pk.column}" AS "__src_pk", t."{tgt_obj.pk.column}" AS "__tgt_pk"'
    sf = ""
    if j.source_filter:
        sf = " AND " + " AND ".join(f's."{k}" = :sf_{k}' for k in j.source_filter)
        params.update({f"sf_{k}": v for k, v in j.source_filter.items()})
    domain_guards: list[str] = []
    if domain:
        src_dom = domain_property(src_obj)
        if src_dom is not None:
            domain_guards.append(f's."{src_dom.name}" = :gd_src')
            params["gd_src"] = domain
        tgt_dom = domain_property(tgt_obj)
        if tgt_dom is not None:
            domain_guards.append(f't."{tgt_dom.name}" = :gd_tgt')
            params["gd_tgt"] = domain
    if j.type == "foreign_key":
        sql = f'{select} FROM "{_table(tgt_obj)}" t JOIN "{_table(src_obj)}" s ON t."{j.target_column}" = s."{j.source_column}"{sf}'
        if domain_guards:
            sql += " WHERE " + " AND ".join(domain_guards)
    else:
        # normalized_key_match: any-of key_pairs，引擎级归一化 + 两侧非空守卫（与引擎一致，不做 per-link 表达式）
        pairs = j.key_pairs or []
        conds = " OR ".join(f"{_norm(f's."{sc}"')} = {_norm(f't."{tc}"')}" for sc, tc in pairs)
        guards = " AND ".join([_empty_guard(f's."{sc}"') for sc, _ in pairs] + [_empty_guard(f't."{tc}"') for _, tc in pairs] + domain_guards)
        sql = f'{select} FROM "{_table(tgt_obj)}" t JOIN "{_table(src_obj)}" s ON ({conds}) WHERE {guards}{sf}'
    sql += f" ORDER BY 1, 2 LIMIT {max(0, capacity)} OFFSET {max(0, offset)}"
    return await engine._resolver.fetch(src_obj.access, sql, params)


async def _cross_connector_link_rows(reg: Any, engine: Any, lt: Any, src_obj: Any, tgt_obj: Any, capacity: int, offset: int, domain: str | None = None) -> list[dict[str, Any]]:
    """跨 connector 回退: 逐源实例 engine.get_links（单 pk 调用域即配对域，配对天然正确）。

    返回契约与同 connector SQL 路径一致: post-offset 行（前 offset 条跳过不返回），
    至多 capacity 条——edges_page 据此切片并判尽，两条路径可互换。
    注意: 每次响应从源类型头重扫，O(源实例数) 次查询——当前注册表所有 enabled 链接均为同 connector
    （cross_module 链接全部 enabled:false stub，进不到这里），此路径仅为未来启用预留，正确性优先。

    EAI-CUSTOM(2026-09-29 图谱投影域过滤): 域过滤激活时本路径**整链接不产出边**（fail-closed
    到空而非半过滤）——engine.get_links 无 filters 接缝，行级域裁剪在此不可表达；当前注册表
    无 enabled 跨 connector 链接，分支今日不可达，先钉住语义防未来启用时静默漏过滤。
    """
    if domain:
        return []
    if not src_obj.enabled:  # 源类型停用时 list_objects 会显式拒绝 → 直接不产出该链接的边（节点层同样不可见）
        return []
    target = offset + capacity  # 需物化的边数上界 = 已发出的 offset 条 + 本次 capacity+1 探针的量
    out: list[dict[str, Any]] = []
    keyset: str | None = None
    while len(out) < target:
        page = await engine.list_objects(lt.source, limit=_CROSS_SOURCE_PAGE, cursor=keyset)
        rows = page["data"]
        if not rows:
            break
        pk_name = src_obj.pk.api_name
        for row in rows:
            links = await engine.get_links(lt.source, row[pk_name], lt.api_name, limit=_CROSS_FANOUT)
            for far in links["data"]:
                out.append({"__src_pk": row[pk_name], "__tgt_pk": far.get(tgt_obj.pk.api_name)})
                if len(out) >= target:
                    return out[offset:]  # bug-3316: 必须 post-offset 返回，否则翻页永远重发头部边
        keyset = page.get("next_cursor")
        if not keyset:
            break
    return out[offset:]


# ---------- SQL 拼接小工具（与引擎同级语义的本地副本，避免触引擎私有方法） ----------


def _table(obj: Any) -> str:
    """物理表名（受信注册表 YAML；引擎 _table 同款）。"""
    return obj.access.table or obj.access.table_name or ""


def _norm(col: str) -> str:
    """引擎级归一化标准（engine._norm 同款）: LOWER(BTRIM(col))。"""
    return f"LOWER(BTRIM({col}))"


def _empty_guard(col: str) -> str:
    """两侧非空守卫（engine._empty_guard 同款）。"""
    return f"{_norm(col)} IS NOT NULL AND {_norm(col)} <> ''"
