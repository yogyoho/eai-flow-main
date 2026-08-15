"""模块① 投标报价分析 — seed 扩量生成器规律回归测试。

EAI-CUSTOM: 纯函数断言,不连 DB。用 importlib 按 Windows/容器双兼容路径加载
backend/scripts/seed_mock_market.py(main 有 __main__ 守卫,模块级加载安全)。

校验"三问框架"仪表盘需要的数据故事:
1. 溢价桶胜率单调递减,拐点(+3% 附近)第3→4桶骤降 ≥25pt;
2. ≥2000万 段我方胜率 = 0(大项目短板);
3. 按年我方中标金额份额 2023 < 2024 < 2025(三年趋势,只算生成部分);
4. 东方宏业平均溢价 < 0(低价抢标画像);
5. 共 34 个生成项目,每项目恰一家 won。
"""

import importlib.util
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed_mock_market.py"
_spec = importlib.util.spec_from_file_location("seed_mock_market", SEED_PATH)
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


def test_bucket_win_rate_monotonic_with_cliff():
    """溢价桶胜率单调递减,且第3→4桶(拐点 +3% 附近)骤降 ≥25pt。"""
    plan = seed.gen_bid_plan()
    prems = sorted({e["prem"] for e in plan})
    assert len(prems) == 6, f"应有 6 个溢价桶,实际 {prems}"
    rates = []
    for prem in prems:
        rows = [e for e in plan if e["prem"] == prem]
        assert rows, f"桶 {prem} 不应为空"
        rates.append(100.0 * sum(1 for e in rows if e["our_won"]) / len(rows))
    # 单调递减(允许相等)
    assert all(rates[k] >= rates[k + 1] for k in range(len(rates) - 1)), f"胜率未单调递减: {rates}"
    # 第3桶(prem=+1.5%)→ 第4桶(+4.5%) 骤降 ≥25pt
    assert rates[2] - rates[3] >= 25.0, f"拐点骤降不足 25pt: 桶3={rates[2]:.1f}% 桶4={rates[3]:.1f}%"


def test_gt2000w_our_win_rate_zero():
    """>=2000万 段我方全败: 计划层(seg 规则) + 展开层(我方实际报价金额)双重校验。"""
    plan = seed.gen_bid_plan()
    gt_entries = [e for e in plan if e["seg"] == "gt2000w"]
    assert gt_entries, "gt2000w 段应有项目"
    assert all(not e["our_won"] for e in gt_entries), "计划层: gt2000w 段不允许我方胜单"
    # 展开层: 我方报价 ≥ 2000万 的行全部 won=False(金额口径与仪表盘 SQL 一致)
    for p in seed.gen_projects():
        for r in p["rows"]:
            if r["role"] == "ours" and r["price"] >= 2000.0:  # 万元
                assert not r["won"], f"{p['name']} 我方报价 {r['price']:.0f}万(≥2000万)却中标,违背大项目短板故事"


def test_yearly_our_won_amount_share_strictly_increasing():
    """按年我方中标金额份额 2023 < 2024 < 2025(只算生成部分,手写 2025 项目不计入)。"""
    share = {}
    for y in (2023, 2024, 2025):
        won_amt = total_amt = 0.0
        n_projects = 0
        for p in seed.gen_projects():
            if p["year"] != y:
                continue
            n_projects += 1
            for r in p["rows"]:
                if r["won"]:  # 每项目恰一家 won → 中标金额 = 该行报价
                    total_amt += r["price"]
                    if r["role"] == "ours":
                        won_amt += r["price"]
        assert n_projects > 0, f"{y} 年无生成项目"
        share[y] = won_amt / total_amt
    assert share[2023] < share[2024] < share[2025], f"年度我方中标金额份额未严格递增: {share}"


def test_low_baller_dongfang_hongye_avg_premium_negative():
    """东方宏业: 每个参与项目报价低于其余友商最低价(溢价 = 报价/其余友商最低价 - 1),平均 < 0。"""
    prems = []
    for p in seed.gen_projects():
        mine = [r for r in p["rows"] if r["role"] == "competitor" and r["bidder"] == seed.LOW_BALLER]
        for r in mine:
            others = [r2["price"] for r2 in p["rows"] if r2["role"] == "competitor" and r2["bidder"] != seed.LOW_BALLER]
            assert others, f"{p['name']} 东方宏业之外应有至少 1 家友商"
            prems.append(r["price"] / min(others) - 1.0)
    assert prems, "东方宏业应参与至少 1 个生成项目"
    avg = sum(prems) / len(prems)
    assert avg < 0, f"东方宏业平均溢价应 < 0(低价抢标画像),实际 {avg:.4f}"


def test_34_generated_projects_each_exactly_one_winner():
    """共 34 个生成项目;每项目恰一家 won=True;名字唯一且不与手写 6 项目重名。"""
    projects = seed.gen_projects()
    assert len(projects) == 34
    names = [p["name"] for p in projects]
    assert len(set(names)) == 34, "生成项目名必须唯一"
    handwritten = {p["name"] for p in seed.PROJECTS}
    assert not (set(names) & handwritten), "生成项目名不得与手写项目重名"
    for p in projects:
        winners = [r for r in p["rows"] if r["won"]]
        assert len(winners) == 1, f"{p['name']} 应恰一家 won,实际 {len(winners)}"
        # 友商 2-3 家 + 我方 1 行
        comps = [r for r in p["rows"] if r["role"] == "competitor"]
        assert 2 <= len(comps) <= 3, f"{p['name']} 友商家数应在 2-3,实际 {len(comps)}"
        assert all(r["bidder"] in seed.COMPETITORS_POOL for r in comps), "友商名必须在池内"
        # 每行 3 条 items 且金额非负
        for r in p["rows"]:
            assert len(r["items"]) == 3
            assert all(s >= 0 and o >= 0 for _, _, _, _, s, o in r["items"])


def test_plan_year_quota_respected():
    """年度配额 {2023:(2,9), 2024:(5,7), 2025:(8,3)} 逐项命中(防交错算法悄悄偏移)。"""
    plan = seed.gen_bid_plan()
    for y, (n_won, n_lost) in seed.YEAR_QUOTA.items():
        rows = [e for e in plan if e["year"] == y]
        won = sum(1 for e in rows if e["our_won"])
        assert won == n_won and len(rows) - won == n_lost, f"{y} 年配额不符: 期望 {n_won}胜{n_lost}负,实际 {won}胜{len(rows) - won}负"
