"""Tests for the three parser modes + dispatch."""

from scripts.parser import parse_chunks
from scripts.parser.list_parser import ListParser
from scripts.parser.table_parser import TableParser


def test_table_parser_extracts_rows():
    chunk = (
        "| 序号 | 货物名称 | 规格型号 | 技术参数 | 数量 | 单位 | 单价(元) |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 1 | 高压开关柜 | KYN28-12 | 电压10kV 电流630A | 2 | 台 | 120000 |\n"
        "| 2 | 变压器 | SCB13 | 容量1000kVA | 1 | 台 | 85000 |"
    )
    items = TableParser().parse(chunk)
    assert len(items) == 2
    assert items[0].goods_name == "高压开关柜"
    assert items[0].unit_price == 120000.0
    assert items[0].spec_model == "KYN28-12"
    assert items[0].tech_params["电压"] == "10kV"
    assert items[0].quantity == 2.0
    assert items[0].unit == "台"
    assert items[1].goods_name == "变压器"
    assert items[1].unit_price == 85000.0


def test_table_parser_skips_separator_and_total_rows():
    chunk = (
        "| 货物名称 | 单价 |\n|---|---|\n| 合计 | 999 |\n| 开关柜 | 100 |"
    )
    items = TableParser().parse(chunk)
    assert [i.goods_name for i in items] == ["开关柜"]


def test_list_parser_extracts_lines():
    chunk = (
        "1. 高压开关柜 KYN28-12，电压10kV，数量2台，单价120000元\n"
        "2. 变压器 SCB13，容量1000kVA，数量1台，单价85000元"
    )
    items = ListParser().parse(chunk)
    assert len(items) == 2
    assert items[0].goods_name == "高压开关柜"
    assert items[0].unit_price == 120000.0
    assert items[1].goods_name == "变压器"
    assert items[1].unit_price == 85000.0


def test_parse_chunks_dispatches_by_mode_table():
    chunk = "| 货物名称 | 单价(元) |\n|---|---|\n| 开关柜 | 100 |"
    items = parse_chunks([chunk], mode="table")
    assert len(items) == 1
    assert items[0].goods_name == "开关柜"
    assert items[0].unit_price == 100.0


def test_parse_chunks_dispatches_by_mode_list():
    chunk = "1. 水泵 IS100，单价5000元"
    items = parse_chunks([chunk], mode="list")
    assert len(items) == 1
    assert items[0].goods_name == "水泵"
    assert items[0].unit_price == 5000.0


def test_parse_chunks_mixed_falls_back_to_list():
    # No table markers → mixed parser should use the list parser.
    chunk = "1. 阀门 DN100，单价1200元"
    items = parse_chunks([chunk], mode="mixed")
    assert len(items) == 1
    assert items[0].goods_name == "阀门"
