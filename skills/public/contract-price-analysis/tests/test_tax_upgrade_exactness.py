"""bug-3401 第十层含税升级收口回归: ±2% 宽窗口改写正确含税单价(桂北 7 行, 硬门失守)。

第十层(commit 4a2467bc1)设计目标: 碎表头把单价锚落到不含税单价格时, 直取值=
不含税单价(蹲式大便器 412.50), 同行存在 t≈单价×(1+税率) 格 → 升级为含税单价
449.63。但原 ±2% 窗口+兜底税率菜单会把行内无关金额误判为 t(桂北 p96r0 实测:
145.25 落 129.38×1.13±2% → 正确含税单价 129.38 被改写为 145.25/13.6=10.68),
桂北 400 行回归 bad_rate 0→0.0175。
修复律: 升级判据收紧为精确闭合(≤max(0.011, 1e-5·t), 覆盖 2 位小数打印舍入)
——真含税升级是打印级恒等式(449.63=412.50×1.09 精确到分), 无关金额不可能
恰好落在分位; 宽窗口下的伪升级(0.65% 偏差)全部出局。
"""

from types import SimpleNamespace

from scripts.cli import _extract_from_tables
from scripts.seed_library import DEFAULT_TABLE_SEEDS

# gcl-qd seed(桂北同构): 碎表头语义=「含税单价」表头锚住的列物理上是不含税价格
# (真实 桂北 p96/p97 的錨位错位机制), 借表头/数据错位复现直取盲区。
_ROWS = [
    ["项目名称", "规格型号", "单位", "工程量", "含税单价", "含税合价"],
    # 设计目标行(必须保持升级): 直取 412.50(物理为不含税单价), 同行 449.63=
    # 412.50×1.09 分位精确, 数量空 → t 即含税单价直接取 → 449.63。
    ["蹲式大便器", "陶瓷", "套", "", "412.50", "449.63"],
    # 回归行(必须保持原值): 129.38×13.6=1759.57 自洽(已是正确含税单价);
    # 145.25 与 129.38×1.13=146.20 差 0.65%, 仅旧 ±2% 窗口会命中(旧代码产出
    # 145.25/13.6=10.68)——精确闭合下不得触发。
    ["地砖", "800x800", "m2", "13.6", "129.38", "1759.57", "", "145.25"],
]


def _table():
    return SimpleNamespace(
        page_no=1,
        table_idx=0,
        rows=[list(r) for r in _ROWS],
        cell_bboxes=None,
        mean_confidence=0.97,
    )


def _extract():
    items, meta = _extract_from_tables([_table()], "test://tax-upgrade", DEFAULT_TABLE_SEEDS)
    return items, meta


def _find(items, name):
    hits = [it for it in items if (it.get("goods_name") or "") == name]
    assert len(hits) == 1, (name, len(hits))
    return hits[0]


def test_designed_upgrade_still_fires():
    """蹲式大便器: 直取不含税 412.50 → 同行 ×1.09 分位精确格存在 → 升级 449.63
    (第十层设计目标不被收口误伤)。"""
    items, meta = _extract()
    assert meta["matched_seeds"], meta
    it = _find(items, "蹲式大便器")
    assert it.get("unit_price") is not None and abs(it["unit_price"] - 449.63) < 0.011, (
        it.get("unit_price"),
        it.get("price_reason"),
    )
    assert it.get("validation_status") == "ok", (it.get("validation_status"), it.get("price_reason"))
    assert "含税升级" in (it.get("price_reason") or ""), it.get("price_reason")


def test_loose_window_upgrade_blocked():
    """地砖: 正确含税单价 129.38 不得被行内无关金额 145.25 经 ×1.13±2% 宽窗口
    改写(旧代码回归: 129.38→145.25/13.6=10.68, 桂北 bad_rate 0.0175 根因)。"""
    items, _ = _extract()
    it = _find(items, "地砖")
    assert it.get("unit_price") is not None and abs(it["unit_price"] - 129.38) < 0.011, (
        it.get("unit_price"),
        it.get("price_reason"),
    )
    assert it.get("quantity") is not None and abs(it["quantity"] - 13.6) < 1e-6, it.get("quantity")
    assert it.get("validation_status") == "ok", (it.get("validation_status"), it.get("price_reason"))
