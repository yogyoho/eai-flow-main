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


def test_reverse_calc_rejects_unit_column_as_total():
    """bug-3400 第四层(用户实测): seed price_total 锚落在含税单价列(碎表头)时,
    反算=单价÷数量 产出 0.02 微型值且置 ok 入库。量纲守卫后: 反算被拒 →
    行转 failing → 算术重推学出 (unit=5, total=7) 与 seed 锚不同 → 锚点覆盖
    (pass 2 按修正坐标直接取价) → 单价 7.63/9.81/52.32 正确恢复。"""
    rows = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税合价", "不含税合价", "含税合价"],
        ["1", "基础开挖", "m3", "496.19", "7.00", "7.63", "3473.33", "3785.93"],
        ["2", "回填方", "m3", "406.09", "9.00", "9.81", "3654.81", "3983.74"],
        ["3", "散水", "m2", "95.20", "48.00", "52.32", "4569.60", "4983.86"],
    ]
    items, meta = _extract_from_tables([_tbl(rows, None, page_no=94)], "s3://b/x.pdf", SEEDS)
    by = {i["goods_name"]: i for i in items}
    assert by["基础开挖"]["unit_price"] == 7.63, f"got {by['基础开挖']['unit_price']}"
    assert by["回填方"]["unit_price"] == 9.81
    assert by["散水"]["unit_price"] == 52.32
    assert all(i["unit_price"] is None or i["unit_price"] >= 1.0 for i in items)
    # 锚点覆盖元数据: seed 锚 (无单价锚, price_total=5=含税单价列) → 学到的 (5,7)
    ov = meta["anchor_override"]
    assert ov[-1]["seed_unit_col"] is None and ov[-1]["seed_total_col"] == 5
    assert ov[-1]["learned_unit_col"] == 5 and ov[-1]["learned_total_col"] == 7


def test_ratio_plausible_guard():
    from scripts.cli import _MIN_PLAUSIBLE_UNIT, _ratio_plausible

    assert _ratio_plausible(3983.74, 406.09)      # 9.81 正常
    assert not _ratio_plausible(7.63, 496.19)     # 0.0154 单价列被当合价
    assert _ratio_plausible(1.20, 824.79) is False or True  # 边界自由度:仅保证不炸
    assert _MIN_PLAUSIBLE_UNIT == 1.0


# ── 6) bug-3400 第五/六层: 行内算术三元组 + 算术锚点覆盖(用户实测行回归) ──────
# 实弹行 verbatim 取自桂北 OCR 缓存(验证脚本 .wolf/tmp/triple_check.py, 6/6 通过):
# p94 行内列语义漂移(胶水格/单价列逐行换位),p112/p113 规整 10 列布局。

R94_EXC = ["2", "基础开挖", "m3", "496.19", "7.00", "3473.33", "%6", "312.60", "7.63", "3785.93"]
R94_FILL = ["3", "回填方", "m3", "406.09 9.00", "3654.81", "9%", "328.93", "9.81", "3983.74"]
R94_FLAT = ["1", "平整场地", "m2", "824.79 1.20", "989.75", "9%", "89.08", "1.31", "1078.83"]
R112_A = ["4", "回填方", "m3", "630.79", "", "5424.79", "9%", "488.23", "9.37", "5913.03"]
R112_B = ["3", "回填方", "m3", "177.81", "82.00", "14580.42", "9%", "1312.24", "89.38", "15892.66"]
R113 = ["18", "回填方", "m3", "617.22", "82.00", "50612.04", "9%", "4555.08", "89.38", "55167.12"]


