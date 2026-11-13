"""批二十 M1-e PS 计算内核测试(EAI-CUSTOM 2026-11-13)——§2.2 硬约束:
明细表唯一事实源/Decimal 2dp HALF_UP/缺价留空/唯一形状=green_ctx 逐键相等。"""

from bid_write_exec_fixtures import green_ctx

from app.extensions.bid_write.generate.price_sheet import calc_price_sheet

_GREEN = green_ctx()["tender"]["tender.boq_items"]
_GREEN_NOTE = green_ctx()["products"]["price_sheet"]["note"]


def test_green_shape_exact():
    """夹具 boq+单价 → 产物与 executor green 夹具逐键相等(形状契约零漂移)。"""
    ps = calc_price_sheet(_GREEN, {"1.1": 800000, "1.2": "400000"}, price_mode="不含税", tax_rate=0.13, note=_GREEN_NOTE)
    assert ps == green_ctx()["products"]["price_sheet"], ps


def test_missing_unit_price_left_blank():
    """缺价行 amount=None 留空(§2.2 降级 D0 留空标注,禁止自动出价);总额只计有价行。"""
    ps = calc_price_sheet(_GREEN, {"1.1": 800000})
    assert ps["rows"][1]["unit_price"] is None and ps["rows"][1]["amount"] is None
    assert ps["rows"][0]["amount"] == 1600000
    assert ps["detail_total"] == 1600000
    assert ps["amount_cn"] == "壹佰陆拾万元整"


def test_decimal_half_up_two_dp():
    """中间 4 位落表 2 位 ROUND_HALF_UP:0.125→0.13(银行家舍入会得 0.12);999.999→1000.00。"""
    boq = [{"id": "1", "name": "a", "qty": 1, "unit": "项"}, {"id": "2", "name": "b", "qty": 3, "unit": "件"}]
    ps = calc_price_sheet(boq, {"1": "0.125", "2": "333.333"})
    assert ps["rows"][0]["amount"] == 0.13
    assert ps["rows"][1]["amount"] == 1000.00
    assert ps["detail_total"] == 1000.13


def test_row_order_stable_and_qty_passthrough():
    """行序=boq 序;qty/unit 原样透传(PS-002 数量一致面:生成器不改招标数量)。"""
    boq = [{"id": "9", "name": "x", "qty": 7, "unit": "台"}, {"id": "2", "name": "y", "qty": 1.5, "unit": "时"}]
    ps = calc_price_sheet(boq, {"9": 100, "2": 10})
    assert [r["id"] for r in ps["rows"]] == ["9", "2"]
    assert ps["rows"][0]["qty"] == 7 and ps["rows"][1]["qty"] == 1.5


def test_empty_boq_honest_zero():
    ps = calc_price_sheet([], {})
    assert ps["rows"] == [] and ps["detail_total"] == 0
    assert ps["amount_cn"] == "零元整"
