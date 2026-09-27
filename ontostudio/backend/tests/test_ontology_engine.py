"""T3 单测：引擎安全断言（注入/hidden/declared-only/stub/跳深）+ 分页/遍历/聚合.

设计: docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md §5-§6
计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T3 Verify
"""

from __future__ import annotations

import uuid

import pytest

from app.ontology.engine import (
    CHUNK,
    MAX_LIMIT,
    ColumnNotFilterableError,
    Engine,
    InvalidFilterError,
    LinkDisabledError,
    TraverseTooDeepError,
    UnknownColumnError,
    UnknownLinkError,
)
from app.ontology.registry import get_registry
from app.ontology.schemas import LinkType

UUID_S = "11111111-1111-1111-1111-111111111111"


class FakeResolver:
    """记录 SQL/参数并返回罐头行; same() 可注入。router(sql) 可按 SQL 路由返回值。

    COUNT(*) 查询回罐头 total（EAI-CUSTOM 2026-09-27 页码分页后 list_objects 附带 COUNT）。
    """

    def __init__(self, same_result: bool = True, router=None):
        self.calls: list[tuple[str, dict]] = []
        self.same_result = same_result
        self.rows: list[dict] = []
        self.router = router

    async def fetch(self, access, sql, params=None):
        self.calls.append((sql, params or {}))
        if self.router is not None:
            return self.router(sql)
        if "COUNT(*)" in sql:
            return [{"total": len(self.rows)}]
        return list(self.rows)

    def same(self, a, b):
        return self.same_result


def make_engine(same_result: bool = True, router=None) -> tuple[Engine, FakeResolver]:
    r = FakeResolver(same_result, router)
    return Engine(get_registry, r), r


@pytest.mark.asyncio
async def test_filter_values_are_bound_params():
    """注入断言：filter/search/q 值只出现在 params，绝不拼接进 SQL。"""
    eng, res = make_engine()
    evil = "x'; DROP TABLE dg_entities;--"
    await eng.list_objects("graph_entity", filters=[{"column": "domain", "op": "eq", "value": evil}])
    sql, params = res.calls[-1]
    assert evil not in sql
    assert evil in params.values()
    # declared-only: 仅声明列进 SQL 标识符位
    assert '"domain"' in sql


@pytest.mark.asyncio
async def test_undeclared_column_and_op_rejected():
    eng, _ = make_engine()
    with pytest.raises(UnknownColumnError):
        await eng.list_objects("graph_entity", filters=[{"column": "no_such_col", "op": "eq", "value": 1}])
    with pytest.raises(ColumnNotFilterableError):
        await eng.list_objects("graph_entity", filters=[{"column": "norm_name", "op": "eq", "value": "x"}])  # 声明列但未 filterable
    with pytest.raises(InvalidFilterError):
        await eng.list_objects("graph_entity", filters=[{"column": "domain", "op": "like", "value": "x"}])  # 未声明操作符
    with pytest.raises(UnknownColumnError):
        await eng.list_objects("graph_entity", order="no_such_col")


@pytest.mark.asyncio
async def test_hidden_column_never_projected():
    """hidden 列零透出：SELECT 投影与序列化双面断言。

    EAI-CUSTOM(2026-09-27 registry 缩编): 真实 registry 已无 hidden 列
    （data_source.connection_config 随四域 yaml 退场），本用例改合成 registry 守机制。
    """
    from types import SimpleNamespace

    from app.ontology.schemas import ObjectType

    obj = ObjectType.model_validate(
        {
            "api_name": "secret_thing",
            "display_name": "t",
            "description": "t",
            "domain": "t",
            "access": {"path": "postgres_ext", "table": "secret_thing"},
            "pk": {"column": "id", "api_name": "id", "type": "string"},
            "properties": [
                {"name": "id", "api_name": "id", "type": "string", "description": "pk"},
                {"name": "connection_config", "api_name": "connectionConfig", "type": "json", "description": "连接密文", "hidden": True},
                {"name": "name", "api_name": "name", "type": "string", "description": "名称"},
            ],
        }
    )
    reg = SimpleNamespace(object_types={"secret_thing": obj})
    eng = Engine(lambda: reg, FakeResolver())
    res = eng._resolver
    res.rows = [{"id": "X1", "connection_config": {"password": "SECRET"}, "name": "thing"}]
    out = await eng.list_objects("secret_thing")
    sql, _ = res.calls[0]
    assert "connection_config" not in sql
    assert "SECRET" not in str(out)
    assert all("connectionConfig" not in r for r in out["data"])


