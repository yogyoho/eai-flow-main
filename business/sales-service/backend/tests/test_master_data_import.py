from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.errors import SalesError
from app.routers.master_data import _canonical, _read_import_rows


def _workbook_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def test_read_csv_utf8_bom_and_chinese_aliases() -> None:
    raw = "\ufeff客户名称,区域,地址\n示例客户,NORTH,示例地址\n".encode()

    rows = _read_import_rows("customers.csv", raw)

    assert len(rows) == 1
    assert _canonical(rows[0]) == {
        "name": "示例客户",
        "region_code": "NORTH",
        "address": "示例地址",
    }


def test_read_csv_falls_back_to_gbk() -> None:
    raw = "客户名称,区域\nGBK 客户,NORTH\n".encode("gbk")

    rows = _read_import_rows("customers.csv", raw)

    assert _canonical(rows[0])["name"] == "GBK 客户"


def test_read_xlsx_converts_cells_and_preserves_row_positions() -> None:
    raw = _workbook_bytes(
        [
            ["客户名称", "区域", "地址"],
            ["Excel 客户", "NORTH", "示例地址"],
            [None, None, None],
            ["第二客户", "NORTH", None],
        ]
    )

    rows = _read_import_rows("customers.xlsx", raw)

    assert len(rows) == 3
    assert _canonical(rows[0])["name"] == "Excel 客户"
    assert not any(_canonical(rows[1]).values())
    assert _canonical(rows[2])["name"] == "第二客户"


def test_read_xlsx_converts_numbers_and_dates() -> None:
    raw = _workbook_bytes(
        [
            ["产品名称", "产品线", "型号"],
            ["采煤机", "智能综采", 12345],
            ["示范面", date(2026, 10, 24), datetime(2026, 10, 24, 9, 30)],
        ]
    )

    rows = _read_import_rows("products.xlsx", raw)

    assert rows[0]["型号"] == "12345"
    assert rows[1]["产品线"] == "2026-10-24"
    assert rows[1]["型号"] == "2026-10-24 09:30:00"


def test_read_xlsx_rejects_empty_header() -> None:
    raw = _workbook_bytes([[None, None], ["客户", "NORTH"]])

    with pytest.raises(SalesError) as exc:
        _read_import_rows("customers.xlsx", raw)

    assert exc.value.code == "SALES-400-IMPORT_HEADER"


def test_read_import_rows_rejects_unknown_and_legacy_formats() -> None:
    with pytest.raises(SalesError) as legacy:
        _read_import_rows("customers.xls", b"legacy")
    assert legacy.value.code == "SALES-400-IMPORT_FORMAT"

    with pytest.raises(SalesError) as unknown:
        _read_import_rows("customers.pdf", b"%PDF")
    assert unknown.value.code == "SALES-400-IMPORT_FORMAT"