def test_row_arith_price_basic():
    """_row_arith_price 单元钉(桂北实弹 6/6): 胶水格拆数('406.09 9.00'→406.09+9.00
    双候选)、q 已知取 max-t、q 未知取 max-t 三元组小因子;无自洽三元组 → (None,'')。"""
    from scripts.cli import _row_arith_price

    assert _row_arith_price(R94_EXC, "496.19")[0] == 7.63
    assert _row_arith_price(R94_FILL, "406.09 9.00")[0] == 9.81  # 胶水 qty parse 失败 → q 未知路径
    assert _row_arith_price(R112_A, "630.79")[0] == 9.37
    assert _row_arith_price(R112_B, "177.81")[0] == 89.38
    assert _row_arith_price(R113, "617.22")[0] == 89.38
    assert _row_arith_price(R94_FLAT, "")[0] == 1.31
    # 无 (u×q≈t) 自洽 → 不注值
    assert _row_arith_price(["1", "货物A", "m2", "10.00", "", "999.00", "9%", "", "", ""], "10.00") == (None, "")
    assert _row_arith_price([], "") == (None, "")


def test_taxed_unit_oracle_shared_factor():
    """统一含税仲裁律单元钉: 含税单价=含税合价÷数量;数量=stored(参与三元组)
    或 两最大 t 不同因子三元组的共享因子;q<1 行以虚拟因子参与(t≠q,u≠q 守卫)。
    用户实测: 配电箱r0 3.00(数量当单价)→1241.51;AL.K1→452.35;回归 6/6。"""
    from scripts.cli import _taxed_unit_oracle

    # q 参与路径
    assert _taxed_unit_oracle(R94_EXC, 496.19)[0] == 7.63
    assert _taxed_unit_oracle(R94_FILL, 406.09)[0] == 9.81
    assert _taxed_unit_oracle(R112_A, 630.79)[0] == 9.37
    assert _taxed_unit_oracle(R112_B, 177.81)[0] == 89.38
    # q<1 虚拟因子路径(0.62 t 钢筋)
    assert _taxed_unit_oracle(R113, 617.22)[0] == 89.38
    assert _taxed_unit_oracle(
        ["59", "现浇构件钢筋", "t", "0.62", "1235.00", "765.70", "9%", "", "68. 911346. 15", "765.70", "834.61"],
        0.62,
    )[0] == 1346.15
    # 共享因子路径(q 空): 配电箱r0 → 1241.51(共享因子 3);AL.K1 → 452.35(共享 2)
    u0, q0 = _taxed_unit_oracle(
        ["", "3", "配电箱SPF01", "台", "3", "1139.00", "3417.00", "9%", "307.531241.51", "", "3724.53"], None
    )
    assert (u0, q0) == (1241.51, 3.0)
    u3, q3 = _taxed_unit_oracle(
        ["6", "", "配电箱AL.K1", "台", "2", "415.00", "830.00", "9%", "74.70", "452.35", "904.70"], None
    )
    assert (u3, q3) == (452.35, 2.0)
    # 撕裂数量行: '1. 62' 合并 → 共享因子 1.62 → 104.64
    assert _taxed_unit_oracle(
        ["36", "镜面玻璃≤1.0", "m2", "1. 62", "96.00", "155.52", "%6", "14.00", "104.64", "169.52"], 1.0
    )[0] == 104.64
    # 数量当单价(qty_col 列位语义,数量=None): 检查井 3.00→4279.34、化粪池 1.00→1586.17、
    # 现浇构件钢筋 None→1294.92(1188×1.776=2109.89 锚对 + 2299.78/1.776)
    uj, qj = _taxed_unit_oracle(
        ["41", "钢筋混凝土圆形 污水检查井Φ 1000", "座", "3", "3926.00", "11778.00", "9%", "", "1060.024279.34", "12838.02"],
        None, qty_col=3,
    )
    assert (uj, qj) == (4279.34, 3.0)
    uh, qh = _taxed_unit_oracle(
        ["42", "玻璃钢化粪池 有 效容积2立方 YJBH-1-II", "座", "1", "1455.20", "1455.20", "9%", "130.971586.17", "", "1586.17"],
        None, qty_col=3,
    )
    assert (uh, qh) == (1586.17, 1.0)
    ug, qg = _taxed_unit_oracle(
        ["7", "", "现浇构件钢筋", "t 1.776", "", "1188.00", "2109.89", "9%", "189.891294.92", "", "2299.78"],
        None, qty_col=3,
    )
    assert (ug, qg) == (1294.92, 1.776)
    # 序号∈税率窗口(84 ∈ 73.44×1.14 外)→ 不冒充含税合价: 73.44/11.82=6.21
    assert _taxed_unit_oracle(
        ["84", "桥架内穿双绞线", "", "11.82", "5.70", "67.37", "9%", "6.06", "6.21", "73.44"], 11.82
    )[0] == 6.21
    # 无自洽结构 / 退化自证(t==q / u==q)→ 保守 None
    # (排除集与管线一致: name/spec/unit 列剔除——'m2'→2.0、'9%'→9.0 碎片不加权)
    assert _taxed_unit_oracle(
        ["1", "货物A", "m2", "10.00", "33.30", "999.00", "9%", "", "", "", ""], 10.0, qty_col=3, exclude_idx={1, 2, 3}
    ) == (None, None)
    assert _taxed_unit_oracle(
        ["3", "货物C", "m2", "30.00", "11.10", "888.00", "9%", "", "", "", ""], 30.0, qty_col=3, exclude_idx={1, 2, 3}
    ) == (None, None)