@pytest.mark.asyncio
async def test_unknown_and_disabled_link_traversal_rejected():
    """链接遍历拒绝双路径：未注册链接 → UnknownLinkError；enabled:false stub（D3 机制）→
    LinkDisabledError。EAI-CUSTOM(2026-09-27 registry 缩编): 真实 registry 已无 stub 链接
    （cross_module 等 stub 链接类型随 yaml 退场），stub 路径改合成链接守机制；
    未注册路径对真实 registry 断言（won_bid_contracts_project 等类型已不存在）。"""
    from types import SimpleNamespace

    eng, _ = make_engine()
    # 未注册：链接类型本身已不存在（随缩编删除）
    with pytest.raises(UnknownLinkError):
        await eng.get_links("graph_entity", UUID_S, "won_bid_contracts_project")
    with pytest.raises(UnknownLinkError):
        await eng.traverse("graph_entity", UUID_S, ["won_bid_contracts_project"])

    # stub：合成 enabled:false 链接，机制断言不变（describe 可见但遍历拒绝）
    real = get_registry()
    stub = LinkType.model_validate(
        {
            "api_name": "stub_link",
            "display_name": "合成 stub",
            "source": "graph_entity",
            "target": "eia_entity",
            "cardinality": "N:1",
            "reverse": "stub_link_r",
            "enabled": False,
            "note": "合成 stub——D3 机制回归锚（缩编后真实 registry 无 stub）",
            "join": {"type": "foreign_key", "source_column": "entity_id", "target_column": "id"},
        }
    )
    reg = SimpleNamespace(object_types=real.object_types, link_types={**real.link_types, "stub_link": stub})
    eng2 = Engine(lambda: reg, FakeResolver())
    with pytest.raises(LinkDisabledError):
        await eng2.get_links("graph_entity", UUID_S, "stub_link")
    with pytest.raises(LinkDisabledError):
        await eng2.traverse("graph_entity", UUID_S, ["stub_link"])


@pytest.mark.asyncio
async def test_traverse_max_hops():
    eng, _ = make_engine()
    with pytest.raises(TraverseTooDeepError):
        await eng.traverse("graph_entity", UUID_S, ["mention_of_entity"] * 6)
    # 恰 5 跳不因深度拒绝（会用罐头空结果走完）


@pytest.mark.asyncio
async def test_keyset_pagination_pk_tiebreaker():
    """排序值相同行集翻页：ORDER BY 恒带 pk tiebreaker，游标是 (order_val, pk) 行比较。"""
    eng, res = make_engine()
    n = len(res.calls)  # list_objects 无 cursor 时会追加 COUNT 查询 → 按序号取 SELECT
    await eng.list_objects("graph_entity", order="confidence", desc=True)
    sql, _ = res.calls[n]
    assert '"confidence" DESC, "id" DESC' in sql
    cur = Engine._encode_cursor(9.9, UUID_S)
    n = len(res.calls)
    await eng.list_objects("graph_entity", order="confidence", desc=True, cursor=cur)
    sql2, params2 = res.calls[n]
    assert '("confidence", "id") < (:_cv, :_cpk)' in sql2
    assert params2["_cpk"] == UUID_S
    with pytest.raises(InvalidFilterError):
        await eng.list_objects("graph_entity", cursor="!!!not-base64!!!")


@pytest.mark.asyncio
async def test_fk_same_connector_single_sql():
    eng, res = make_engine(same_result=True)
    await eng.get_links("graph_mention", UUID_S, "mention_of_entity")
    sql, params = res.calls[-1]
    assert "JOIN" in sql
    assert ":n0" in sql and params["n0"] == uuid.UUID(UUID_S)


