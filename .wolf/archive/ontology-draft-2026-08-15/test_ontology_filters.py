"""Tests for ontology filter compiler."""

import pytest

from app.extensions.ontology.engine.filters import compile_filter
from app.extensions.ontology.registry import AccessDecl, ObjectTypeDecl, PkDecl, PropertyDecl


def _item_type():
    return ObjectTypeDecl(
        api_name="contract_item",
        display_name="合同分项",
        description="d",
        domain="contract_price",
        access=AccessDecl(path="postgres_ext", table="cpa_items"),
        pk=PkDecl(column="id", api_name="id", type="string", immutable=True),
        properties=[
            PropertyDecl(name="goods_name", api_name="goodsName", type="string", filterable=True),
            PropertyDecl(name="unit_price", api_name="unitPrice", type="decimal", filterable=True),
        ],
    )


def test_compile_simple_eq():
    bind: dict = {}
    where = compile_filter(_item_type(), {"goodsName": {"eq": "泵"}}, bind)
    assert where == "goods_name = :p0"
    assert bind["p0"] == "泵"


def test_compile_and_nested():
    bind: dict = {}
    where = compile_filter(_item_type(), {"and": [{"goodsName": {"in": ["泵", "阀"]}}, {"unitPrice": {"gte": 100}}]}, bind)
    assert "goods_name IN" in where and "unit_price >=" in where
    assert " AND " in where and "{k}" not in where  # connector must be a real AND, not a template bug
    assert len(bind) == 3


def test_compile_unknown_field_raises():
    with pytest.raises(ValueError):
        compile_filter(_item_type(), {"nope": {"eq": 1}}, {})


def test_compile_between_and_is_null():
    bind: dict = {}
    where = compile_filter(_item_type(), {"unitPrice": {"between": [10, 99]}}, bind)
    assert where == "unit_price BETWEEN :p0 AND :p1"
    where2 = compile_filter(_item_type(), {"goodsName": {"is_null": True}}, {})
    assert where2 == "goods_name IS NULL"