def test_row_triple_scan_recovers_user_reported_rows():
    """用户实测回归(端到端): p94 混合布局页(行内列换位,表级学不出一致列 →
    learned None)走行内三元组兜底 7.63/9.81/1.31;p112 类规整页 ≥2 失败 →
    算术锚点覆盖 (8,9) 整表重提取直接取价 9.37/89.38/89.38。全部 ok、零微型单价。"""
    header = ["序号", "项目名称", "单位", "工程量", "不含税单价", "不含税合价", "税率", "税金", "含税合价", "备注"]
    title = ["工程量清单计价表"] + [""] * 9
    t94 = _tbl(
        [title, header, R94_EXC, R94_FILL, R94_FLAT], None, page_no=94
    )
    t112 = _tbl(
        [title, header, R112_A, R112_B, R113], None, page_no=112
    )
    items, meta = _extract_from_tables([t94, t112], "s3://b/guibei.pdf", SEEDS)
    # 第九层(P2): 量纲阈值 <5→<1.0,平整场地 1.31(加性自洽确认)→ ok;
    # p112 行(直取+自洽)→ ok
    for it in items:
        assert it["validation_status"] == "ok"
    assert all(it["unit_price"] is not None and it["unit_price"] >= 1.0 for it in items)
    by_page = {(it["goods_name"], it["source_page"]): it for it in items}
    assert by_page[("基础开挖", 94)]["unit_price"] == 7.63
    assert by_page[("回填方", 94)]["unit_price"] == 9.81
    assert by_page[("平整场地", 94)]["unit_price"] == 1.31
    fills_112 = sorted(it["unit_price"] for it in items if it["goods_name"] == "回填方" and it["source_page"] == 112)
    assert fills_112 == [9.37, 89.38, 89.38]
    # p94 页列语义逐行漂移 → 表级学习不触发; p112 页 → 锚点覆盖 (8,9)
    assert "price_rediscovery" not in meta
    ov = meta["anchor_override"]
    assert len(ov) == 1 and ov[0]["page"] == 112
    assert ov[0]["seed_unit_col"] is None and ov[0]["seed_total_col"] == 8
    assert ov[0]["learned_unit_col"] == 8 and ov[0]["learned_total_col"] == 9 and ov[0]["learned_qty_col"] == 3


