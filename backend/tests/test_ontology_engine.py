"""T3 单测：引擎安全断言（注入/hidden/declared-only/stub/跳深）+ 分页/遍历/聚合.

设计: docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md §5-§6
计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T3 Verify
"""

from __future__ import annotations

import uuid

import pytest

from app.extensions.ontology.engine import (
    CHUNK,
    MAX_LIMIT,
    ColumnNotFilterableError,
    Engine,
    InvalidFilterError,
    LinkDisabledError,
    TraverseTooDeepError,
    UnknownColumnError,
)
from app.extensions.ontology.registry import get_registry
from app.extensions.ontology.schemas import LinkType

UUID_S = "11111111-1111-1111-1111-111111111111"


class FakeResolver:
    """记录 SQL/参数并返回罐头行; same() 可注入。router(sql) 可按 SQL 路由返回值。"""

    def __init__(self, same_result: bool = True, router=None):
        self.calls: list[tuple[str, dict]] = []
        self.same_result = same_result
        self.rows: list[dict] = []
        self.router = router

    async def fetch(self, access, sql, params=None):
        self.calls.append((sql, params or {}))
        if self.router is not None:
            return self.router(sql)
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
    evil = "x'; DROP TABLE cpa_items;--"
    await eng.list_objects("contract_item", filters=[{"column": "unit_price", "op": "eq", "value": evil}])
    sql, params = res.calls[-1]
    assert evil not in sql
    assert evil in params.values()
    # declared-only: 仅声明列进 SQL 标识符位
    assert '"unit_price"' in sql


@pytest.mark.asyncio
async def test_undeclared_column_and_op_rejected():
    eng, _ = make_engine()
    with pytest.raises(UnknownColumnError):
        await eng.list_objects("contract_item", filters=[{"column": "no_such_col", "op": "eq", "value": 1}])
    with pytest.raises(ColumnNotFilterableError):
        await eng.list_objects("contract_item", filters=[{"column": "spec_model", "op": "eq", "value": "x"}])  # 声明列但未 filterable
    with pytest.raises(InvalidFilterError):
        await eng.list_objects("contract_item", filters=[{"column": "unit_price", "op": "like", "value": "x"}])  # 未声明操作符
    with pytest.raises(UnknownColumnError):
        await eng.list_objects("contract_item", order="no_such_col")


@pytest.mark.asyncio
async def test_hidden_column_never_projected():
    """hidden 列零透出：SELECT 投影与序列化双面断言。"""
    eng, res = make_engine()
    res.rows = [{"id": UUID_S, "connection_config": {"password": "SECRET"}, "name": "bid-quote"}]
    out = await eng.list_objects("data_source")
    sql, _ = res.calls[-1]
    assert "connection_config" not in sql
    assert "SECRET" not in str(out)
    assert all("connectionConfig" not in r for r in out["data"])


@pytest.mark.asyncio
async def test_stub_link_traversal_rejected():
    """D3: enabled:false 链接 describe 可见但遍历拒绝。"""
    eng, _ = make_engine()
    with pytest.raises(LinkDisabledError):
        await eng.get_links("bid", "B001", "won_bid_contracts_project")
    with pytest.raises(LinkDisabledError):
        await eng.traverse("bid", "B001", ["won_bid_contracts_project"])


@pytest.mark.asyncio
async def test_traverse_max_hops():
    eng, _ = make_engine()
    with pytest.raises(TraverseTooDeepError):
        await eng.traverse("contract_item", UUID_S, ["a"] * 6)
    # 恰 5 跳不因深度拒绝（会用罐头空结果走完）


