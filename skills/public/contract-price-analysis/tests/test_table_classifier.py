"""bbox-x column alignment tests (the ② root fix, hybrid form).

Hybrid: role IDENTIFICATION stays on the index path (_map_roles over the
collapsed header — robust even when rapid-table fragments the header); x is used
only to recover cells on drifted CONTINUATION pages, and role x-bands are read
from DATA cells (clean bboxes), not the header (the cause of the
含税合价/含税单价 mix-up). No live OCR — synthetic tables.
"""

from scripts.table_classifier import (
    _bboxes_usable,
    _roles_x_from_data,
    extract_items,
    looks_like_continuation,
)


def _bbox(xc, w=0.04):
    return [xc - w, 0.10, xc + w, 0.20]


# role x-bands as _roles_x_from_data would read them from data cells
_ROLES_X = {"name": 0.14, "unit": 0.28, "qty": 0.42, "price_untaxed": 0.58, "price_taxed": 0.74}
# index map _map_roles would derive from the header
_ROLES_IDX = {"name": 1, "unit": 2, "qty": 3, "price_untaxed": 4, "price_taxed": 5}


def test_roles_x_from_data_reads_column_x_from_data_cells():
    """role x-bands come from DATA cells, so 含税单价 (0.74) is NOT confused with
    含税合价 (0.90) even though a fragmented header might place them wrong."""
    header = ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"]
    dx = [0.04, 0.14, 0.28, 0.42, 0.58, 0.74, 0.90]
    d1 = ["1", "镀锌钢管DN100", "m", "100", "50.00", "54.50", "5450.00"]
    d2 = ["2", "弯头", "个", "10", "3.20", "3.49", "34.90"]
    rows = [header, d1, d2]
    bboxes = [[_bbox(x) for x in dx] for _ in range(3)]  # header x irrelevant; data x matters
    rx = _roles_x_from_data(rows, bboxes, _ROLES_IDX, header_rows=1)
    assert abs(rx["name"] - 0.14) < 0.01
    assert abs(rx["price_taxed"] - 0.74) < 0.01   # 含税单价, NOT 合价 at 0.90
    assert abs(rx["price_untaxed"] - 0.58) < 0.01


def test_bboxes_usable_flag():
    assert _bboxes_usable([["a"]], [[_bbox(0.1)]]) is True
    assert _bboxes_usable([["a"]], None) is False
    assert _bboxes_usable([["a", "b"]], [[[0, 0, 0, 0], [0, 0, 0, 0]]]) is False


def test_x_alignment_recovers_drifted_continuation_row_that_index_loses():
    """p106-style drift on a continuation page: an extra empty cell shifts
    indices, but inherited role x-bands keep each role on the right cell. Index
    path loses the name (empty → row skipped); x path recovers name + correct
    taxed 单价 (54.50, not untaxed 50.00 nor 合价 5450)."""
    drifted_text = ["1", "", "镀锌钢管DN100", "m", "100", "50.00", "54.50", "5450.00"]
    drifted_x = [0.04, 0.09, 0.14, 0.28, 0.42, 0.58, 0.74, 0.90]
    rows = [drifted_text]
    bboxes = [[_bbox(x) for x in drifted_x]]

    # x path (continuation: roles_x inherited from goods page)
    items_x = extract_items(rows, _ROLES_IDX, header_rows=0, cell_bboxes=bboxes, roles_x=_ROLES_X)
    assert len(items_x) == 1
    assert items_x[0]["name"] == "镀锌钢管DN100"
    assert items_x[0]["price_taxed_raw"] == "54.50"
    assert items_x[0]["qty_raw"] == "100"

    # index path (no bbox) → name_col=1 is the empty drift cell → row SKIPPED
    assert extract_items(rows, _ROLES_IDX, header_rows=0) == []


def test_x_alignment_detects_drifted_continuation_page():
    """looks_like_continuation x-based: a drifted headerless page (name cell at
    the inherited name x-band) is detected; index-based (empty name_col) misses
    it — the p106 'one drifted page orphans the rest' bug."""
    cont_text = [["45", "", "钢管埋地敷", "m", "80.60", "", "", "1612.00", "1757.08"]]
    cont_x = [0.04, 0.09, 0.14, 0.28, 0.42, 0.55, 0.66, 0.74, 0.90]
    cont_bbox = [[_bbox(x) for x in cont_x]]

    assert looks_like_continuation(cont_text, _ROLES_IDX, goods_col_count=9,
                                   cell_bboxes=cont_bbox, roles_x=_ROLES_X) is True
    assert looks_like_continuation(cont_text, _ROLES_IDX, goods_col_count=9) is False
