"""graph_views 投影纯逻辑测试（游标编解码/节点标签选择/边投影形状）——无 DB.

EAI-CUSTOM(2026-09-12, plan Task1): docs/superpowers/plans/2026-09-12-ontology-semantic-map-ui.md Step 1.1/1.5。
前 5 例为计划原文测试；其后为本实现的排水/翻页/stub 排除契约测试（mock engine 形状对齐 engine.list_objects 真实签名）。
"""

import base64
import json
import re
from collections import Counter
from types import SimpleNamespace

import pytest

from app.ontology import graph_views
from app.ontology.schemas import (
    AccessConfig,
    JoinConfig,
    LinkType,
    ObjectType,
    PKConfig,
    PropertySchema,
)


def _enc(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode()


def test_cursor_roundtrip():
    cur = graph_views.encode_cursor(2, 50)
    assert graph_views.decode_cursor(cur) == {"type_idx": 2, "offset": 50}


def test_cursor_none():
    assert graph_views.decode_cursor(None) == {"type_idx": 0, "offset": 0}


def test_cursor_garbage_returns_none():
    assert graph_views.decode_cursor("???not-base64-json") is None


def test_node_projection_shape():
    obj = type("O", (), {"api_name": "bid", "display_name": "投标记录", "pk": type("P", (), {"api_name": "bidId"})()})()
    row = {"bidId": "B-1", "projectName": "横城煤矿项目", "won": True}
    searchable = ["projectName"]
    node = graph_views.project_node(obj, row, searchable)
    assert node["id"] == "bid:B-1"
    assert node["type"] == "bid"
    assert node["label"] == "横城煤矿项目"  # 首个 searchable 列的值
    assert node["properties"]["won"] is True


def test_node_label_fallback_to_pk():
    obj = type("O", (), {"api_name": "bid", "display_name": "投标记录", "pk": type("P", (), {"api_name": "bidId"})()})()
    node = graph_views.project_node(obj, {"bidId": "B-9"}, [])
    assert node["label"] == "B-9"


# ---------- 契约测试: nodes_page / edges_page 排水/翻页/stub 排除 ----------


class FakeEngine:
    """nodes 用: 对齐 engine.list_objects 真实签名与 {"data","next_cursor","object_type"} 返回形状（engine.py:88-136）。

    EAI-CUSTOM(2026-09-29 图谱投影域过滤): filter_calls 逐调用记录 (object_type, filters)，
    供域过滤契约断言（None = 未传过滤，即缺省行为不变）。
    """

    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables
        self.calls: list[tuple[str, int, str | None]] = []
        self.filter_calls: list[tuple[str, list[dict[str, object]] | None]] = []

    async def list_objects(self, object_type, filters=None, q=None, limit=50, cursor=None, order=None, desc=False):
        self.calls.append((object_type, limit, cursor))
        self.filter_calls.append((object_type, filters))
        rows = self.tables[object_type]
        start = int(cursor) if cursor else 0
        data = rows[start : start + limit]
        return {"data": data, "next_cursor": str(start + limit) if start + limit < len(rows) else None, "object_type": object_type}


class FakeResolver:
    """edges 用: engine._resolver 协议替身（same 恒 True；fetch 按 FROM 表名路由罐头行并解析 LIMIT/OFFSET）。"""

    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables
        self.calls: list[str] = []

    async def fetch(self, access, sql, params=None):
        self.calls.append(sql)
        table = re.search(r'FROM "([^"]+)"', sql).group(1)
        rows = self.tables.get(table, [{"__src_pk": "S1", "__tgt_pk": "T1"}])
        m = re.search(r"LIMIT (\d+) OFFSET (\d+)$", sql)
        n, off = (int(m.group(1)), int(m.group(2))) if m else (len(rows), 0)
        return rows[off : off + n]

    def same(self, a, b):
        return True


def _drain_obj(api_name: str) -> SimpleNamespace:
    """鸭子类型 ObjectType：nodes_page/project_node 只触 api_name/enabled/pk.api_name/properties。"""
    props = [
        type("Pr", (), {"api_name": "id", "searchable": False, "hidden": False})(),
        type("Pr", (), {"api_name": "name", "searchable": True, "hidden": False})(),
    ]
    return type("O", (), {"api_name": api_name, "display_name": api_name, "enabled": True, "pk": type("PK", (), {"api_name": "id"})(), "properties": props})()


def _edge_obj(api_name: str, table: str, pk_col: str, with_domain: bool = False) -> ObjectType:
    """真 pydantic ObjectType（edges SQL 构建走真实 schema 形状）。

    EAI-CUSTOM(2026-09-29 图谱投影域过滤): with_domain=True 追加 filterable 的 domain 属性
    （仿真 doc_graph.yaml 的 graph_entity 声明形状）；False = 无域列类型（dg_relations 同款）。
    """
    props = [PropertySchema(name=pk_col, api_name=pk_col, type="string")]
    if with_domain:
        props.append(PropertySchema(name="domain", api_name="domain", type="string", filterable=True))
    return ObjectType(
        api_name=api_name,
        display_name=api_name,
        description="契约测试",
        domain="test",
        access=AccessConfig(path="postgres_ext", table=table),
        pk=PKConfig(column=pk_col, api_name=pk_col, type="string"),
        properties=props,
    )


def _edge_link(api_name: str, source: str, target: str, **join_kw) -> LinkType:
    return LinkType(api_name=api_name, display_name=api_name, source=source, target=target, cardinality="N:1", reverse=api_name + "_rev", join=JoinConfig(**join_kw))


@pytest.mark.asyncio
async def test_nodes_page_idempotent_same_cursor():
    reg = SimpleNamespace(object_types={"aa": _drain_obj("aa"), "bb": _drain_obj("bb")}, link_types={})
    rows = {"aa": [{"id": f"a{i}", "name": f"A{i}"} for i in range(3)], "bb": [{"id": f"b{i}", "name": f"B{i}"} for i in range(3)]}
    p1 = await graph_views.nodes_page(reg, FakeEngine(rows), None, 2)
    p2 = await graph_views.nodes_page(reg, FakeEngine(rows), None, 2)
    assert p1 == p2


@pytest.mark.asyncio
async def test_nodes_page_drains_across_types_no_gap_no_dup():
    """两个 mock 类型各 3 行、limit=2 → 3 页取尽 6 行：无重复无遗漏、末页 next_cursor=None。"""
    reg = SimpleNamespace(object_types={"aa": _drain_obj("aa"), "bb": _drain_obj("bb")}, link_types={})
    eng = FakeEngine({"aa": [{"id": f"a{i}", "name": f"A{i}"} for i in range(3)], "bb": [{"id": f"b{i}", "name": f"B{i}"} for i in range(3)]})
    seen: list[str] = []
    cursor, pages = None, 0
    while True:
        page = await graph_views.nodes_page(reg, eng, cursor, 2)
        seen.extend(n["id"] for n in page["nodes"])
        pages += 1
        assert pages < 10  # 防失控
        if page["next_cursor"] is None:
            break
        cursor = page["next_cursor"]
    assert pages == 3
    assert len(seen) == len(set(seen)) == 6  # 集合断言: 不重不漏
    assert set(seen) == {"aa:a0", "aa:a1", "aa:a2", "bb:b0", "bb:b1", "bb:b2"}


@pytest.mark.asyncio
async def test_nodes_page_exhausted_and_garbage_cursor_fresh_start():
    reg = SimpleNamespace(object_types={"aa": _drain_obj("aa")}, link_types={})
    eng = FakeEngine({"aa": [{"id": "a0", "name": "A0"}]})
    page = await graph_views.nodes_page(reg, eng, None, 10)
    assert page == {"nodes": [{"id": "aa:a0", "type": "aa", "label": "A0", "properties": {"id": "a0", "name": "A0"}}], "next_cursor": None}
    # 类型序号越界 → 空页且 next_cursor=None；损坏游标 → 按从头开始处理（与 fresh 结果一致）
    assert await graph_views.nodes_page(reg, eng, graph_views.encode_cursor(9, 0), 2) == {"nodes": [], "next_cursor": None}
    assert await graph_views.nodes_page(reg, eng, "???junk", 2) == await graph_views.nodes_page(reg, eng, None, 2)


def _edges_reg_fk_only():
    # EAI-CUSTOM(2026-09-27): lb 改异签名（sa→sc）——同签名链接会被 2026-09-27 去重让位
    # （见 graph_views.edges_page），机制测试需要两条都参与排水的链接。
    reg = SimpleNamespace(
        object_types={
            "sa": _edge_obj("sa", "ta", "sid"),
            "sb": _edge_obj("sb", "tb", "pid"),
            "sc": _edge_obj("sc", "tc", "qid"),
        },
        link_types={
            "la": _edge_link("la", "sa", "sb", type="foreign_key", source_column="sid", target_column="pid"),
            "lb": _edge_link("lb", "sa", "sc", type="foreign_key", source_column="sid", target_column="qid"),
        },
    )
    resolver = FakeResolver(
        {
            "tb": [{"__src_pk": f"s{i}", "__tgt_pk": f"p{i}"} for i in range(3)],
            "tc": [{"__src_pk": f"s{i}", "__tgt_pk": f"q{i}"} for i in range(3)],
        }
    )  # FK SQL 的 FROM 表 = target 表
    return reg, SimpleNamespace(_resolver=resolver), resolver


@pytest.mark.asyncio
async def test_edges_page_drains_across_links_no_gap_no_dup():
    reg, eng, resolver = _edges_reg_fk_only()
    seen: list[tuple[str, str, str]] = []
    cursor, pages = None, 0
    while True:
        page = await graph_views.edges_page(reg, eng, cursor, 2)
        seen.extend((e["type"], e["source"], e["target"]) for e in page["edges"])
        pages += 1
        assert pages < 10
        if page["next_cursor"] is None:
            break
        cursor = page["next_cursor"]
    assert pages == 3
    assert len(seen) == len(set(seen)) == 6  # 集合断言: 不重不漏
    assert Counter(t for t, _, _ in seen) == {"la": 3, "lb": 3}  # 两链接各取尽 3 条
    assert all(re.search(r"LIMIT \d+ OFFSET \d+$", sql) for sql in resolver.calls)  # SQL 固定带 LIMIT/OFFSET 分页尾巴


@pytest.mark.asyncio
async def test_edges_page_normalized_join_and_shape():
    reg = SimpleNamespace(
        object_types={"sn": _edge_obj("sn", "tn", "mid"), "tn2": _edge_obj("tn2", "tt", "cid")},
        link_types={"ln": _edge_link("ln", "sn", "tn2", type="normalized_key_match", key_pairs=[["code", "code"]])},
    )
    eng = SimpleNamespace(_resolver=FakeResolver({"tt": [{"__src_pk": "m1", "__tgt_pk": "c1"}]}))
    page = await graph_views.edges_page(reg, eng, None, 100)
    assert page["next_cursor"] is None  # 单链接单行 → 取尽
    e = page["edges"][0]
    assert e == {"source": "sn:m1", "target": "tn2:c1", "type": "ln", "label": "ln"}
    sql = eng._resolver.calls[0]
    assert "LOWER(BTRIM" in sql  # 归一化 join 与引擎级标准一致
    assert "IS NOT NULL" in sql  # 两侧非空守卫


@pytest.mark.asyncio
async def test_edges_page_excludes_stub_links():
    """真注册表: 输出边只来自 enabled 链接，且同输入同 cursor 幂等。

    EAI-CUSTOM(2026-09-27 registry 缩编): 真实 registry 已无 stub 链接（原 4 条跨模块 stub
    随四域 yaml 退场）——判别力从「stub 不产生边」改为「每条 enabled 链接都产边且不重不漏」
    （罐头 resolver 对任意 FROM 表回一对 pk，6 条链接各产 1 边）。
    """
    from app.ontology.registry import load_registry

    reg = load_registry()
    eng = SimpleNamespace(_resolver=FakeResolver({}))  # 任意 SQL → 罐头一对 pk
    stub_names = {lt.api_name for lt in reg.link_types.values() if not lt.enabled}
    enabled_names = {lt.api_name for lt in reg.link_types.values() if lt.enabled}
    assert enabled_names and not stub_names  # 缩编后现实: 全 enabled
    p1 = await graph_views.edges_page(reg, eng, None, 5000)
    p2 = await graph_views.edges_page(reg, eng, None, 5000)
    assert p1 == p2
    types = {e["type"] for e in p1["edges"]}
    # EAI-CUSTOM(2026-09-27 双透镜去重): mention_of_eia_entity/relation 与
    # mention_of_entity/relation 同 FK 签名（目标为让位透镜 eia_entity/eia_relation），
    # 按签名让位。
    # EAI-CUSTOM(2026-09-29 mention 排除): mention_of_entity/relation 默认随 mention 节点
    # 一并排除（节点不在场则边成孤端；opt-in 契约见 mention 排除契约段）——期望集合 =
    # enabled 减去这四条。
    assert types == enabled_names - {"mention_of_eia_entity", "mention_of_eia_relation", "mention_of_entity", "mention_of_relation"}
    for e in p1["edges"]:
        assert set(e.keys()) == {"source", "target", "type", "label"}


# ---------- 跨 connector 回退路径（当前注册表无此类 enabled 链接，回归钉住 offset 契约 bug-3316） ----------


class FakeCrossEngine:
    """same() 恒 False → 强制走 _cross_connector_link_rows；list_objects keyset 枚举源表，get_links 每源实例产 1 条边。"""

    def __init__(self, source_rows: list[dict]):
        self.source_rows = source_rows
        self.fetch_calls = 0
        self._resolver = self._Res(self)

    class _Res:
        def __init__(self, outer):
            self.outer = outer

        async def fetch(self, access, sql, params=None):
            self.outer.fetch_calls += 1
            return []

        def same(self, a, b):
            return False

    async def list_objects(self, object_type, filters=None, q=None, limit=50, cursor=None, order=None, desc=False):
        start = int(cursor) if cursor else 0
        data = self.source_rows[start : start + limit]
        return {"data": data, "next_cursor": str(start + limit) if start + limit < len(self.source_rows) else None, "object_type": object_type}

    async def get_links(self, object_type, pk, link_type, limit=200):
        return {"data": [{"id": f"t{pk}"}], "link_type": link_type, "from": {"object_type": object_type, "pk": pk}}


def _cross_reg() -> SimpleNamespace:
    """source=data_source / target=postgres_ext（异 connector），单条 FK 链接。"""
    src = ObjectType(
        api_name="xsrc",
        display_name="xsrc",
        description="跨 connector 测试源",
        domain="test",
        access=AccessConfig(path="data_source", source_id="dsx", table_name="xsrc_t"),
        pk=PKConfig(column="id", api_name="id", type="string"),
        properties=[PropertySchema(name="id", api_name="id", type="string")],
    )
    tgt = ObjectType(
        api_name="xtgt",
        display_name="xtgt",
        description="跨 connector 测试目标",
        domain="test",
        access=AccessConfig(path="postgres_ext", table="xtgt_t"),
        pk=PKConfig(column="id", api_name="id", type="string"),
        properties=[PropertySchema(name="id", api_name="id", type="string")],
    )
    lt = _edge_link("lx", "xsrc", "xtgt", type="foreign_key", source_column="tid", target_column="id")
    return SimpleNamespace(object_types={"xsrc": src, "xtgt": tgt}, link_types={"lx": lt})


@pytest.mark.asyncio
async def test_edges_page_cross_connector_offset_contract():
    """回归钉（bug-3316, 规格审查发现）: 5 条跨 connector 边、limit=2 → 翻页取尽，
    无重复无遗漏、链接推进、末页 next_cursor=None。修复前每页重发头部 2 条边死循环。"""
    reg = _cross_reg()
    eng = FakeCrossEngine([{"id": f"s{i}"} for i in range(5)])
    seen: list[str] = []
    cursor, pages = None, 0
    while True:
        page = await graph_views.edges_page(reg, eng, cursor, 2)
        seen.extend(e["source"] for e in page["edges"])
        pages += 1
        assert pages < 10  # 防失控（修复前此循环永不终止）
        if page["next_cursor"] is None:
            break
        cursor = page["next_cursor"]
    assert pages == 3  # 5 条 / 每页 2 → 3 页
    assert seen == [f"xsrc:s{i}" for i in range(5)]  # 有序、不重、不漏、链接推进至取尽
    assert eng.fetch_calls == 0  # 跨 connector 回退绝不走专用 SQL 通道


@pytest.mark.asyncio
async def test_cursor_huge_offset_rejected():
    """硬化回归: 巨型 offset = 敌意游标 → decode None（按垃圾处理，翻页从头开始，绝不产生无界 SQL OFFSET）。"""
    assert graph_views.decode_cursor(graph_views.encode_cursor(0, graph_views._MAX_OFFSET)) is not None  # 上限内合法
    assert graph_views.decode_cursor(graph_views.encode_cursor(0, graph_views._MAX_OFFSET + 1)) is None
    assert graph_views.decode_cursor(graph_views.encode_cursor(0, 10**12)) is None
    # 端到端: 超限游标被当从头开始（与 fresh 结果一致，不会把 offset 拼进 SQL OFFSET）
    reg, eng, _resolver = _edges_reg_fk_only()
    r1 = await graph_views.edges_page(reg, eng, graph_views.encode_cursor(0, 10**12), 2)
    r2 = await graph_views.edges_page(reg, eng, None, 2)
    assert r1 == r2  # 超限游标 ≡ fresh 起点


# ---------- mention 排除契约（EAI-CUSTOM 2026-09-29, 批量入图淹没回归） ----------
#
# 生产事故形态: dg_mentions 批量入图 120→5050 行，而 graph_mention 是 4 条 mention 链的
# source（链接引用数=4，压过实体/关系的各 3），projection_order 排序**首位**——/graph/nodes
# limit=500 窗口被 uuid 标签的 mention 节点灌满，实体/关系节点整类型出不了画布。此处复刻同款
# 拓扑（doc_graph 三类型 + eia 双透镜 + 6 链接、同表让位），钉住「默认排除 + include opt-in」契约。


def _mentions_flood_reg() -> SimpleNamespace:
    """仿真生产拓扑: graph_mention 链接引用数 4 排首位；eia_entity/eia_relation 同表让位进 lens。

    用真 pydantic ObjectType（同 _edge_obj）——nodes 走 properties/searchable、edges 走
    access/pk.column/物理表，一套类型两条路径通吃。"""

    def obj(api_name: str, table: str) -> ObjectType:
        return ObjectType(
            api_name=api_name,
            display_name=api_name,
            description="mention 淹没契约测试",
            domain="test",
            access=AccessConfig(path="postgres_ext", table=table),
            pk=PKConfig(column="id", api_name="id", type="string"),
            properties=[
                PropertySchema(name="id", api_name="id", type="string"),
                PropertySchema(name="name", api_name="name", type="string", searchable=True),
            ],
        )

    types = {
        "graph_entity": obj("graph_entity", "dg_entities"),
        "graph_relation": obj("graph_relation", "dg_relations"),
        "graph_mention": obj("graph_mention", "dg_mentions"),
        "eia_entity": obj("eia_entity", "dg_entities"),
        "eia_relation": obj("eia_relation", "dg_relations"),
    }
    links = {
        "relation_subject": _edge_link("relation_subject", "graph_relation", "graph_entity", type="foreign_key", source_column="subject_id", target_column="id"),
        "relation_object": _edge_link("relation_object", "graph_relation", "graph_entity", type="foreign_key", source_column="object_id", target_column="id"),
        "mention_of_entity": _edge_link("mention_of_entity", "graph_mention", "graph_entity", type="foreign_key", source_column="entity_id", target_column="id"),
        "mention_of_relation": _edge_link("mention_of_relation", "graph_mention", "graph_relation", type="foreign_key", source_column="relation_id", target_column="id"),
        "mention_of_eia_entity": _edge_link("mention_of_eia_entity", "graph_mention", "eia_entity", type="foreign_key", source_column="entity_id", target_column="id"),
        "mention_of_eia_relation": _edge_link("mention_of_eia_relation", "graph_mention", "eia_relation", type="foreign_key", source_column="relation_id", target_column="id"),
    }
    return SimpleNamespace(object_types=types, link_types=links)


def _flood_rows() -> dict[str, list[dict]]:
    return {
        "graph_entity": [{"id": f"e{i}", "name": f"实体{i}"} for i in range(3)],
        "graph_relation": [{"id": f"r{i}", "name": f"关系{i}"} for i in range(2)],
        "graph_mention": [{"id": f"m{i}", "name": f"提及{i}"} for i in range(600)],
        "eia_entity": [],
        "eia_relation": [],
    }


@pytest.mark.asyncio
async def test_nodes_page_mentions_flood_do_not_squeeze_entities():
    """600 mentions + 5 实体/关系、limit=500: 默认投影只出实体/关系节点，mention 不挤占窗口。

    修复前 graph_mention 排序首位（链接引用数 4 压过实体/关系各 3），整窗 500 条 uuid 标签
    mention、graph_entity/graph_relation 整类型出不了首页。"""
    reg = _mentions_flood_reg()
    page = await graph_views.nodes_page(reg, FakeEngine(_flood_rows()), None, 500)
    counter = Counter(n["type"] for n in page["nodes"])
    assert counter == {"graph_entity": 3, "graph_relation": 2}  # 实体/关系全量在场，mention 零出场
    assert page["next_cursor"] is None  # 实体窗口内取尽，无需翻页
    assert not any(n["type"] == "graph_mention" for n in page["nodes"])


@pytest.mark.asyncio
async def test_nodes_page_include_mentions_opt_in_restores_full_set():
    """include_mentions=True 恢复旧全集行为: graph_mention 回到首位参与排水，翻页不重不漏。"""
    reg = _mentions_flood_reg()
    eng = FakeEngine(_flood_rows())
    first = await graph_views.nodes_page(reg, eng, None, 500, include_mentions=True)
    counter = Counter(n["type"] for n in first["nodes"])
    assert counter == {"graph_mention": 500}  # 修复前形态复现: 首窗 500 条全是 mention
    assert first["next_cursor"] is not None
    # 排水取尽: 605 节点无重无漏
    seen: list[str] = [n["id"] for n in first["nodes"]]
    cursor = first["next_cursor"]
    while cursor:
        page = await graph_views.nodes_page(reg, eng, cursor, 500, include_mentions=True)
        seen.extend(n["id"] for n in page["nodes"])
        cursor = page["next_cursor"]
    assert len(seen) == len(set(seen)) == 605
    assert Counter(t for t in (s.split(":")[0] for s in seen)) == {"graph_entity": 3, "graph_relation": 2, "graph_mention": 600}


@pytest.mark.asyncio
async def test_edges_page_mention_links_excluded_in_tandem():
    """默认边投影与节点同规则排除 mention 链接（节点不在场则边成孤端）；opt-in 同步恢复。

    mention_of_eia_* 无论何种模式都因目标为让位透镜（eia_entity/eia_relation）被 2026-09-27
    去重丢弃——两个排除系统叠加的回归钉。"""
    reg = _mentions_flood_reg()
    resolver = FakeResolver(
        {
            "dg_entities": [{"__src_pk": "m0", "__tgt_pk": "e0"}, {"__src_pk": "m1", "__tgt_pk": "e1"}],  # FROM=目标表
            "dg_relations": [{"__src_pk": "m0", "__tgt_pk": "r0"}, {"__src_pk": "m1", "__tgt_pk": "r1"}],
        }
    )
    eng = SimpleNamespace(_resolver=resolver)
    default = await graph_views.edges_page(reg, eng, None, 100)
    assert Counter(e["type"] for e in default["edges"]) == {"relation_subject": 2, "relation_object": 2}  # mention 零边
    opted_in = await graph_views.edges_page(reg, eng, None, 100, include_mentions=True)
    assert Counter(e["type"] for e in opted_in["edges"]) == {
        "relation_subject": 2,
        "relation_object": 2,
        "mention_of_entity": 2,
        "mention_of_relation": 2,
    }  # eia 透镜对仍被签名让位丢弃


# ---------- 图谱投影域过滤契约（EAI-CUSTOM 2026-09-29） ----------
#
# 语义：domain= 只裁**实体类型行**（声明了 filterable domain 属性的类型，走引擎行过滤，
# 与 /objects 同一条引擎路径）；无域列类型（dg_relations/dg_mentions）不裁剪——脚手架
# 保持可见，与前端既有透明化行为（空域属性节点在域过滤下可见）一致。缺省（无参数）
# 行为逐字节不变。


def _domain_reg() -> SimpleNamespace:
    """实体类型（有域列）+ 关系类型（无域列）+ 二者间一条 FK 链接（仿真 doc_graph 拓扑）。"""
    return SimpleNamespace(
        object_types={
            "ent": _edge_obj("ent", "dg_entities", "id", with_domain=True),
            "rel": _edge_obj("rel", "dg_relations", "id"),
        },
        link_types={
            "rel_ent": _edge_link("rel_ent", "rel", "ent", type="foreign_key", source_column="subject_id", target_column="id"),
        },
    )


@pytest.mark.asyncio
async def test_nodes_page_domain_filter_hits_only_domain_capable_types():
    """domain=eia：实体类型收到引擎行过滤，无域列类型收到 None（不裁剪）；缺省全 None。"""
    reg = _domain_reg()
    rows = {
        "ent": [{"id": f"e{i}", "name": f"实体{i}"} for i in range(2)],
        "rel": [{"id": f"r{i}", "name": f"关系{i}"} for i in range(2)],
    }
    eng = FakeEngine(rows)
    await graph_views.nodes_page(reg, eng, None, 100, domain="eia")
    by_type = dict(eng.filter_calls)
    assert by_type["ent"] == [{"column": "domain", "op": "eq", "value": "eia"}], "有域列类型必须走引擎行过滤"
    assert by_type["rel"] is None, "无域列类型不裁剪（脚手架语义，与前端既有透明化行为一致）"
    # 缺省（无 domain 参数）行为不变：全部类型 filters=None
    eng_default = FakeEngine(rows)
    await graph_views.nodes_page(reg, eng_default, None, 100)
    assert all(f is None for _, f in eng_default.filter_calls)


@pytest.mark.asyncio
async def test_edges_page_domain_guard_on_capable_endpoint_only():
    """domain 激活：FK 链接只给**有域列的一端**加守卫（实体端 t."domain"），无域列端不守卫。

    仿真 relation_subject 拓扑（源=关系无域列、目标=实体有域列）——守卫列名用属性
    name（物理列），参数键 gd_tgt 与 gd_src 命名空间独立。
    """
    reg = _domain_reg()
    resolver = FakeResolver({"dg_entities": [{"__src_pk": "r0", "__tgt_pk": "e0"}]})
    eng = SimpleNamespace(_resolver=resolver)
    await graph_views.edges_page(reg, eng, None, 100, domain="doc_graph")
    sql = resolver.calls[0]
    assert 't."domain" = :gd_tgt' in sql, "有域列的一端必须加行域守卫"
    assert "gd_src" not in sql, "无域列的一端不得守卫（dg_relations 物理无 domain 列）"
    assert "ORDER BY 1, 2 LIMIT" in sql  # 分页尾巴不受影响
    # 缺省行为不变：无守卫、无域参数
    resolver_default = FakeResolver({"dg_entities": [{"__src_pk": "r0", "__tgt_pk": "e0"}]})
    await graph_views.edges_page(reg, SimpleNamespace(_resolver=resolver_default), None, 100)
    assert "gd_tgt" not in resolver_default.calls[0] and "gd_src" not in resolver_default.calls[0]


@pytest.mark.asyncio
async def test_edges_page_domain_guard_both_sides_when_capable():
    """两端都有域列：两侧守卫都加（未来实体-实体直连链接的形态）。"""
    reg = SimpleNamespace(
        object_types={
            "a": _edge_obj("a", "ta", "id", with_domain=True),
            "b": _edge_obj("b", "tb", "id", with_domain=True),
        },
        link_types={"ab": _edge_link("ab", "a", "b", type="foreign_key", source_column="bid", target_column="id")},
    )
    resolver = FakeResolver({"tb": [{"__src_pk": "a0", "__tgt_pk": "b0"}]})
    await graph_views.edges_page(reg, SimpleNamespace(_resolver=resolver), None, 100, domain="eia")
    sql = resolver.calls[0]
    assert 's."domain" = :gd_src' in sql and 't."domain" = :gd_tgt' in sql


@pytest.mark.asyncio
async def test_edges_page_domain_guard_in_normalized_join_path():
    """normalized_key_match 路径同样带域守卫（拼进既有 WHERE guards，尾部分页不受影响）。"""
    reg = SimpleNamespace(
        object_types={
            "sn": _edge_obj("sn", "tn", "mid", with_domain=True),
            "tn2": _edge_obj("tn2", "tt", "cid", with_domain=True),
        },
        link_types={"ln": _edge_link("ln", "sn", "tn2", type="normalized_key_match", key_pairs=[["code", "code"]])},
    )
    eng = SimpleNamespace(_resolver=FakeResolver({"tt": [{"__src_pk": "m1", "__tgt_pk": "c1"}]}))
    page = await graph_views.edges_page(reg, eng, None, 100, domain="doc_graph")
    sql = eng._resolver.calls[0]
    assert 's."domain" = :gd_src' in sql and 't."domain" = :gd_tgt' in sql
    assert "LOWER(BTRIM" in sql and "IS NOT NULL" in sql  # 归一化 join 与非空守卫保持
    assert page["next_cursor"] is None


@pytest.mark.asyncio
async def test_edges_page_domain_fails_closed_on_cross_connector():
    """域过滤激活时跨 connector 回退**整链接不产边**（fail-closed 到空而非半过滤）。"""
    reg = _cross_reg()
    eng = FakeCrossEngine([{"id": f"s{i}"} for i in range(5)])
    page = await graph_views.edges_page(reg, eng, None, 100, domain="doc_graph")
    assert page["edges"] == [] and page["next_cursor"] is None
    assert eng.fetch_calls == 0  # 未发起任何 SQL（在枚举之前短路）


# ---------- 折叠边投影契约（EAI-CUSTOM 2026-09-30, mode="flat"） ----------
#
# 用户期望: 画布上关系是连线不是圆点。flat 模式把关系行直接折叠为 实体—谓词—实体
# 带标签边（source=主体实体节点 id、target=客体实体节点 id、type=label=谓词值、
# relation_pk=关系行 id），悬挂的 relation_subject/object 边不再依赖关系节点在场。
# default 模式逐字节不变（回归钉见末例）。


def _flat_reg() -> SimpleNamespace:
    """仿真 doc_graph.yaml 拓扑: graph_relation(属性声明序 subject_id→predicate→object_id,
    有谓词列) 经 relation_subject/object 两条 FK 链接指向 graph_entity(有 filterable 域列);
    graph_mention 组两条链接但无谓词列——flat 下折叠组直接不形成（证据行无三元组可标）。"""

    def obj(api_name: str, table: str, props: list[PropertySchema]) -> ObjectType:
        return ObjectType(
            api_name=api_name,
            display_name=api_name,
            description="折叠边契约测试",
            domain="test",
            access=AccessConfig(path="postgres_ext", table=table),
            pk=PKConfig(column="id", api_name="id", type="string"),
            properties=props,
        )

    types = {
        "graph_entity": obj(
            "graph_entity",
            "dg_entities",
            [
                PropertySchema(name="id", api_name="id", type="string"),
                PropertySchema(name="domain", api_name="domain", type="string", filterable=True),
            ],
        ),
        "graph_relation": obj(
            "graph_relation",
            "dg_relations",
            [
                PropertySchema(name="id", api_name="id", type="string"),
                PropertySchema(name="subject_id", api_name="subjectId", type="string"),
                PropertySchema(name="predicate", api_name="predicate", type="string"),
                PropertySchema(name="object_id", api_name="objectId", type="string"),
            ],
        ),
        "graph_mention": obj(
            "graph_mention",
            "dg_mentions",
            [
                PropertySchema(name="id", api_name="id", type="string"),
                PropertySchema(name="entity_id", api_name="entityId", type="string"),
                PropertySchema(name="relation_id", api_name="relationId", type="string"),
            ],
        ),
    }
    links = {
        "relation_subject": _edge_link("relation_subject", "graph_relation", "graph_entity", type="foreign_key", source_column="subject_id", target_column="id"),
        "relation_object": _edge_link("relation_object", "graph_relation", "graph_entity", type="foreign_key", source_column="object_id", target_column="id"),
        "mention_of_entity": _edge_link("mention_of_entity", "graph_mention", "graph_entity", type="foreign_key", source_column="entity_id", target_column="id"),
        "mention_of_relation": _edge_link("mention_of_relation", "graph_mention", "graph_relation", type="foreign_key", source_column="relation_id", target_column="id"),
    }
    return SimpleNamespace(object_types=types, link_types=links)


_FLAT_TRIPLES = [
    {"__ep_0": "e1", "__ep_1": "e2", "__predicate": "bidder_supplies_goods", "__relation_pk": "r1"},
    {"__ep_0": "e0", "__ep_1": "e2", "__predicate": "bidder_of_project", "__relation_pk": "r0"},
]


@pytest.mark.asyncio
async def test_edges_page_flat_collapses_relations_into_labeled_entity_edges():
    """flat: 关系行 → 实体—谓词—实体 折叠边——两端为实体节点 id（与 nodes 投影同构）、
    type=label=谓词值、relation_pk=行 id；SQL 端点经 JOIN 从实体表取 pk（悬挂 FK 天然
    丢弃），subject/object 方向随属性声明序（subject_id 先声明 → __ep_0=主体端）。"""
    reg = _flat_reg()
    resolver = FakeResolver({"dg_relations": _FLAT_TRIPLES})  # 折叠 SQL 的 FROM 表 = 关系表
    page = await graph_views.edges_page(reg, SimpleNamespace(_resolver=resolver), None, 100, mode="flat")
    assert page["next_cursor"] is None  # 单组取尽
    assert page["edges"] == [
        {"source": "graph_entity:e1", "target": "graph_entity:e2", "type": "bidder_supplies_goods", "label": "bidder_supplies_goods", "relation_pk": "r1"},
        {"source": "graph_entity:e0", "target": "graph_entity:e2", "type": "bidder_of_project", "label": "bidder_of_project", "relation_pk": "r0"},
    ]
    sql = resolver.calls[0]
    assert 'FROM "dg_relations" s' in sql
    assert 't0."id" = s."subject_id"' in sql and 't1."id" = s."object_id"' in sql  # __ep_0=主体、__ep_1=客体
    assert 's."predicate" AS "__predicate"' in sql and 's."id" AS "__relation_pk"' in sql
    assert "ORDER BY" in sql and "LIMIT" in sql and "OFFSET" in sql  # 分页尾巴与 default 同款


@pytest.mark.asyncio
async def test_edges_page_flat_mention_and_domain_params_effective():
    """mention: flat 下 mention 链接默认排除，include_mentions=True 也不产 mention 噪声边
    （证据行无谓词列，折叠组直接不形成——证据表从未被查询）；domain: 两端实体都有域列 →
    双端行域守卫（与 default 下同一关系的两条边各守实体端等价），缺省无守卫。"""
    reg = _flat_reg()
    resolver = FakeResolver({"dg_relations": _FLAT_TRIPLES})
    eng = SimpleNamespace(_resolver=resolver)
    default = await graph_views.edges_page(reg, eng, None, 100, mode="flat")
    opted_in = await graph_views.edges_page(reg, eng, None, 100, mode="flat", include_mentions=True)
    assert default == opted_in  # mention 折叠组无谓词列，opt-in 也不产出
    assert all('FROM "dg_mentions"' not in sql for sql in resolver.calls)  # 证据表从未进 SQL
    assert all(e["source"].startswith("graph_entity:") and e["target"].startswith("graph_entity:") for e in default["edges"])

    resolver_dom = FakeResolver({"dg_relations": _FLAT_TRIPLES})
    await graph_views.edges_page(reg, SimpleNamespace(_resolver=resolver_dom), None, 100, mode="flat", domain="eia")
    sql = resolver_dom.calls[0]
    assert 't0."domain" = :gd_0' in sql and 't1."domain" = :gd_1' in sql, "两端实体都有域列必须双端守卫"
    assert "gd_0" not in resolver.calls[0], "缺省（无 domain 参数）折叠 SQL 无域守卫"


@pytest.mark.asyncio
async def test_edges_page_default_mode_regression_with_flat_available():
    """default 回归: 不传 mode 与 mode="default" 输出完全一致，边形状仍为悬挂双轨
    （source=关系节点 id、四键无 relation_pk）；未知 mode 显式拒绝。"""
    reg = _flat_reg()
    rows = {
        "dg_entities": [{"__src_pk": "r0", "__tgt_pk": "e0"}, {"__src_pk": "r1", "__tgt_pk": "e1"}],  # default 边 SQL 的 FROM = 链接目标表
        "dg_relations": _FLAT_TRIPLES,
    }
    eng = SimpleNamespace(_resolver=FakeResolver(rows))
    d1 = await graph_views.edges_page(reg, eng, None, 100)
    d2 = await graph_views.edges_page(reg, eng, None, 100, mode="default")
    assert d1 == d2
    assert Counter(e["type"] for e in d1["edges"]) == {"relation_subject": 2, "relation_object": 2}
    assert all(set(e.keys()) == {"source", "target", "type", "label"} for e in d1["edges"])  # 无 relation_pk
    assert all(e["source"].startswith("graph_relation:") for e in d1["edges"])  # 悬挂双轨形态原样
    with pytest.raises(ValueError):
        await graph_views.edges_page(reg, eng, None, 100, mode="bogus")
