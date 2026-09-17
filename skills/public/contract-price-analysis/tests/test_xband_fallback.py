"""bug-3400: 种子路径逐行 x→index 回退 + 合计行守卫。

fixture 钉在桂北 OCR 缓存实弹行(oracle: .wolf/tmp/cpa-acceptance-runbook.md §9.2 取证):
p115 row18 = ['59','现浇构件钢筋','t','0.62','1235.00','765.70','9%','','68. 911346. 15','834.61']
  - 生产 x-band 路径把粘连格 '68. 911346. 15'(税金68.91+单价1346.15 OCR黏连)映射进
    price_total → validate 失败 → 反算失败 → 行被当 price-less 丢弃;
  - 关掉 roles_x 重放同一行: price_total='834.61' → 反算 834.61/0.62=1346.15
    = 旧引擎基线单价精确一致 ⇒ 列号映射对该行是对的。
哲学者注: x-band 对大多数行是对的(修复过真实漂移缺陷),回退只对「该行 x 映射
完全无可用价格、而行内有价格数字信号」逐行触发,全局 x-band 行为不变。
"""

from types import SimpleNamespace

from scripts.cli import _extract_from_tables
from scripts.seed_library import DEFAULT_TABLE_SEEDS
from scripts.table_classifier import (
    _roles_x_from_data,
    _row_cells_by_x,
    extract_items_seed,
    match_seed,
)

SEEDS = DEFAULT_TABLE_SEEDS
SEED = next(s for s in SEEDS if s["id"] == "gcl-qd")

# 与生产 roles 形状一致(gcl-qd 命中: name/qty/price_total,price_total 落在「含税合价」列;
# 12 列布局,含税合价在 idx9——真实 p94/p115 的 price_total 种子列就是它的右侧邻列)
COL_X = [0.05, 0.20, 0.30, 0.38, 0.46, 0.54, 0.60, 0.64, 0.67, 0.7264, 0.82]

TITLE_ROW = ["工程量清单计价表", "", "", "", "", "", "", "", "", "", ""]
HEADER_ROW = ["序号", "项目名称", "单位", "工程量", "不含税价", "不含税合价", "税率", "", "税金", "含税合价", "备注"]


def _bb(xc, w=0.025):
    return [xc - w, 0.10, xc + w, 0.20]


def _clean_bbox_row():
    return [_bb(x) for x in COL_X]


# t1: seed 命中表(roles_x 供体)。干净数据行,x 取值 = 列号取值。
T1_ROWS = [
    TITLE_ROW,
    HEADER_ROW,
    ["12", "现浇构件钢筋", "t", "63.553", "1205.84", "76634.75", "9%", "", "6897.13", "83531.88", ""],
    ["5", "多孔砖墙", "m3", "210.86", "511.00", "107749.46", "9%", "", "9697.45", "117446.91", ""],
]
T1_BBOXES = [None, None, _clean_bbox_row(), _clean_bbox_row()]

# t2: 续表(production p115 形状)。row0=分类行,row1=实弹故障行。
T2_ROWS = [
    ["", "钢筋工程", "", "", "", "", "", "", "", "", ""],
    ["59", "现浇构件钢筋", "t", "0.62", "1235.00", "765.70", "9%", "", "68. 911346. 15", "834.61", ""],
]
# 故障行: 粘连格 bbox 正落在 price_total 带上(dist≈0 抢占),真含税合价 '834.61'
# 的 bbox 远离所有带(dist>tol → 缺席)——精确复刻生产 x 映射结果。
T2_BBOXES = [
    _clean_bbox_row(),
    [
        _bb(0.05), _bb(0.20), _bb(0.30), _bb(0.38), _bb(0.46),
        _bb(0.54), _bb(0.60), _bb(0.64), _bb(0.7264), _bb(0.88), _bb(0.82),
    ],
]


def _tbl(rows, bboxes, page_no):
    return SimpleNamespace(
        page_no=page_no, table_idx=0, rows=rows, cell_bboxes=bboxes,
        page_preview_b64="", mean_confidence=0.9,
    )


def _fixture_tables():
    return [_tbl(T1_ROWS, T1_BBOXES, page_no=94), _tbl(T2_ROWS, T2_BBOXES, page_no=115)]


# ── 1) 逐行回退: 单元级 ────────────────────────────────────────────────────


def _p115_raw():
    roles_x = {"name": COL_X[1], "unit": COL_X[2], "qty": COL_X[3], "price_total": COL_X[9]}
    rows = [
        T2_ROWS[0],
        T2_ROWS[1],
    ]
    bboxes = T2_BBOXES
    roles = {"name": 1, "unit": 2, "qty": 3, "price_total": 9}
    return extract_items_seed(rows, SEED, roles, 0, bboxes, roles_x)


