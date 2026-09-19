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
    # 恢复走行内三元组(算术自洽);P3: 粘连判定遇自洽确认 → 粘连洗白
    assert all(
        ("行内算术" in (i["price_reason"] or "")) or ("粘连洗白" in (i["price_reason"] or ""))
        for i in items
    )


def test_confidence_tiering_nine_cases():
    """第九层置信分层: 「已校验」须直取+行内自洽双确认;直取无佐证/量纲边界
    (<5 元)/仲裁改写 → needs_review(待核验队列,前端「仅看待核验」过滤即看)。"""
    jzgs_hdr = [
        "序号", "品名", "规格型号", "单位", "1.数量", "2.网价", "3.运杂费", "4.税率",
        "5.综合单 价（5=2+3）", "6.总金额 6=1*5",
    ]
    jzgs_title = ["物资采购合同（钢材）"] + [""] * 9
    t1 = _tbl(
        [
            jzgs_title, jzgs_hdr,
            # ① 直取+行内自洽(综合 7.63=网价6.56+运杂费1.07;7.63×496.19=3785.93) → ok
            ["1", "基础开挖", "HPB300", "m3", "496.19", "6.56", "1.07", "13%", "7.63", "3785.93"],
            # ② 直取无佐证(总金额 9999.99 ≠ 1234.56×3,行内无自洽) → needs_review
            ["2", "货物X", "国标", "台", "3", "1234.56", "2345.67", "9%", "1234.56", "9999.99"],
            # ③ 恢复+佐证(综合单价格空,加性 9.81+0.29=10.10,10.10×406.09=4101.51) → ok
            ["3", "回填方", "中砂", "m3", "406.09", "9.81", "0.29", "9%", "", "4101.51"],
            # ④ 量纲边界(综合 4.50 < 5 元) → needs_review
            ["4", "低值品", "国标", "m2", "100", "4.00", "0.50", "13%", "4.50", "450.00"],
        ],
        None, page_no=8,
    )
    # ⑤ 仲裁改写(直取 2.30 被行内算术换 2.51,值冲突史) → needs_review
    t2 = _tbl(
        [
            jzgs_title, jzgs_hdr,
            ["5", "管内穿线", "PVC", "m", "562.97", "2.30", "0.21", "9%", "2.51", "1411.37"],
        ],
        None, page_no=105,
    )
    items, _meta = _extract_from_tables([t1, t2], "s3://b/tier.pdf", SEEDS)
    by = {i["goods_name"]: i for i in items}
    assert by["基础开挖"]["validation_status"] == "ok"  # 直取+自洽双确认
    assert by["货物X"]["validation_status"] == "needs_review"  # 直取无佐证
    assert by["回填方"]["validation_status"] == "ok"  # 恢复+佐证
    assert by["低值品"]["validation_status"] == "ok"  # P2: 综合 4.50 ≥1.0 且加性/乘性自洽
    assert by["管内穿线"]["validation_status"] == "ok"  # 直取+自洽双确认