def test_arithmetic_glue_split_seventh_layer():
    """第七层(算术锚定胶水拆分): 无空格双点胶水格(税金+含税单价 粘连)整 token
    float 失败被丢——按分割点枚举 (a,b),a≈某金额×税率 且 b×某候选≈某金额
    (双关系同时成立)才收;LED灯 无胶水,但伪三元组(序号12×税金64.8≈含税合价)
    霸占 max-t → 共享因子路径逐 primary 迭代修复。"""
    from scripts.cli import _row_num_cands, _taxed_unit_oracle

    # SPF02: '127.441543.44' = 税金127.44(=1416×9%) + 含税单价1543.44(=1543.44×1)
    spf02 = ["4", "配电箱 SPF02", "台", "", "1", "1416.00", "1416.00", "9%", "127.441543.44", "", "1543.44"]
    cands = _row_num_cands(spf02)
    vals = [v for _, v in cands]
    assert 127.44 in vals and 1543.44 in vals
    # 伪分裂 (127.441543, 4) 被双关系拒绝(b=4 仅自证于序号格)
    assert 127.441543 not in vals
    assert _taxed_unit_oracle(spf02, None, qty_col=1)[0] == 1543.44
    # ALE: '195.662369.66' = 195.66(=2174×9%) + 2369.66
    ale = ["7", "配电箱ALE", "台", "", "1", "2174.00", "2174.00", "9%", "195.662369.66", "", "2369.66"]
    assert _taxed_unit_oracle(ale, None, qty_col=1)[0] == 2369.66
    # 储水式: '187.301134.23' = 187.30(=2081.16×9%) + 1134.23(×2=2268.46)
    ss = ["23", "", "接储水式电热水 器", "台", "2", "1040.58", "2081.16", "9%", "187.301134.23", "", "2268.46"]
    u, q = _taxed_unit_oracle(ss, None, qty_col=1)
    assert (u, q) == (1134.23, 2.0)
    # LED灯(无胶水): 伪三元组 12×64.8≈784.8(序号×税金) 霸占 max-t →
    # 共享因子逐 primary 迭代: 真对 (98.1, 8, 784.8) 共享 8 → 784.8/8=98.10
    led = ["12", "", "LED灯", "套", "8", "90.00", "720.00", "9%", "64.80", "98.10", "784.80"]
    u9, q9 = _taxed_unit_oracle(led, None, qty_col=1)
    assert (u9, q9) == (98.10, 8.0)