@pytest.mark.asyncio
async def test_keyset_pagination_pk_tiebreaker():
    """排序值相同行集翻页：ORDER BY 恒带 pk tiebreaker，游标是 (order_val, pk) 行比较。"""
    eng, res = make_engine()
    await eng.list_objects("contract_item", order="unit_price", desc=True)
    sql, _ = res.calls[-1]
    assert '"unit_price" DESC, "id" DESC' in sql
    cur = Engine._encode_cursor(9.9, UUID_S)
    await eng.list_objects("contract_item", order="unit_price", desc=True, cursor=cur)
    sql2, params2 = res.calls[-1]
    assert '("unit_price", "id") < (:_cv, :_cpk)' in sql2
    assert params2["_cpk"] == UUID_S
    with pytest.raises(InvalidFilterError):
        await eng.list_objects("contract_item", cursor="!!!not-base64!!!")


@pytest.mark.asyncio
async def test_fk_same_connector_single_sql():
    eng, res = make_engine(same_result=True)
    await eng.get_links("contract_item", UUID_S, "contract_item_in_cluster")
    sql, params = res.calls[-1]
    assert "JOIN" in sql
    assert ":n0" in sql and params["n0"] == uuid.UUID(UUID_S)


@pytest.mark.asyncio
async def test_fk_reverse_direction_join_columns():
    """回归(eval 抓出): 反向遍历(文档→条目) join 条件必须是 far.fk = near.pk。

    FK 声明: source=contract_item(source_column=document_id) → target=contract_document(target_column=id)。
    从 target 侧出发: far=cpa_items(t), near=cpa_documents(s) → ON t."document_id" = s."id"。
    """
    eng, res = make_engine(same_result=True)
    await eng.get_links("contract_document", UUID_S, "contract_item_in_document")
    sql, _ = res.calls[-1]
    assert 'FROM "cpa_items" t JOIN "cpa_documents" s ON t."document_id" = s."id"' in sql


@pytest.mark.asyncio
async def test_cross_connector_chunked_join():
    """D11: 跨 connector = 近侧取键 → 分块对侧 IN 查询; 键集 >CHUNK 自动分批不丢。"""
    near_rows = [{"project_name": f"proj{i}"} for i in range(450)]

    def router(sql: str):
        return near_rows if '"mock_bid"' in sql else []  # 近侧回键, 对侧回空

    eng, res = make_engine(same_result=False, router=router)
    lt = LinkType.model_validate(
        {
            "api_name": "test_x",
            "display_name": "x",
            "source": "bid",
            "target": "goods_cluster",
            "cardinality": "N:N",
            "reverse": "test_x_r",
            "join": {"type": "normalized_key_match", "key_pairs": [["project_name", "representative_name"]]},
        }
    )
    rows = await eng._follow(lt, forward=True, pks=["B1"], limit=MAX_LIMIT * 4)
    far_calls = [c for c in res.calls if "cpa_clusters" in c[0]]
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
        await eng.aggregate("contract_item", group_by="goods_name", metric="median")
    with pytest.raises(InvalidFilterError):
        await eng.aggregate("contract_item", group_by="goods_name", metric="sum")  # sum 缺 metric_column
    with pytest.raises(InvalidFilterError):
        await eng.aggregate("contract_item", group_by="goods_name", metric="sum", metric_column="goods_name")  # 非数值列
    eng2, res2 = make_engine()
    res2.rows = [{"group": "pump", "value": 3}]
    out = await eng2.aggregate("contract_item", group_by="validation_status", metric="avg", metric_column="unit_price")
    sql, _ = res2.calls[-1]
    assert 'AVG("unit_price")' in sql and 'GROUP BY "validation_status"' in sql
    assert out["data"] == [{"group": "pump", "value": 3}]


@pytest.mark.asyncio
async def test_search_requires_searchable_and_binds_q():
    eng, res = make_engine()
    await eng.list_objects("contract_document", q="水泵'; --")
    sql, params = res.calls[-1]
    assert "ILIKE" in sql
    assert any("水泵'; --" in str(v) for v in params.values())
    assert "水泵" not in sql


@pytest.mark.asyncio
async def test_get_object_serializes_api_names():
    eng, res = make_engine()
    res.rows = [{"id": UUID_S, "unit_price": 100.0}]
    out = await eng.get_object("contract_item", UUID_S)
    assert out["unitPrice"] == 100.0 and "unit_price" not in out
