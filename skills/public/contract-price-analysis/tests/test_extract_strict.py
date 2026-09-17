"""严格 seed-only 管线: 命中提取/未匹配零提取+记录/续表继承/跨页分类续传/反算。"""

from types import SimpleNamespace

from scripts.cli import _extract_from_tables
from scripts.seed_library import DEFAULT_TABLE_SEEDS

SEEDS = DEFAULT_TABLE_SEEDS


def _tbl(rows, page_no=1, table_idx=0, conf=0.9):
    return SimpleNamespace(
        page_no=page_no, table_idx=table_idx, rows=rows, cell_bboxes=None,
        page_preview_b64="", mean_confidence=conf,
    )


def test_seed_hit_extracts_items_and_meta():
    tables = [_tbl([
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
        ["2", "现浇构件钢筋", "t", "63.55", "1131.55", "1205.84", "76631.13"],
    ])]
    items, meta = _extract_from_tables(tables, "s3://b/k.pdf", SEEDS)
    assert len(items) == 2
    assert items[0]["unit_price"] == 1.20          # seed price_unit → unit_price(统计)
    assert items[0]["price_untaxed"] == 1.07
    assert items[0]["category"] is None
    assert meta["goods_tables"] == 1
    assert meta["matched_seeds"] == {"工程量清单计价表": 1}
    assert meta["unmatched_tables"] == []


def test_unmatched_table_recorded_not_extracted():
    tables = [_tbl([
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
    ]), _tbl([
        ["编号", "事项", "说明", "标准"],       # 4列非价格表,无 seed 确认
        ["1", "进场", "三级教育", "合格"],
    ], page_no=3)]
    items, meta = _extract_from_tables(tables, "s3://b/k.pdf", SEEDS)
    assert len(items) == 1                              # 严格: 未匹配表零提取
    assert meta["unmatched_tables"][0]["page"] == 3
    assert meta["unmatched_tables"][0]["header"] == ["编号", "事项", "说明", "标准"]


def test_continuation_inherits_seed_roles():
    t1 = _tbl([
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
    ], page_no=4)
    t2 = _tbl([                                        # 续表: 无表头,列结构同
        ["2", "回填方", "m3", "406.09", "8.27", "9.00", "3654.81"],
    ], page_no=5)
    items, meta = _extract_from_tables([t1, t2], "s3://b/k.pdf", SEEDS)
    assert len(items) == 2
    assert meta["continuation_tables"] == 1
    assert items[1]["goods_name"] == "回填方"
    assert items[1]["unit_price"] == 9.00


def test_category_threads_across_pages():
    """跨页分类续传(修订I2): 表1尾部是屋面分类,续表页首行(下一分类行之前)的
    item 必须继承 屋面;新分类行出现后切换。
    注: t1 的钢筋行在屋面分类行之前 → category None(规划稿原断言
    ["屋面","屋面"] 漏计了该行,任何正确实现都会产出 3 个 item)。"""
    t1 = _tbl([
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["12", "现浇构件钢筋", "t", "63.55", "1131.55", "1205.84", "76631.13"],
        ["", "屋面", "", "", "", "", ""],
    ], page_no=4)
    t2 = _tbl([                                        # 续表: 无表头,屋面分类延续
        ["14", "雨棚面砂浆防水", "m2", "30.70", "18.35", "20.00", "614.00"],
        ["15", "涂膜防水屋面", "m2", "305.78", "57.14", "60.30", "18438.51"],
    ], page_no=5)
    items, meta = _extract_from_tables([t1, t2], "s3://b/k.pdf", SEEDS)
    assert meta["continuation_tables"] == 1
    assert [it["category"] for it in items] == [None, "屋面", "屋面"]


def test_category_threads_across_header_repeat_pages():
    """表头重复页(每页都 match_seed 命中)分类不丢: 页2 新分类行前继承页1尾部。"""
    t1 = _tbl([
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["", "屋面", "", "", "", "", ""],
        ["14", "雨棚面砂浆防水", "m2", "30.70", "18.35", "20.00", "614.00"],
    ], page_no=2)
    t2 = _tbl([                                        # 表头重复的页3
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["16", "屋面保温板", "m2", "790.80", "98.90", "106.57", "84274.66"],
    ], page_no=3)
    items, meta = _extract_from_tables([t1, t2], "s3://b/k.pdf", SEEDS)
    assert meta["goods_tables"] == 2
    assert items[-1]["category"] == "屋面"


def test_unmatched_breaks_category_chain():
    """未匹配表断开继承链: 其后的续表不再继承上一命中表的列。
    注: 断链后 t3 零提取,items 仅 t1 的雨棚 1 条(规划稿原写 2,与其自身
    注释「t3 不被当作 t1 的续表提取」矛盾)。"""
    t1 = _tbl([
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["", "屋面", "", "", "", "", ""],
        ["14", "雨棚面砂浆防水", "m2", "30.70", "18.35", "20.00", "614.00"],
    ], page_no=2)
    t2 = _tbl([["编号", "事项", "说明", "标准"], ["1", "进场", "三级教育", "合格"]], page_no=3)
    t3 = _tbl([["2", "回填方", "m3", "406.09", "8.27", "9.00", "3654.81"]], page_no=4)
    items, meta = _extract_from_tables([t1, t2, t3], "s3://b/k.pdf", SEEDS)
    assert len(items) == 1                    # 断链: t3 零提取
    assert items[0]["category"] == "屋面"
    assert meta["unmatched_tables"][0]["page"] == 3


def test_unit_price_reverse_calc_from_total():
    """含税单价缺失时 合价÷工程量 反算(seed price_total 列)。"""
    tables = [_tbl([
        ["序号", "项目名称", "单位", "工程量", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "989.75"],
    ])]
    items, _ = _extract_from_tables(tables, "s3://b/k.pdf", SEEDS)
    assert items[0]["unit_price"] is not None
    assert abs(items[0]["unit_price"] - 989.75 / 824.79) < 0.01
    assert items[0]["price_reason"] == "合价/工程量反算"


def test_generic_goods_price_label_without_seed_still_recorded():
    """I-0: 泛型词表判 goods_price(品名+单价)但无 seed 确认 → 必须进 unmatched_tables,
    不得 parsed+0提取静默零(设计 §9.6)。"""
    tables = [_tbl([
        ["序号", "品名", "规格", "单价"],
        ["1", "DN100阀门", "PN16", "350.00"],
    ])]
    items, meta = _extract_from_tables(tables, "s3://b/k.pdf", SEEDS)
    assert items == []
    assert meta["skipped"] == {"goods_price": 1}
    assert len(meta["unmatched_tables"]) == 1
    assert meta["unmatched_tables"][0]["header"] == ["序号", "品名", "规格", "单价"]