@pytest.mark.asyncio
async def test_fk_reverse_direction_join_columns():
    """回归(eval 抓出): 反向遍历(实体→关系) join 条件必须是 far.fk = near.pk。

    FK 声明: source=graph_relation(source_column=subject_id) → target=graph_entity(target_column=id)。
    从 target 侧出发: far=dg_relations(t), near=dg_entities(s) → ON t."subject_id" = s."id"。
    """
    eng, res = make_engine(same_result=True)
    await eng.get_links("graph_entity", UUID_S, "relation_subject")
    sql, _ = res.calls[-1]
    assert 'FROM "dg_relations" t JOIN "dg_entities" s ON t."subject_id" = s."id"' in sql


@pytest.mark.asyncio
async def test_cross_connector_chunked_join():
    """D11: 跨 connector = 近侧取键 → 分块对侧 IN 查询; 键集 >CHUNK 自动分批不丢。

    EAI-CUSTOM(2026-09-27 registry 缩编): 原 bid/goods_cluster 合成对象退场，
    改真实 registry 的 graph_entity/graph_relation 顶名（same() 注入 False 强制跨 connector
    路径，键列不入 registry 亦可——引擎运行时不做 declared-only 复查）。
    """
    near_rows = [{"project_name": f"proj{i}"} for i in range(450)]

    def router(sql: str):
        return near_rows if '"dg_entities"' in sql else []  # 近侧回键, 对侧回空

    eng, res = make_engine(same_result=False, router=router)
    lt = LinkType.model_validate(
        {
            "api_name": "test_x",
            "display_name": "x",
            "source": "graph_entity",
            "target": "graph_relation",
            "cardinality": "N:N",
            "reverse": "test_x_r",
            "join": {"type": "normalized_key_match", "key_pairs": [["project_name", "predicate"]]},
        }
    )
    rows = await eng._follow(lt, forward=True, pks=[UUID_S], limit=MAX_LIMIT * 4)
    far_calls = [c for c in res.calls if '"dg_relations"' in c[0]]
    assert len(far_calls) == 3, f"450 键应分 3 批(200+200+50), 实际 {len(far_calls)}"
    # 每批占位符 ≤ CHUNK
    for sql, params in far_calls:
        assert len(params) <= CHUNK
    # 归一化标准断言: LOWER(BTRIM(...)) + 非空守卫
    near_sql = res.calls[0][0]
    assert "LOWER(BTRIM(" in near_sql and "<> ''" in near_sql
    assert rows == []


@pytest.mark.asyncio
async def test_aggregate_validation():
    eng, _ = make_engine()
    with pytest.raises(InvalidFilterError):
        await eng.aggregate("graph_entity", group_by="etype", metric="median")
    with pytest.raises(InvalidFilterError):
        await eng.aggregate("graph_entity", group_by="etype", metric="sum")  # sum 缺 metric_column
    with pytest.raises(InvalidFilterError):
        await eng.aggregate("graph_entity", group_by="etype", metric="sum", metric_column="domain")  # 非数值列
    eng2, res2 = make_engine()
    res2.rows = [{"group": "doc_graph", "value": 3}]
    out = await eng2.aggregate("graph_entity", group_by="status", metric="avg", metric_column="confidence")
    sql, _ = res2.calls[-1]
    assert 'AVG("confidence")' in sql and 'GROUP BY "status"' in sql
    assert out["data"] == [{"group": "doc_graph", "value": 3}]


@pytest.mark.asyncio
async def test_search_requires_searchable_and_binds_q():
    eng, res = make_engine()
    await eng.list_objects("graph_entity", q="水泵'; --")
    sql, params = res.calls[-1]
    assert "ILIKE" in sql
    assert any("水泵'; --" in str(v) for v in params.values())
    assert "水泵" not in sql


@pytest.mark.asyncio
async def test_get_object_serializes_api_names():
    eng, res = make_engine()
    res.rows = [{"id": UUID_S, "canonical_name": 100.0}]
    out = await eng.get_object("graph_entity", UUID_S)
    assert out["canonicalName"] == 100.0 and "canonical_name" not in out
