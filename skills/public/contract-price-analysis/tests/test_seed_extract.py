"""extract_items_seed: 角色取值 + 分类行识别/传播。桂北实表结构合成回放。"""

from scripts.seed_library import DEFAULT_TABLE_SEEDS
from scripts.table_classifier import _roles_x_from_data, extract_items_seed, match_seed

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


def _bbox(xc, w=0.04):
    return [xc - w, 0.10, xc + w, 0.20]


def test_xband_path_handles_drifted_rows_and_category():
    """x-band 路径(production 主路径,Task 4 后唯一): 漂移行(多一个前导空cell)下
    取值与干净表基线一致,分类传播不丢。

    漂移的本质是数组下标移位而文本物理位置不变——bbox 跟着文本走(语义列),
    所以漂移行的 bbox 必须按内容所在列给 x,而非按下标。role x-band 由
    _roles_x_from_data 从数据 cell 取中位数,单行下标/内容错位被中位数吸收。"""
    dx = [0.04, 0.14, 0.28, 0.42, 0.58, 0.74, 0.90]
    rows = [
        ["序号", "项目名称", "单 位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["(一)", "建筑工程", "", "", "", "", ""],
        ["7", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
        ["", "14", "雨棚面砂浆防水", "m2", "30.70", "18.35", ""],  # 漂移: 前导空cell,含税单价/合价缺失
        ["", "屋面", "", "", "", "", ""],
        ["15", "涂膜防水屋面", "m2", "305.78", "57.14", "60.30", "18438.51"],
    ]
    clean = [_bbox(x) for x in dx]
    # 漂移行: cell0 多余空列(dummy@0.02,距 name band 0.12>tol 不占角色);
    # 其后 cell 依次回到 序号(0.04,非角色)/name/unit/qty/不含税 band;
    # 末位空 cell@0.98 距 price_total(0.90) 0.08>tol → 价格角色缺席。
    drifted = [_bbox(0.02), _bbox(0.04), _bbox(0.14), _bbox(0.28), _bbox(0.42), _bbox(0.58), _bbox(0.98)]
    bboxes = [clean, clean, clean, drifted, clean, clean]

    seed, roles, header_rows = match_seed(rows, [SEED])
    roles_x = _roles_x_from_data(rows, bboxes, roles, header_rows)
    assert roles_x is not None  # use_x 前提:x-band 真正参与取值

    items = extract_items_seed(rows, seed, roles, header_rows, bboxes, roles_x)
    names = [it["name"] for it in items]
    assert names == ["平整场地", "雨棚面砂浆防水", "涂膜防水屋面"]
    assert "屋面" not in names and "建筑工程" not in names  # 分类行仍不产 item
    # x-band 取值与干净表基线一致(items[0] 走完整 7 列布局)
    assert items[0]["qty_raw"] == "824.79"
    assert items[0]["price_unit_raw"] == "1.20"
    assert items[0]["price_total_raw"] == "989.75"
    assert items[0]["price_untaxed_raw"] == "1.07"
    # 漂移行按下标错 2 位,按 x 正确归位;价格漏读行保留空价(Task4 定夺)
    drift = items[1]
    assert drift["qty_raw"] == "30.70" and drift["unit"] == "m2"
    assert drift["price_unit_raw"] == "" and drift["price_total_raw"] == ""
    assert drift["price_untaxed_raw"] == "18.35"
    assert items[-1]["category"] == "屋面"  # 分类传播在 x 路径同样成立
