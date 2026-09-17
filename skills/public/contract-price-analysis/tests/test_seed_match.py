"""match_seed: 归一化子串锚点/exclude 守卫/确认条件/多候选消歧。合成表格,无 OCR。"""

from scripts.seed_library import DEFAULT_TABLE_SEEDS
from scripts.table_classifier import _norm_header, match_seed

SEEDS = DEFAULT_TABLE_SEEDS

_GCL_ROWS = [
    ["工程量清单计价表"],
    ["序号", "项目名称", "单 位", "工程量", "不含税单价", "含税单价", "含税合价"],
    ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
]


def test_norm_header_strips_spaces_and_brackets():
    assert _norm_header("5.综合单 价（5=2+3）") == "5.综合单价"
    assert _norm_header("含 税 单 价") == "含税单价"
    assert _norm_header("不含税单价") == "不含税单价"


def test_match_seed_gcl_baseline():
    seed, roles, header_rows = match_seed(_GCL_ROWS, SEEDS)
    assert seed["id"] == "gcl-qd"
    assert roles["name"] == 1
    assert roles["price_unit"] == 5   # 含税单价, 不是 不含税单价(2)
    assert roles["price_total"] == 6
    assert roles["price_untaxed"] == 4
    assert header_rows == 2           # 标题行 + 表头行


def test_match_seed_jzgs_formula_header():
    """JZGS 表头带编号+公式后缀,归一化后命中 综合单价/总金额;网价/运杂费不入角色。"""
    rows = [
        ["序号", "品名", "规格型号", "单位", "1.数量", "2.网价", "3.运杂费", "4.税率", "5.综合单 价（5=2+3）", "6.总金额 6=1*5"],
        ["1", "盘圆", "HPB300 6mm", "吨", "100.000", "4930.00", "107.00", "13%", "5037.00", "503700.00"],
    ]
    seed, roles, _ = match_seed(rows, SEEDS)
    assert seed["id"] == "jzgs-gc"
    assert roles["price_unit"] == 8   # 综合单价,不是网价(5)
    assert roles["price_total"] == 9
    assert "spec" in roles and roles["spec"] == 2


def test_match_seed_exclude_blocks_untaxed_steal():
    """不含税单价 包含 含税单价 子串——exclude 必须拦住。签字版表。"""
    rows = [
        ["品名", "规格型号", "厂家/ 品牌", "单位", "数量", "税率", "网价", "其他 固定 单价", "含税 单价", "不含税 单价", "含税合价"],
        ["热轧光圆钢筋", "HPB300 6mm", "威钢", "t", "4.755", "13%", "4370", "390", "4760", "4214.16", "22633.80"],
    ]
    seed, roles, _ = match_seed(rows, SEEDS)
    assert seed["id"] == "gc-qzb"
    assert roles["price_unit"] == 8   # 含税单价列,非 不含税单价(9)
    assert roles["price_untaxed"] == 9


def test_match_seed_requires_name_and_price():
    """只有名称列没有价格列 → 不确认(返回 None 走 unmatched)。"""
    rows = [
        ["序号", "项目名称", "备注"],
        ["1", "平整场地", "独立费"],
    ]
    assert match_seed(rows, SEEDS) is None


def test_match_seed_title_disambiguation():
    """多 seed 都能锚上时,标题关键词命中者优先。"""
    rows = [
        ["钢筋供货及价格表"],
        ["物资名称", "材质", "计量单位", "暂定数量", "含税单价", "含税总价"],
        ["线材", "HPB300Φ8", "吨", "2.288", "6290", "14391.52"],
    ]
    seed, roles, _ = match_seed(rows, SEEDS)
    assert seed["id"] == "sp-gj"
    assert roles["spec"] == 1         # 材质列作规格
