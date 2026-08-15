"""Tests for ontology row mapper."""

from decimal import Decimal

from app.extensions.ontology.engine.mapper import jsonable, select_columns, to_object
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
            PropertyDecl(name="goods_name", api_name="goodsName", type="string"),
            PropertyDecl(name="unit_price", api_name="unitPrice", type="decimal"),
            PropertyDecl(name="hidden_col", api_name="hiddenCol", type="string", hidden=True),
        ],
    )


def test_to_object_maps_api_names_and_omits_nulls_and_hidden():
    row = {"id": "abc", "goods_name": "泵", "unit_price": None, "hidden_col": "secret"}
    obj = to_object(_item_type(), row)
    assert obj["primaryKey"] == "abc"
    assert obj["properties"] == {"goodsName": "泵"}  # null omitted, hidden excluded


def test_to_object_converts_decimal():
    row = {"id": "x", "goods_name": "阀", "unit_price": Decimal("12.50"), "hidden_col": None}
    obj = to_object(_item_type(), row)
    assert obj["properties"]["unitPrice"] == 12.5


def test_select_columns_excludes_hidden():
    assert select_columns(_item_type()) == ["id", "goods_name", "unit_price"]


def test_jsonable_dates_and_decimals():
    from datetime import date

    assert jsonable(Decimal("0.5")) == 0.5
    assert jsonable(date(2026, 8, 14)) == "2026-08-14"