def test_p115_row_x_path_reproduces_production_glue():
    """缺陷形状 pin(映射层): x-band 对该行的映射确为粘连格原串——回退修复的是
    取值层,映射层缺陷形状必须保持可见(防有人误改 bbox 映射语义)。"""
    from scripts.table_classifier import _row_cells_by_x

    cells = _row_cells_by_x(
        T2_ROWS[1],
        T2_BBOXES[1],
        {"name": COL_X[1], "unit": COL_X[2], "qty": COL_X[3], "price_total": COL_X[9]},
    )
    assert cells["price_total"] == "68. 911346. 15"
    assert cells["qty"] == "0.62"
    assert cells["name"] == "现浇构件钢筋"


def test_p115_row_recovers_via_index_fallback():
    """回退后: 同一行按 seed 列号重映射 → price_total='834.61'(finalize 反算出基线价)。"""
    raw = _p115_raw()
    it = next(r for r in raw if r["name"] == "现浇构件钢筋")
    assert it["price_total_raw"] == "834.61"
    assert it["qty_raw"] == "0.62"
    assert it["name"] == "现浇构件钢筋"


def test_p115_row_survives_end_to_end_at_baseline_price():
    """端到端(生产管线): t1 命中 + t2 续表继承 → 该行存活,反算单价 = 旧基线 1346.15。"""
    items, meta = _extract_from_tables(_fixture_tables(), "s3://b/guibei.pdf", SEEDS)
    names = [it["goods_name"] for it in items]
    assert meta["continuation_tables"] == 1
    assert names.count("现浇构件钢筋") == 2  # t1 干净行 + t2 回退救回行
    rescued = [it for it in items if it["source_page"] == 115]
    assert len(rescued) == 1
    assert rescued[0]["category"] == "钢筋工程"
    assert rescued[0]["quantity"] == 0.62
    assert rescued[0]["unit_price"] == 1346.15  # 834.61 / 0.62 = 旧基线精确一致
    assert rescued[0]["price_reason"] == "合价/工程量反算"


# ── 2) 全局 x-band 行为不变(不许被回退语义波及) ─────────────────────────────


def test_x_path_kept_when_price_usable():
    """x 映射已有可用价格 → 决不回退(roles_x 主路径语义不变)。构造行:
    qty/合价经 x 正确归位(可用)而 列号 price_total 落在空列——
    若回退误触发,price_total 会被列号空串覆盖。"""
    rows = [
        ["", "平整场地", "m2", "824.79", "", "", "9%", "", "989.75", "", ""],
    ]
    # '989.75' 在 idx8 但 bbox 正落 price_total 带;x 正确取值,列号(idx9)为空
    bboxes = [
        [_bb(0.05), _bb(0.20), _bb(0.30), _bb(0.38), _bb(0.46), _bb(0.54),
         _bb(0.60), _bb(0.64), _bb(0.7264), _bb(0.88), _bb(0.82)],
    ]
    roles = {"name": 1, "unit": 2, "qty": 3, "price_total": 9}
    roles_x = {"name": COL_X[1], "unit": COL_X[2], "qty": COL_X[3], "price_total": COL_X[9]}
    items = extract_items_seed(rows, SEED, roles, 0, bboxes, roles_x)
    assert len(items) == 1
    assert items[0]["qty_raw"] == "824.79"
    assert items[0]["price_total_raw"] == "989.75"  # x 取值保留,未被列号空串覆盖


def test_x_path_not_downgraded_when_index_empty():
    """x 取到合价但工程量缺席(平整场地 p94 实况: 反算不成)且列号映射同为空 →
    不得用「更差的」列号格覆盖 x 格(回退只许换到更好的映射,不许降级)。"""
    rows = [
        ["", "平整场地", "m2", "", "824.79 1.20", "", "9%", "", "89.08", "1.31", "1078.83"],
    ]
    # x: price_total 带最近 = '1.31'(可用但无 qty,反算不成);列号 idx9 同为 '1.31'
    bboxes = [_clean_bbox_row()]
    roles = {"name": 1, "unit": 2, "qty": 3, "price_total": 9}
    roles_x = {"name": COL_X[1], "unit": COL_X[2], "qty": COL_X[3], "price_total": COL_X[9]}
    items = extract_items_seed(rows, SEED, roles, 0, bboxes, roles_x)
    assert len(items) == 1
    assert items[0]["price_total_raw"] == "1.31"  # x 取值保留


