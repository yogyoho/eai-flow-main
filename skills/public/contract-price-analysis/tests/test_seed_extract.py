"""extract_items_seed: 角色取值 + 分类行识别/传播。桂北实表结构合成回放。"""

from scripts.seed_library import DEFAULT_TABLE_SEEDS
from scripts.table_classifier import extract_items_seed, match_seed

SEED = next(s for s in DEFAULT_TABLE_SEEDS if s["id"] == "gcl-qd")

# 桂北 p2 实测结构: 标题/表头/分类行(一)建筑工程/数据.../分类行'屋面'/数据
ROWS = [
    ["工程量清单计价表", "", "", "", "", "", ""],
    ["序号", "项目名称", "单 位", "工程量", "不含税单价", "含税单价", "含税合价"],
    ["(一)", "建筑工程", "", "", "", "", ""],
    ["7", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
    ["12", "现浇构件钢筋", "t", "63.55", "1131.55", "1205.84", "76631.13"],
    ["", "屋面", "", "", "", "", ""],
    ["14", "雨棚面砂浆防水", "m2", "30.70", "18.35", "20.00", "614.00"],
]


def _extract():
    seed, roles, header_rows = match_seed(ROWS, [SEED])
    return extract_items_seed(ROWS, seed, roles, header_rows)


def test_category_rows_become_context_not_items():
    items = _extract()
    names = [it["name"] for it in items]
    assert "建筑工程" not in names and "屋面" not in names  # 分类行不产 item
    assert [it["name"] for it in items] == ["平整场地", "现浇构件钢筋", "雨棚面砂浆防水"]


def test_category_propagates_to_following_items():
    items = _extract()
    assert items[0]["category"] == "建筑工程"
    assert items[1]["category"] == "建筑工程"
    assert items[2]["category"] == "屋面"


def test_prices_mapped_to_seed_roles():
    items = _extract()
    assert items[0]["price_unit_raw"] == "1.20"
    assert items[0]["price_total_raw"] == "989.75"
    assert items[0]["price_untaxed_raw"] == "1.07"
    assert items[0]["qty_raw"] == "824.79"
