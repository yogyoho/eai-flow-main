"""ssxl-cgjh 深扫表头兜底 + 砂石料 p4 审批单种子(wf 待办 2026-09-20)。

砂石料 p4『大宗物资采购审批单·计划采购主要物资』: 真表头在第 4 行(前 3 行是
表单 label:value 行,含伪表头 token『完工时间』),标准 _collapse_header(peek=3)
折叠出『制表人…』伪表头 → 永不命中。深扫兜底: seed 锚(≥2 角色)+标题词双门,
从 rows[:8] 逐行找真表头。种子只许命中 p4(129 表回放固化,零翻旧命中);
p6 会签价目表与 p13 同货同价,双 ingestion 会污染统计——明确不许命中。

p4 网格重病(PP-Structure 错位): 物资单价+运输单价综合价拆胶('150.00 50.00'/
'123.00'+'28.00' 两格)、量格粘连('217500.0060.00')、总价列漂移(r7→c7,r11→c9)、
r11 名称格只剩序号'8'。合计闭环重推(_closure_recover_rows)以打印总额
49,868,500 为独立锚逐行恢复 t/q/u——8 行真值:
  粉煤灰 16350×200 / 机制砂 217500×89 / 河砂 26000×151 / 碎石5-10 4500×130 /
  碎石10-20 40000×125 / 碎石5-16 150000×58 / 碎石16-31.5 110000×58 /
  减水剂母液 500×5300 (物资+运输=综合单价,×数量=预计总价,Σ=打印总额)。
"""

from scripts.cli import _extract_from_tables, _closure_recover_rows
from scripts.seed_library import DEFAULT_TABLE_SEEDS, normalize_seeds
from scripts.table_classifier import extract_items_seed, match_seed

SEEDS = DEFAULT_TABLE_SEEDS

# 砂石料 p4/t0 实测缓存行(裁剪: 标题 3 行 + 表头 + 8 货物行 + 合计行,列位原样)。
_P4_ROWS = [
    ["上报项目", "宜春项目", "", "项目全称", "", "中交第三公路工程局有限公司宜春大道总承包项目经理部", "", "", "", "", "", ""],
    ["制表人", "", "刘君", "", "联系电话", "18679500663", "", "完工时间 2021-06-20", "", "", "", ""],
    ["拟采购主要物资基本 情况（具体见附件）", "", "粉煤灰、砂石料、减水剂母液采购。", "", "", "", "", "", "", "", "", ""],
    ["计划采购主要物资", "序号 物资名称", "II级", "规格型号计量单位", "", "数量", "物资单价运输单价", "", "预计总价", "使用时间", "采购方式", ""],
    ["", "粉煤灰", "", "吨", "", "16350.000", "150.00 50.00", "", "3,270,000.00", "2019-07-25", "线上公开", ""],
    ["", "2 机制砂", "中租", "吨", "0", "217500.0060.00", "29.00", "", "19,357,500.00", "2019-07-25", "线上公开", ""],
    ["", "3 河砂", "小粗", "吨", "", "26000.000", "123.00", "28.00", "3,926,000.00", "2019-07-25", "线上公开", ""],
    ["", "1 碎石", "5-10", "吨", "", "4500.000", "110.00 20.00", "585,000.00", "", "2019-07-25", "线上公开", ""],
    ["", "5 碎石", "10-20", "吨", "", "40000.000", "105.00", "20.00", "5,000,000.00", "2019-07-25", "线上公开", ""],
    ["", "6 碎石", "5-16", "", "吨", "150000.00", "45.00", "13.00", "8,700,000.00", "2019-07-25", "线上公开", ""],
    ["", "7 碎石", "", "16-31.5 吨", "", "0 110000.00", "45.00 13.00", "", "6,380,000.00", "2019-07-25", "线上公开", ""],
    ["", "8", "减水剂母液 吨", "0 500.000 5,300.00", "", "", "", "", "", "2,650,000.00", "2019-07-25", "线上公开"],
    ["预计总金额", "插入项 49868500元", "", "", "", "", "", "", "", "", "", ""],
]

# 砂石料 p6/t0 会签价目表区(实测缓存行,裁剪): r5 表头 '名称/规格型号 数量…/单价/
# 税率/金额'——无『物资名称』『预计总价』字样,新种子 name 锚不命中 → 不得深扫命中。
_P6_ROWS = [
    ["项目名称：", "合同备案编亏： 2G3-CL-CG-2019-393 中交第三公路工程局有限公司宜春大道总承包项目经理部", "", "", "", "", ""],
    ["", "砂石料采购", "", "项目合同编号", "", "", ""],
    ["合同内容", "", "", "是", "2GS-YCXM-CL-CG-024-2019", "", ""],
    ["供方单位 付款方式", "宜春市佳之通贸易有限公司", "", "项目是否会签 采购方式 线上公开", "", "", ""],
    ["网银支付", "标的物名称型号数量", "", "", "", "", ""],
    ["名称", "规格型号 数量（带单 位）", "单价", "税率", "金额 (元)", "备注（租赁期", ""],
    ["河砂", "中粗", "8000（吨） 173", "3%", "1384000", "限）", ""],
    ["机制砂", "中粗", "70000（吨）", "108 3%", "7560000", "", ""],
]


def _tbl(rows, page_no=4, table_idx=0):
    from types import SimpleNamespace

    return SimpleNamespace(
        page_no=page_no, table_idx=table_idx, rows=rows, cell_bboxes=None,
        page_preview_b64="", mean_confidence=0.9,
    )


