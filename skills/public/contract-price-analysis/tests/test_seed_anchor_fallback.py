"""碎表头实弹形状端到端测试(用户实测 0.02 案例,桂北 p94 两行折叠表头)。

裸'含税'兜底锚方案已被否决回退('含税' 是 '含税合价' 子串,会抢走合价列)——
碎表头场景改由 算术锚点覆盖 + 行内算术三元组 兜底恢复,本文件钉住该形状的
端到端结果(不依赖任何 seed 锚改动)。
"""
import sys

sys.path.insert(0, "tests")

from test_xband_fallback import _tbl, SEEDS  # 复用既有夹具助手

from scripts.cli import _extract_from_tables


def test_fragment_header_row_triple_scan_recovers():
    """碎表头: 单价/合价列锚全部失真(两行折叠后只剩'含税'/'合价'碎片,seed 锚
    不落在正确列)→ 表级学不出一致列,行内三元组逐行自洽恢复 7.63/9.81/1.31。"""
    rows = [
        ["工程量清单"] + [""] * 10,
        ["序号", "项目名称", "", "单位工程量", "不含增值税", "", "", "", "税金合 单价", "含税", ""],
        ["", "", "", "", "合价 单价", "", "计", "", "", "合价", ""],
        ["1", "平整场地", "m2", "", "824.79 1.20", "989.75", "9%", "", "89.08", "1.31", "1078.83"],
        ["2", "基础开挖", "m3", "496.19", "7.00", "3473.33", "%6", "", "312.60", "7.63", "3785.93"],
        ["3", "回填方", "m3", "", "406.09 9.00", "3654.81", "9%", "", "328.93", "9.81", "3983.74"],
    ]
    items, meta = _extract_from_tables([_tbl(rows, None, page_no=94)], "s3://b/x.pdf", SEEDS)
    by = {i["goods_name"]: i for i in items}
    assert by["基础开挖"]["unit_price"] == 7.63, f"got {by['基础开挖']['unit_price']}"
    assert by["回填方"]["unit_price"] == 9.81
    assert by["平整场地"]["unit_price"] == 1.31
    assert all(i["unit_price"] is None or i["unit_price"] >= 1.0 for i in items)
    # 恢复走行内三元组(算术自洽),无锚学习/覆盖发生
    assert all("行内算术" in (i["price_reason"] or "") for i in items)