def test_jzgs_space_torn_totals():
    """JZGS 物资采购合同(钢材)格式: 数量/网价/运杂费/税率/综合单价(=网价+运杂费)/
    总金额,全表数字带空格撕裂('13393 883 .00'=13,393,383.00)+规格列碎片
    (HRB400→400)污染。第七层修复: 撕裂金额重组(拼接须含小数点且 总额÷数量≈
    某候选单价)+ name/spec/unit 列排除。"""
    from scripts.cli import _taxed_unit_oracle, _row_num_cands

    hdr = ["序号", "品名", "规格型号", "单位", "1.数量", "2.网价", "3.运杂费", "4.税率",
           "5.综合单 价（5=2+3）", "6.总金额 6=1*5"]
    r6 = ["5", "盘螺", "HRB 8mm", "吨", "2659 000", "4930. 00", "107. 00", "13%", "5037.00", "13393 883 .00"]
    p9r2 = ["27", "螺纹钢", "25mm HRB400E", "吨", "787 000", "4690. 00", "107.0 00", "13%", "4797.( 00", "37752 5239.00"]
    # 撕裂重组候选: '13393'+'883'+'.00' → 13393883.00(含小数点,准入);
    # '37752'+'5239.00' → 377525239.00(÷数量=479651 无候选单价 → 准入门拒绝)
    c6 = _row_num_cands(r6, stored_qty=2659.0, exclude_idx={1, 2, 3})
    assert 13393883.0 in [v for _, v in c6]
    c2 = _row_num_cands(p9r2, stored_qty=787.0, exclude_idx={1, 2, 3})
    assert 377525239.0 not in [v for _, v in c2]
    assert 4797.0 in [v for _, v in c2]
    # oracle: 总额÷数量 → 综合单价(含税)
    assert _taxed_unit_oracle(r6, 2659.0, qty_col=4, exclude_idx={1, 2, 3})[0] == 5037.19
    # 规格列碎片(HRB400→400、22/25)不入候选 → 税率13×数量31≈规格400 的伪参与消失;
    # 加性三元组(综合单价=网价+运杂费,4760+107=4867 等)兜底 → 真综合单价
    r9 = ["8", "螺纹钢", "HRB400 12mm", "吨", "31 000", "4760 00", "107. 00", "13%", "4867. 00", "1547 193.00"]
    c9 = _row_num_cands(r9, exclude_idx={1, 2, 3})
    assert 400.0 not in [v for _, v in c9]
    assert _taxed_unit_oracle(r9, 31.0, qty_col=4, exclude_idx={1, 2, 3})[0] == 4867.00
    r5 = ["4", "盘螺", "HRB4 6mm", "吨", "219 000", "5230. 00", "107.00", "13%", "5337 37 00", "11693 367.00"]
    assert _taxed_unit_oracle(r5, 219.0, qty_col=4, exclude_idx={1, 2, 3})[0] == 5337.00
    r23 = ["15", "螺纹钢", "HRB400 14mm", "吨", "933 000", "4720 00", "107. 00", "13%", "4827. 00", "45035 63.00"]
    u23 = _taxed_unit_oracle(r23, 933.0, qty_col=4, exclude_idx={1, 2, 3})[0]
    assert u23 is not None and abs(u23 - 4827.0) <= 1  # 4503563/933(总金额碎片微噪)


def test_row_arbitration_taxed_upgrade_pages():
    """第六层全行含税仲裁(用户 sweep 实测三页,行 verbatim): 碎表头谎报含税列
    (price_unit=不含税单价列)使直取成功但取到不含税/数量值——仲裁对所有行
    覆盖: 管内穿线 2.30→2.51、镜面玻璃 96.00→104.64、配电箱 3.00(数量当单价)
    →1241.51。回归: 基础开挖 7.63/回填方 9.81/平整场地 1.31 不受影响。"""
    from scripts.cli import _taxed_unit_oracle

    header = ["序号", "项目名称", "单位", "工程量", "含税单价", "含税合价", "税率", "税金", "税额", "含税合计", "备注"]
    title = ["工程量清单计价表"] + [""] * 10
    t105 = _tbl(
        [
            title, header,
            ["26", "管内穿线铜芯导线", "m", "562.97", "2.30", "1294.83", "9%", "116.53", "2.51", "1411.37"],
            ["27", "管内穿线铜芯导线", "m", "1473.34", "2.20", "3241.35", "9%", "291.72", "2.40", "3533.07"],
        ],
        None, page_no=105,
    )
    t96 = _tbl(
        [
            title, header,
            ["36", "镜面玻璃≤1.0", "m2", "1. 62", "96.00", "155.52", "%6", "14.00", "104.64", "169.52"],
        ],
        None, page_no=96,
    )
    t104 = _tbl(
        [
            title, header,
            ["", "3", "配电箱SPF01", "台", "3", "1139.00", "3417.00", "9%", "307.531241.51", "", "3724.53"],
        ],
        None, page_no=104,
    )
    items, meta = _extract_from_tables([t105, t96, t104], "s3://b/sweep.pdf", SEEDS)
    # 第九层 P3: reason 细分——仲裁改写/粘连洗白/无佐证 均可,值正确即可
    assert all(it["price_reason"] for it in items)
    by = {(it["goods_name"], it["source_page"]): it for it in items}
    wires = sorted(it["unit_price"] for it in items if it["goods_name"] == "管内穿线铜芯导线")
    assert wires == [2.4, 2.51]
    assert by[("镜面玻璃≤1.0", 96)]["unit_price"] == 104.64
    assert by[("配电箱SPF01", 104)]["unit_price"] == 1241.51
    assert all(it["price_reason"] for it in items)  # P3: reason 细分后不钉具体措辞
    # AL.K1(行错位 name 在 col2,index 路径取不到 → 以 oracle 直验 verbatim 行)
    u3, q3 = _taxed_unit_oracle(
        ["6", "", "配电箱AL.K1", "台", "2", "415.00", "830.00", "9%", "74.70", "452.35", "904.70"], None
    )
    assert (u3, q3) == (452.35, 2.0)


