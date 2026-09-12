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

from app.extensions.ontology import graph_views
from app.extensions.ontology.schemas import (
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
    """nodes 用: 对齐 engine.list_objects 真实签名与 {"data","next_cursor","object_type"} 返回形状（engine.py:88-136）。"""

    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables
        self.calls: list[tuple[str, int, str | None]] = []

    async def list_objects(self, object_type, filters=None, q=None, limit=50, cursor=None, order=None, desc=False):
        self.calls.append((object_type, limit, cursor))
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


def _edge_obj(api_name: str, table: str, pk_col: str) -> ObjectType:
    """真 pydantic ObjectType（edges SQL 构建走真实 schema 形状）。"""
    return ObjectType(
        api_name=api_name,
        display_name=api_name,
        description="契约测试",
        domain="test",
        access=AccessConfig(path="postgres_ext", table=table),
        pk=PKConfig(column=pk_col, api_name=pk_col, type="string"),
        properties=[PropertySchema(name=pk_col, api_name=pk_col, type="string")],
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
    reg = SimpleNamespace(
        object_types={"sa": _edge_obj("sa", "ta", "sid"), "sb": _edge_obj("sb", "tb", "pid")},
        link_types={
            "la": _edge_link("la", "sa", "sb", type="foreign_key", source_column="sid", target_column="pid"),
            "lb": _edge_link("lb", "sa", "sb", type="foreign_key", source_column="sid", target_column="pid"),
        },
    )
    pairs = [{"__src_pk": f"s{i}", "__tgt_pk": f"p{i}"} for i in range(3)]
    resolver = FakeResolver({"tb": pairs})  # FK SQL 的 FROM 表 = target 表
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
    """真注册表: 输出边只来自 enabled 链接（stub=4 条不产生边），且同输入同 cursor 幂等。"""
    from app.extensions.ontology.registry import load_registry

    reg = load_registry()
    eng = SimpleNamespace(_resolver=FakeResolver({}))  # 任意 SQL → 罐头一对 pk
    stub_names = {lt.api_name for lt in reg.link_types.values() if not lt.enabled}
    enabled_names = {lt.api_name for lt in reg.link_types.values() if lt.enabled}
    assert stub_names  # 真注册表确有 stub（当前 4 条），断言非空才有判别力
    p1 = await graph_views.edges_page(reg, eng, None, 5000)
    p2 = await graph_views.edges_page(reg, eng, None, 5000)
    assert p1 == p2
    types = {e["type"] for e in p1["edges"]}
    assert types <= enabled_names and not (types & stub_names)
    for e in p1["edges"]:
        assert set(e.keys()) == {"source", "target", "type", "label"}
