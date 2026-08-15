"""Tests for ontology query engine (pure helpers + fake-connector integration)."""

import asyncio
from decimal import Decimal

import pytest

from app.extensions.ontology.engine.query import (
    QueryEngine,
    cursor_decode,
    cursor_encode,
    resolve_fk_where,
    rewrite_match_expression,
)
from app.extensions.ontology.registry import (
    AccessDecl,
    JoinDecl,
    LinkTypeDecl,
    ObjectTypeDecl,
    PkDecl,
    PropertyDecl,
    load_registry,
)


def test_cursor_roundtrip():
    enc = cursor_encode("abc-123")
    assert cursor_decode(enc) == "abc-123"


def _fk_link():
    return LinkTypeDecl(
        api_name="item_in_document",
        display_name="d",
        source="contract_item",
        target="contract_document",
        cardinality="N:1",
        join=JoinDecl(type="foreign_key", source_column="document_id", target_column="id"),
    )


def test_resolve_fk_where():
    link = _fk_link()
    # forward: target docs whose pk is in the item's document_id values (subquery on source table)
    fwd = resolve_fk_where(link, source_table="cpa_items", source_pk_col="id", target_pk_col="id", forward=True)
    assert "document_id" in fwd and "IN (SELECT" in fwd and "cpa_items" in fwd
    # reverse: items whose document_id equals the current document pk
    rev = resolve_fk_where(link, "cpa_items", "id", "id", forward=False)
    assert rev == '"document_id" = :p0'


def test_rewrite_match_expression_substitutes_current_side():
    obj = ObjectTypeDecl(
        api_name="bid",
        display_name="投标",
        description="d",
        domain="bid_quote",
        access=AccessDecl(path="data_source", source_id="bid-quote", table_name="mock_bid"),
        pk=PkDecl(column="bid_id", api_name="bidId", type="string", immutable=True),
        properties=[
            PropertyDecl(name="project_name", api_name="projectName", type="string"),
            PropertyDecl(name="won", api_name="won", type="boolean"),
        ],
    )
    cur = {"primaryKey": "B1", "properties": {"projectName": "电厂项目", "won": True}}
    expr = "LOWER(BTRIM(mock_bid.project_name)) = LOWER(BTRIM(cpa_documents.project_name)) AND mock_bid.won = true"
    out, bind = rewrite_match_expression(expr, "mock_bid", obj, cur)
    assert "mock_bid" not in out  # current-side refs fully substituted
    assert "cpa_documents.project_name" in out  # target side untouched
    assert set(bind.values()) == {"电厂项目", True}


class FakeConnector:
    """Records calls; returns scripted rows per call."""

    def __init__(self, script=None):
        self.calls: list[tuple] = []
        self.script = script or []

    async def execute_select(self, *args, **kwargs):
        self.calls.append(tuple(args))
        return self.script.pop(0) if self.script else []

    async def run_raw_select(self, *args, **kwargs):
        self.calls.append(("raw",) + tuple(args))
        return self.script.pop(0) if self.script else []


def test_engine_list_maps_rows_and_compiles_filter():
    fake = FakeConnector(script=[[{"id": "a1", "goods_name": "泵", "unit_price": Decimal("10.5")}, {"id": "a2", "goods_name": "阀", "unit_price": None}]])
    eng = QueryEngine(load_registry(), pg_connector=fake, ds_connector=fake)
    out = asyncio.run(eng.list("contract_item", {"goodsName": {"eq": "泵"}}))
    assert out["objects"][0]["properties"]["goodsName"] == "泵"
    assert out["objects"][0]["primaryKey"] == "a1"
    table, cols, where, bind, order_by, limit = fake.calls[0]
    assert table == "cpa_items" and "goods_name = :p0" in where and bind == {"p0": "泵"}


def test_engine_aggregate_whitelists_fn():
    fake = FakeConnector()
    eng = QueryEngine(load_registry(), pg_connector=fake, ds_connector=fake)
    with pytest.raises(ValueError, match="unsupported aggregate fn"):
        asyncio.run(eng.aggregate("contract_item", metric={"fn": "evil; DROP TABLE"}))


def test_engine_aggregate_builds_grouped_sql():
    fake = FakeConnector(script=[[{"group_value": "泵", "value": Decimal("12.5")}]])
    eng = QueryEngine(load_registry(), pg_connector=fake, ds_connector=fake)
    rows = asyncio.run(eng.aggregate("contract_item", group_by="goodsName", metric={"field": "unitPrice", "fn": "avg"}))
    assert rows == [{"group_value": "泵", "value": 12.5}]
    _, sql, bind = fake.calls[0]
    assert "AVG(unit_price) AS value" in sql and '"goods_name" AS group_value' in sql and "GROUP BY" in sql


def test_engine_get_links_fk_forward():
    fake = FakeConnector(script=[[{"id": "doc1", "contract_no": "C1"}]])
    eng = QueryEngine(load_registry(), pg_connector=fake, ds_connector=fake)
    out = asyncio.run(eng.get_links("contract_item", "a1", "item_in_document"))
    assert out["objects"][0]["primaryKey"] == "doc1"
    table, cols, where, bind, order_by, limit = fake.calls[0]
    assert table == "cpa_documents"
    assert "IN (SELECT" in where and "document_id" in where and bind == {"p0": "a1"}


def test_engine_get_links_normalized_match_cross_db():
    # first call: get(bid) on mock_bid via data_source path; second: cpa_documents via postgres_ext
    fake = FakeConnector(
        script=[
            [{"bid_id": "B1", "project_name": "电厂项目", "won": True}],
            [{"id": "c1", "project_name": "电厂项目", "supplier": "ACME"}],
        ]
    )
    eng = QueryEngine(load_registry(), pg_connector=fake, ds_connector=fake)
    out = asyncio.run(eng.get_links("bid", "B1", "won_bid_contracts_project"))
    assert out["objects"][0]["primaryKey"] == "c1"
    first = fake.calls[0]
    assert first[0] == "bid-quote" and first[1] == "mock_bid"  # data_source-arity dispatch
    table, cols, where, bind, order_by, limit = fake.calls[1]
    assert table == "cpa_documents"
    assert "mock_bid" not in where and "cpa_documents.project_name" in where  # current side substituted
    assert "电厂项目" in bind.values() and True in bind.values()


def test_engine_traverse_path_two_hops():
    fake = FakeConnector(
        script=[
            [{"id": "i1", "cluster_id": "g1", "goods_name": "泵"}],  # get(contract_item)
            [{"id": "g1", "representative_name": "泵"}],  # get_links -> goods_cluster
            [{"id": "g1", "representative_name": "泵"}],  # get(part_cluster match) — returns same-shape row
        ]
    )
    eng = QueryEngine(load_registry(), pg_connector=fake, ds_connector=fake)
    out = asyncio.run(eng.traverse_path("contract_item", "i1", "item_in_cluster.part_cluster_matches_goods_cluster"))
    assert out["primaryKey"] == "i1"
    assert out["via_item_in_cluster"]["primaryKey"] == "g1"
    assert "via_part_cluster_matches_goods_cluster" in out