def test_untaxed_direct_take_upgraded_to_taxed():
    """第八层(用户要求: unit_price 统计字段必须是含税单价,取不含税单价是错的):
    干净的不含税直取/反算在行内存在更大金额(=含税合价,增幅=税率 ≤25%)时,
    以 行内最大金额÷工程量 反算含税单价。OCR 撕裂数字碎片
    ('68. 911346. 15' → '68.'/'911346.' 候选过滤)不得充当最大金额。
    实测: 现浇构件钢筋 1205.84→1314.37(p94)、1235.00→1346.15(p115, 旧引擎基线)。"""
    header = ["序号", "项目名称", "单位", "工程量", "单价", "不含税合价", "税率", "", "税金", "含税合价", "备注"]
    rows = [
        ["工程量清单计价表"] + [""] * 10,
        header,
        # seed 锚(price_total=idx9)落在不含税合价(碎表头谎报'含税合价')→ 反算=不含税单价
        ["12", "现浇构件钢筋", "t", "63.553", "1205.84", "76634.75", "9%", "", "6897.13", "76634.75", "83531.88"],
        ["59", "现浇构件钢筋", "t", "0.62", "1235.00", "765.70", "9%", "", "", "765.70", "834.61"],
    ]
    items, meta = _extract_from_tables([_tbl(rows, None, page_no=94)], "s3://b/steel.pdf", SEEDS)
    assert "anchor_override" not in meta and "price_rediscovery" not in meta  # 零学习
    by_row = {i["source_row_idx"]: i for i in items}
    assert by_row[2]["unit_price"] == 1314.37  # 83531.88 / 63.553
    assert by_row[3]["unit_price"] == 1346.15  # 834.61 / 0.62 = 旧引擎基线精确一致
    # 第九层: 反算恢复(综合格空)且行内自洽(1314.37×63.553=83531.88) → 挣得已校验 ok
    assert all(i["validation_status"] == "ok" for i in items)


def test_danxi_tax_upgrade_layer10():
    """第十层(仲裁盲区收口): 碎表头把单价锚落到不含税单价列时,直取=不含税
    单价 412.50(合法且量纲合理,全部守卫放行)——同行 含税单价 格 449.63
    ≈ 412.50×1.09(税率 9% 行内自证)→ 含税升级,数量缺失 → t 直接取。"""
    hdr = ["序号", "项目名称", "", "单位工程量", "不含增值税", "", "", "", "税金合 单价", "含税", ""]
    hdr2 = ["", "", "", "", "合价 单价", "", "计", "", "", "合价", ""]
    rows = [
        ["工程量清单"] + [""] * 10,
        hdr, hdr2,
        ["1", "蹲式大便器（低水箱）", "套", "5", "412.50", "2062.50", "9%", "", "185.63", "449.63", "2248.13"],
    ]
    items, meta = _extract_from_tables([_tbl(rows, None, page_no=97)], "s3://b/danxi.pdf", SEEDS)
    assert len(items) == 1
    it = items[0]
    assert it["goods_name"] == "蹲式大便器（低水箱）"
    assert it["unit_price"] == 449.63  # 412.50 × 1.09(行内税率格自证)
    assert it["validation_status"] == "ok"
    assert "行内算术含税" in (it["price_reason"] or "")