def test_roles_x_derivation_unchanged():
    """_roles_x_from_data 供体表(干净行)派生带不受回退改动影响。"""
    seed, roles, header_rows = match_seed(T1_ROWS, SEEDS)
    roles_x = _roles_x_from_data(T1_ROWS, T1_BBOXES, roles, header_rows)
    assert roles_x is not None
    assert abs(roles_x["price_total"] - COL_X[9]) < 1e-9
    assert abs(roles_x["name"] - COL_X[1]) < 1e-9


# ── 3) 分类行安全 pin: 无价格数字信号的行不得回退 ────────────────────────────


def test_category_row_without_price_signal_not_remapped():
    """分类行 pin: x 映射下无任何价格/工程量数字 → 不得触发回退(列号重映射会
    把错位数字格捡进价格角色,把分类行变成垃圾 item 并污染分类上下文)。"""
    rows = [
        # x: name='钢筋工程',价格/工程量全空 → 分类行;列号: qty='12',price_total='30.5' 可用
        ["", "钢筋工程", "", "12", "", "", "", "", "", "30.5", ""],
        ["60", "预埋铁件", "kg", "50.00", "5.80", "", "9%", "", "0.52", "6.32", ""],
    ]
    bboxes = [
        # '12'@0.60 / '30.5'@0.05 都远离 qty(0.38)/price_total(0.7264) 带 → x 缺席
        [_bb(0.05), _bb(0.20), _bb(0.30), _bb(0.60), _bb(0.46), _bb(0.54),
         _bb(0.60), _bb(0.64), _bb(0.67), _bb(0.05), _bb(0.82)],
        _clean_bbox_row(),
    ]
    roles = {"name": 1, "unit": 2, "qty": 3, "price_total": 9}
    roles_x = {"name": COL_X[1], "unit": COL_X[2], "qty": COL_X[3], "price_total": COL_X[9]}
    items = extract_items_seed(rows, SEED, roles, 0, bboxes, roles_x)
    assert [it["name"] for it in items] == ["预埋铁件"]  # 分类行未变 item
    assert items[0]["category"] == "钢筋工程"  # 分类上下文未被污染


# ── 4) 合计行守卫: 任一映射格命中跳过集 → 整行跳过 ───────────────────────────


def test_totals_label_in_nonname_cell_skipped_x_path():
    """x 路径: 「合计」标签格落到非名称列(此处 unit),名称列捡到数字——
    旧行为: item 泄漏且被 cli 烂行改名救成 '合计'(补充协议 F7 泄漏形状);
    新守卫: 任一映射格命中跳过集 → 整行跳过。"""
    rows = [
        ["合计", "511.00", "", "3.5", "", "", "", "", "", "83531.88", ""],
    ]
    bboxes = [
        # '合计'@0.30 落 unit 带,'511.00'@0.20 落 name 带,'3.5'@0.38 落 qty,合价在带内
        [_bb(0.30), _bb(0.20), _bb(0.46), _bb(0.38), _bb(0.46), _bb(0.54),
         _bb(0.60), _bb(0.64), _bb(0.67), _bb(0.7264), _bb(0.82)],
    ]
    roles = {"name": 1, "unit": 2, "qty": 3, "price_total": 9}
    roles_x = {"name": COL_X[1], "unit": COL_X[2], "qty": COL_X[3], "price_total": COL_X[9]}
    items = extract_items_seed(rows, SEED, roles, 0, bboxes, roles_x)
    assert items == []


def test_totals_label_in_nonname_cell_skipped_index_path():
    """列号路径同守卫(此前只查名称格): unit='合计' → 整行跳过。"""
    rows = [
        ["合计", "511.00", "合计", "3.5", "", "", "", "", "", "83531.88", ""],
    ]
    roles = {"name": 1, "unit": 2, "qty": 3, "price_total": 9}
    items = extract_items_seed(rows, SEED, roles, 0)
    assert items == []


def test_totals_leak_end_to_end():
    """端到端: 合计行不得以任何名字进 items(旧路径会被 ragged-fix 改名泄漏)。"""
    t1 = _tbl(T1_ROWS, T1_BBOXES, page_no=94)
    t2 = _tbl(
        T2_ROWS + [["合计", "511.00", "", "3.5", "", "", "", "", "", "83531.88", ""]],
        T2_BBOXES + [[
            _bb(0.30), _bb(0.20), _bb(0.46), _bb(0.38), _bb(0.46), _bb(0.54),
            _bb(0.60), _bb(0.64), _bb(0.67), _bb(0.7264), _bb(0.82),
        ]],
        page_no=115,
    )
    items, _meta = _extract_from_tables([t1, t2], "s3://b/guibei.pdf", SEEDS)
    assert not any(it["goods_name"] in ("合计", "小计", "总计", "511.00") for it in items)