# ── 深扫表头兜底 + 种子命中 ──────────────────────────────────────────────────


def test_match_seed_deep_finds_real_header_on_p4():
    """标准折叠(前3行)翻不出真表头 → 深扫兜底: 锚+标题词双门命中 ssxl-cgjh,
    header_rows=4(表头行 r3 + 上方 3 表单行)。"""
    hit = match_seed(_P4_ROWS, SEEDS)
    assert hit is not None
    seed, roles, header_rows = hit
    assert seed["id"] == "ssxl-cgjh"
    assert roles == {"name": 1, "qty": 5, "unit": 3, "price_unit": 6, "price_total": 8}
    assert header_rows == 4


def test_match_seed_deep_negative_p6_never_hit():
    """p6 会签价目表(与 p13 同货同价)不得被新种子命中——名称锚『物资名称』
    不在 p6 表头,标题词『拟/计划采购主要物资』也不在。"""
    seeds = normalize_seeds(SEEDS)
    assert match_seed(_P6_ROWS, seeds) is None


def test_p13_still_belongs_to_ssly_sm():
    """新种子不许抢走 p13(采购物资说明): 标题命中+专锚归 ssly-sm。"""
    rows = [
        ["采购物资说明", "品名", "规格型号", "厂家/ 品牌", "单 位", "数量", "税率", "含税落地单价 （元）", "落地合价 （元）", "备注"],
        ["河砂", "中粗", "", "吨", "8000", "3%", "173", "1384000", ""],
    ]
    seed, _roles, _hr = match_seed(rows, SEEDS)
    assert seed["id"] == "ssly-sm"


def test_extract_items_seed_raw_8_rows():
    """extract_items_seed 原始 8 行: 名称/数量/单价/总价列元组逐行正确(综合单价
    列的胶合原文如实带出,综合值的算术恢复属 cli 层)。"""
    seed, roles, header_rows = match_seed(_P4_ROWS, SEEDS)
    items = extract_items_seed(_P4_ROWS, seed, roles, header_rows)
    assert len(items) == 8
    assert [it["name"] for it in items] == [
        "粉煤灰", "2 机制砂", "3 河砂", "1 碎石", "5 碎石", "6 碎石", "7 碎石", "8",
    ]
    assert [it["qty_raw"] for it in items][:6] == [
        "16350.000", "217500.0060.00", "26000.000", "4500.000", "40000.000", "150000.00",
    ]
    assert items[0]["price_unit_raw"] == "150.00 50.00" and items[0]["price_total_raw"] == "3,270,000.00"
    assert items[2]["price_unit_raw"] == "123.00" and items[2]["price_untaxed_raw"] == ""
    # 合计行/意见行不产 item;单价×数量=总价的算术关系交给 cli 层闭环重推


# ── 管线级: 合计闭环重推 8 行真值 ────────────────────────────────────────────


def test_pipeline_recovers_8_rows_to_printed_total():
    """端到端: 8 行 名称/数量/综合单价 全部真值,validation_status 全 ok,
    Σ(量×价)=打印总额 49,868,500;r11 序号'8'名被烂行改名救成『减水剂母液 吨』。"""
    items, meta = _extract_from_tables([_tbl(_P4_ROWS)], "s3://b/k.pdf", SEEDS)
    assert len(items) == 8
    got = [(it["goods_name"], it["quantity"], it["unit_price"]) for it in items]
    assert got == [
        ("粉煤灰", 16350.0, 200.0),
        ("2 机制砂", 217500.0, 89.0),
        ("3 河砂", 26000.0, 151.0),
        ("1 碎石", 4500.0, 130.0),
        ("5 碎石", 40000.0, 125.0),
        ("6 碎石", 150000.0, 58.0),
        ("7 碎石", 110000.0, 58.0),
        ("减水剂母液 吨", 500.0, 5300.0),
    ]
    assert all(it["validation_status"] == "ok" for it in items)
    assert abs(sum(q * u for _, q, u in got) - 49868500.0) < 0.01


# ── 闭环重推守卫(负例) ───────────────────────────────────────────────────────


def test_closure_recover_guards():
    """无合计行/项数<3/已闭环 → 零干预;调价表(adj)跳过。"""
    rows_no_total = [r for r in _P4_ROWS]  # 无 '预计总金额' 行
    items, meta = _extract_from_tables([_tbl(rows_no_total[:11])], "s3://b/k.pdf", SEEDS)
    # 无合计锚: 行保持行级仲裁原状(不重推不改写)
    before = [(it["goods_name"], it["quantity"], it["unit_price"], it["price_reason"]) for it in items]
    _closure_recover_rows(_tbl(rows_no_total[:11]), items, 0)
    after = [(it["goods_name"], it["quantity"], it["unit_price"], it["price_reason"]) for it in items]
    assert before == after


def test_closure_recover_noop_when_already_closed():
    """健康表(提取已闭环)零干预: 重推前后逐项一致。"""
    healthy = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
        ["2", "回填方", "m3", "406.09", "8.27", "9.00", "3654.81"],
        ["", "合计", "", "", "", "", "4,644.56"],
    ]
    items, _meta = _extract_from_tables([_tbl(healthy, page_no=1)], "s3://b/k.pdf", SEEDS)
    snapshot = [dict(it) for it in items]
    _closure_recover_rows(_tbl(healthy, page_no=1), items, 0)
    assert items == snapshot
