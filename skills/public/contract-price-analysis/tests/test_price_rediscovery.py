"""bug-3400 终轮: 表级算术价列重推(单价×工程量≈合价 ±2%)+ 单失败行回退。

fixture 数值全部取自桂北 OCR 缓存 p94 实弹行(oracle: .wolf/tmp/cpa-acceptance-runbook.md):
- 平整场地 row5  = ['1','平整场地','m2','','824.79 1.20','989.75','9%','','89.08','1.31','1078.83']
- 多孔砖墙 row9  = ['5','多孔砖墙','m3','210.86','511.00','107749.46','9%','','9697.45556.99','','117446.91']
- 现浇构件钢筋 r16 = ['12','现浇构件钢筋','t','63.553','1205.84','76634.75','9%','','6897.131314.37','','83531.88']
p94 种子 price_total 列(idx9)数据行大多为空、真含税合价在 idx10(右邻列);但含税对
(单价,含税合价)差 9% 增值税,±2% 一致性门只可能学到不含税对 (不含税单价,不含税合价)。
触发门槛: 表内 ≥2 行价格双失败才学习(健康表零触发);失败==2 时要求一致性 ≥60% 数据行。
"""

from types import SimpleNamespace

from scripts.cli import _extract_from_tables
from scripts.seed_library import DEFAULT_TABLE_SEEDS

SEEDS = DEFAULT_TABLE_SEEDS

# 表头与真实 p94 等价: 折叠后种子角色 = {name:1, unit:2, qty:3, price_total:9}
# (idx4 用「单价」而非「不含税单价」——否则 price_untaxed 角色被映射,行经不含税价存活,不复现失败)
HEADER = ["序号", "项目名称", "单位", "工程量", "单价", "不含税合价", "税率", "", "税金", "含税合价", "备注"]

# p94 形状: 种子 price_total 列(idx9)数据行空/错值 → 全部行价格双失败
P94_ROWS = [
    ["工程量清单计价表"] + [""] * 10,
    HEADER,
    ["1", "平整场地", "m2", "", "824.79 1.20", "989.75", "9%", "", "89.08", "1.31", "1078.83"],
    ["2", "挖沟槽土方", "m3", "120.50", "45.00", "5422.50", "9%", "", "487.03", "", "5909.53"],
    ["3", "灰土垫层", "m3", "88.00", "130.00", "11440.00", "9%", "", "1029.60", "", "12469.60"],
    ["4", "C30混凝土", "m3", "56.20", "410.00", "23042.00", "9%", "", "2073.78", "", "25115.78"],
    ["5", "多孔砖墙", "m3", "210.86", "511.00", "107749.46", "9%", "", "9697.45556.99", "", "117446.91"],
    ["6", "钢筋", "t", "2.50", "4000.00", "10000.00", "9%", "", "900.00", "", "10900.00"],
    ["12", "现浇构件钢筋", "t", "63.553", "1205.84", "76634.75", "9%", "", "6897.131314.37", "", "83531.88"],
]


def _tbl(rows, page_no=94):
    return SimpleNamespace(
        page_no=page_no, table_idx=0, rows=rows, cell_bboxes=None,
        page_preview_b64="", mean_confidence=0.9,
    )


def _by_name(items):
    return {it["goods_name"]: it for it in items}