# ── 5) bug-3400 二阶段: 列带语义化 ──────────────────────────────────────────
# 取证(.wolf/tmp/cpa-acceptance-runbook.md §9.2 复验): p94 表种子 price_total 列
# (idx9)数据行大多为空串——空格参与中位数把带钉在空列上;真含税合价在 idx10。
# row16 实弹: idx9 空格 dist 0.004 抢占 price_total 带, '83531.88'(idx10, dist 0.053)
# 被挡在门外 → 行 price-less 丢弃(多孔砖墙/平整场地同类)。


def test_roles_x_omits_role_with_only_empty_cells():
    """空单元格不定义列带: 某角色扫描窗口内数据格全空 → 该角色从 roles_x 省略
    (迫使上层回退列号路径,而非用空格位置冒充语义带)。"""
    rows = [
        ["1", "货物A", "", "", "", "", "", "", "", "", ""],
        ["2", "货物B", "", "", "", "", "", "", "", "", ""],
    ]
    bboxes = [_clean_bbox_row(), _clean_bbox_row()]
    roles = {"name": 1, "qty": 3, "price_total": 9}
    roles_x = _roles_x_from_data(rows, bboxes, roles, header_rows=0)
    assert roles_x is not None
    assert "name" in roles_x
    assert "qty" not in roles_x and "price_total" not in roles_x


def test_two_pass_prefers_nonempty_cell_in_band():
    """两段式认领: 角色带内最近格是空格(dist 0.004)但有非空格(dist 0.055<tol)
    → 取非空值(旧实现被空格抢占产出空值——纯信息损失)。"""
    row = ["", "", "", "", "", "", "", "", "83531.88", ""]
    bboxes = [
        _bb(0.05), _bb(0.10), _bb(0.20), _bb(0.30), _bb(0.40),
        _bb(0.50), _bb(0.60), _bb(0.64), _bb(0.6714), _bb(0.7224),
    ]
    cells = _row_cells_by_x(row, bboxes, {"price_total": 0.7264})
    assert cells["price_total"] == "83531.88"


def test_role_with_only_empty_cell_in_band_stays_empty():
    """带内只有空格 → 角色仍空(pass2 认领空格,不发明值)。"""
    row = ["", "", "", "", "", "", "", "", "", "", ""]
    cells = _row_cells_by_x(row, _clean_bbox_row(), {"name": COL_X[1], "qty": COL_X[3], "price_total": COL_X[9]})
    assert cells.get("name", "") == ""
    assert cells.get("qty", "") == ""
    assert cells.get("price_total", "") == ""


def test_p94_row_price_reaches_real_total_via_two_pass():
    """实弹 p94 row16(桂北 OCR 缓存): 空格 idx9(dist 0.004)曾抢占 price_total 带,
    真合价 '83531.88'(idx10, dist 0.053<tol)被挡 → 两段式后非空优先取真值,
    反算可得旧基线单价 1314.37(83531.88/63.553)。"""
    row = [
        "12", "现浇构件钢筋", "t", "63.553", "1205.84", "76634.75",
        "9%", "", "6897.131314.37", "", "83531.88",
    ]
    bboxes = [
        [0.1491, 0.7011, 0.1988, 0.7444], [0.2079, 0.7017, 0.3106, 0.7415],
        [0.2928, 0.7030, 0.3533, 0.7424], [0.3536, 0.7034, 0.4056, 0.7431],
        [0.4116, 0.7021, 0.4853, 0.7418], [0.4776, 0.7016, 0.5611, 0.7409],
        [0.5591, 0.7017, 0.6192, 0.7407], [0.6042, 0.7030, 0.6575, 0.7419],
        [0.6413, 0.7036, 0.6980, 0.7420], [0.6898, 0.7034, 0.7547, 0.7424],
        [0.7318, 0.7052, 0.8267, 0.7455],
    ]
    cells = _row_cells_by_x(row, bboxes, {"name": 0.26416, "qty": 0.38110, "price_total": 0.72642})
    assert cells["name"] == "现浇构件钢筋"
    assert cells["qty"] == "63.553"
    assert cells["price_total"] == "83531.88"  # 非空优先: idx10(dist 0.053) 胜 idx9 空格(dist 0.004)