def test_stage1_learns_untaxed_pair_and_recovers_failing_rows():
    """≥2 失败行 → 学到 (unit=不含税单价, total=不含税合价, qty=工程量);学到的列
    与 seed 锚不同 → 算术锚点覆盖: 整表按修正坐标重提取。第七层语义: failing 行
    行内算术(三元组+max-t=含税合价)优先于学到的列直接取价——统计主字段是含税
    单价,行内锚对合价之上有更大金额(=含税合价)时反算之,不取不含税列
    (oracle: .wolf/tmp/cpa-acceptance-runbook.md §9.2: 多孔砖墙 556.99、
    现浇构件钢筋 1314.37、平整场地 1.31)。"""
    items, meta = _extract_from_tables([_tbl(P94_ROWS)], "s3://b/guibei.pdf", SEEDS)
    got = _by_name(items)
    assert meta["goods_tables"] == 1
    # 覆盖元数据(additive key): seed 锚 (无单价锚, price_total=9) → 学到的 (4,5,3)
    assert "price_rediscovery" not in meta  # 键迁移: 覆盖发生时不记行级重推
    ov = meta["anchor_override"]
    assert ov[-1]["seed_unit_col"] is None and ov[-1]["seed_total_col"] == 9
    assert ov[-1]["learned_unit_col"] == 4 and ov[-1]["learned_total_col"] == 5 and ov[-1]["learned_qty_col"] == 3
    # 平整场地: 工程量空(q 未知) → 行内 max-t 三元组小因子 = 含税单价 1.31(oracle)
    assert got["平整场地"]["unit_price"] == 1.31
    # 多孔砖墙/现浇构件钢筋: 含税单价格是无分隔粘连格 → 锚对(不含税对)之上
    # 以行内最大金额(含税合价)反算 = 旧引擎基线精确一致(oracle)
    assert got["多孔砖墙"]["unit_price"] == 556.99
    assert got["现浇构件钢筋"]["unit_price"] == 1314.37
    # 干净行同样经行内算术恢复(锚对之上含税合价反算)
    assert got["挖沟槽土方"]["unit_price"] == 49.04
    assert got["灰土垫层"]["unit_price"] == 141.70
    # 数量保持种子列语义(idx3),row5 工程量空 → None(契约不变)
    assert got["平整场地"]["quantity"] is None
    assert got["多孔砖墙"]["quantity"] == 210.86


def test_healthy_table_never_learns():
    """全部行价格可用(种子 price_total 列有值) → 零触发、无 meta 键。"""
    rows = [P94_ROWS[0], P94_ROWS[1]]
    for r in P94_ROWS[2:]:
        r = list(r)
        r[9] = r[5]  # 种子 price_total 列 = 干净合价
        rows.append(r)
    items, meta = _extract_from_tables([_tbl(rows)], "s3://b/ok.pdf", SEEDS)
    assert len(items) == 7
    assert "price_rediscovery" not in meta
    assert "anchor_override" not in meta  # 健康表零学习/零覆盖(第八层行内升级不算学习)
    got = _by_name(items)
    # 合价/工程量反算 = 不含税 511.00,第八层行内最大金额(含税合价 117446.91,
    # 增幅 9%)反算升级为含税单价 556.99(= §9.2 oracle,零学习发生)
    assert got["多孔砖墙"]["unit_price"] == 556.99


def test_no_consistent_pair_returns_none_rows_stay_dropped():
    """失败行存在但列间无 ±2% 一致对 → 学习 None,行照旧丢弃、无 meta 键。"""
    rows = [
        P94_ROWS[0],
        P94_ROWS[1],
        ["1", "货物A", "m2", "10.00", "33.30", "999.00", "9%", "", "", "", ""],
        ["2", "货物B", "m2", "20.00", "77.70", "1234.00", "9%", "", "", "", ""],
        ["3", "货物C", "m2", "30.00", "11.10", "888.00", "9%", "", "", "", ""],
    ]
    items, meta = _extract_from_tables([_tbl(rows)], "s3://b/bad.pdf", SEEDS)
    assert items == []  # 双失败照旧丢弃
    assert "price_rediscovery" not in meta


def test_lone_failing_row_single_row_fallback():
    """健康表的单失败行(平整场地类: 工程量空、单价在空格粘连格里、映射 total 有值)
    → 单行数值对回退: 1.31×824.79≈1078.83(±2%) → 单价 1.31 = 旧基线精确一致。"""
    rows = [P94_ROWS[0], P94_ROWS[1]]
    for r in P94_ROWS[2:]:  # 其余行种子列有值 → 健康
        r = list(r)
        r[9] = r[5]
        rows.append(r)
    rows[2] = P94_ROWS[2]  # 平整场地保持失败(idx9='1.31' 有值但 qty 空 → 反算不成)
    assert len(rows) == 9
    items, meta = _extract_from_tables([_tbl(rows)], "s3://b/lone.pdf", SEEDS)
    assert "price_rediscovery" not in meta  # 失败行 <2 → 不学习
    got = _by_name(items)
    assert got["平整场地"]["unit_price"] == 1.31
    assert "单行" in (got["平整场地"]["price_reason"] or "")


def test_lone_fallback_prefers_qty_role_col_value():
    """单行回退的量优先取种子 qty 列(防 单价↔工程量 互换误判):
    63.553×1205.84≈76634.75 应以 qty=63.553 求单价,而非反向。"""
    from scripts.cli import _lone_row_price
    row = ["12", "现浇构件钢筋", "t", "63.553", "1205.84", "76634.75", "9%", "", "6897.131314.37", "", "83531.88"]
    unit, reason = _lone_row_price(row, qty_col=3)
    assert unit == 1205.84
    assert "单行" in reason


# ── 量文本守卫: 单位文本不得当工程量(两段式 x-band 副作用,实测 1.31/2=0.66 污染) ──


def test_qty_text_plausibility():
    from scripts.cli import _qty_text_ok

    assert not _qty_text_ok("m2") and not _qty_text_ok("m3") and not _qty_text_ok("t 1.776")
    assert not _qty_text_ok("") and not _qty_text_ok("平整场地")
    assert _qty_text_ok("63.553") and _qty_text_ok("824.79 1.20") and _qty_text_ok("100m2")


def test_unit_text_as_qty_never_feeds_reverse_calc():
    """qty 被单位文本占用('m2')时: 不得经 parse_qty('m2')=2 反算(1.31/2=0.66);
    行保持失败 → 行内算术(q 未知,max-t 小因子)取含税单价 1.31,非 0.66。"""
    from scripts.cli import _raw_price_usable

    raw = {"price_unit_raw": "", "price_untaxed_raw": "", "price_total_raw": "1.31", "qty_raw": "m2"}
    assert not _raw_price_usable(raw)

    rows = [
        P94_ROWS[0],
        P94_ROWS[1],
        # 平整场地实弹行(qty 列被 'm2' 占位 = 两段式 x-band 认领结果),seed total 有值但量不可信
        ["1", "平整场地", "m2", "m2", "824.79 1.20", "989.75", "9%", "", "89.08", "1.31", "1078.83"],
        ["5", "多孔砖墙", "m3", "210.86", "511.00", "107749.46", "9%", "", "9697.45556.99", "", "117446.91"],
        ["2", "挖沟槽土方", "m3", "120.50", "45.00", "5422.50", "9%", "", "487.03", "", "5909.53"],
        ["3", "灰土垫层", "m3", "88.00", "130.00", "11440.00", "9%", "", "1029.60", "", "12469.60"],
        ["4", "C30混凝土", "m3", "56.20", "410.00", "23042.00", "9%", "", "2073.78", "", "25115.78"],
    ]
    items, meta = _extract_from_tables([_tbl(rows)], "s3://b/m2.pdf", SEEDS)
    got = _by_name(items)
    assert got["平整场地"]["unit_price"] == 1.31  # 行内 max-t 小因子,非 1.31/2=0.66
    assert got["平整场地"]["quantity"] is None  # 'm2' 不得成为工程量
    assert got["多孔砖墙"]["unit_price"] == 556.99  # 含税合价/工程量反算(oracle)
    assert meta["anchor_override"][-1]["learned_unit_col"] == 4  # 覆盖后行级兜底,键随覆盖迁移
