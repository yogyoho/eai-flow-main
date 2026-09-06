"""coal-eia-report v2 T2 CRITICAL 参数对照回归（D5：calc 5 脚本 → Decimal 计算函数重写）。

【T7 测试矩阵 7 文件之一（docs/designs/coal-eia-report-v2.md「一期/二期范围」第 8 条，
对齐 geo 先例 backend/tests/test_geological_report_*.py 的组织方式）】
  ① test_coal_eia_calc_regression.py   本文件——calc 参数对照回归（CRITICAL）
  ② test_coal_eia_report_skill.py      SKILL.md v2 结构 + stages/planning_eia.json 接口
  ③ test_coal_eia_report_v2_scripts.py v2 脚本子进程参数化（吸收 scripts/_smoke_t1*.py）
  ④ test_coal_eia_report_e2e_planning.py    横城参数点 planning_eia 全管线 e2e
  ⑤ test_coal_eia_report_e2e_underground.py 月儿湾参数 underground e2e + 实体泄漏反测
  ⑥ test_coal_eia_report_v2_replay.py  KF found=false 兜底契约 + 多 run 断点续跑回放
  ⑦ test_coal_eia_delivery_protocol.py mapping/seed_gen/delivered 交付协议
运行: cd backend && PYTHONPATH=. uv run pytest tests/test_coal_eia_calc_regression.py -v


对 skills/public/coal-eia-report/scripts/calc/ 的 5 个原脚本（只读基准）逐个取 3 组代表参数：
原脚本 subprocess JSON 输出 vs 新 Decimal 函数输出同参同果。容差=原脚本 float 出口舍入界
（0.5·10^-dp × (1+1e-9)，原脚本逐键舍入位见 _TOL_DP）——Decimal 侧为 prec 50 精算，相对误差
≤1e-9 远低于舍入界。fracture_zone 无原脚本（唯一纯新写域）——回归=样例正文数值人工回代单列：
  月儿湾（docs/designs/2026-09-06-coal-eia-v2-yueerwan-ch5-walkthrough.md +
  .wolf/tmp/eia-samples/_body_dump.txt 7.5.2.1）：软弱式 100M/(3.1M+5.0)+4.0 →
  1煤 M=1.46→19.33、3煤 M=1.69→20.51（正文区间下端精确复现）；
  四季屯（sijitun-fulltext.txt 表3.2-23/24）：软弱 24.22/15.22/26.50/19.96/19.16、
  极软弱 14.58、垮落带 2M→4.40，全部逐值精确。

可独立运行：cd backend && PYTHONPATH=. python -m pytest tests/test_coal_eia_calc_regression.py -v
（或 python tests/test_coal_eia_calc_regression.py——文件尾部自跑 main）。

模块名冲突防线：conftest._SkillScriptsFinder 按 SCRIPTS 指向隔离 formula_runner/chapter_planner
（geo/water/coal 三技能同名脚本），故 import 一律放测试函数内、SCRIPTS 必须为模块级常量。
"""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "public" / "coal-eia-report"
SCRIPTS = SKILL / "scripts"
CALC = SCRIPTS / "calc"
STAGE = SKILL / "references" / "stages" / "planning_eia.json"
FORMULAS = SKILL / "references" / "formulas.json"


def _run_script(script: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", str(script), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def _run_calc(name: str, params: dict) -> dict:
    r = _run_script(CALC / name, ["--params", json.dumps(params), "--output", "json"])
    assert r.returncode == 0, f"{name} rc={r.returncode}: {r.stderr[:300]}"
    return json.loads(r.stdout)


# 原脚本逐键出口舍入位（round(x, dp)）——容差=0.5·10^-dp（float 半舍入界），按域分组防串键
_SUBS_DP = {"W_max_mm": 2, "r_m": 2, "U_max_mm": 2, "i_max_mm_per_m": 4, "K_max_per_m_e3": 6, "eps_max_mm_per_m": 4}
_WBAL_DP = {"total_supply_m3d": 2, "total_demand_m3d": 2, "total_reuse_m3d": 2, "total_discharge_m3d": 2, "reuse_rate_pct": 2, "balance_m3d": 2, "balance_ratio": 4, "water_loss_m3d": 2}
_AIRSCREEN_DP = {"plume_rise_m": 2, "effective_height_m": 2, "max_conc_ugm3": 4, "max_conc_distance_m": 1}
_CAP_AIR_DP = {"capacity_10kt_per_year": 4, "capacity_tons_per_year": 2}
_CAP_WATER_DP = {"capacity_tons_per_day": 4, "capacity_tons_per_year": 2}


def _assert_same(old: dict, new: dict, keys: dict[str, int], ctx: str = "") -> float:
    """逐键对照：|new−old| ≤ 0.5·10^-dp·(1+1e-9)。返回最大绝对偏差（报告用）。"""
    worst = 0.0
    for k, dp in keys.items():
        assert k in old, f"{ctx}: 原输出缺键 {k}"
        assert k in new, f"{ctx}: 新输出缺键 {k}"
        o, n = float(old[k]), float(new[k])
        tol = 0.5 * 10 ** (-dp) * (1 + 1e-9)
        dev = abs(n - o)
        worst = max(worst, dev)
        assert dev <= tol, f"{ctx}: {k} old={o} new={n} dev={dev:.3g} > tol={tol:.3g}"
    return worst


# ── ① 参数对照回归：5 原脚本 × 3 组 ─────────────────────────────────────────

_SUBSIDENCE_GROUPS = [
    # 月儿湾走查参数（q=0.8/tgβ=2.4/b=0.3/α=35°，m=3.08 → W_max=2018.39 表5.3-7 实证）
    {"q": 0.8, "b": 0.3, "tan_beta": 2.4, "m": 3.08, "H": 250, "alpha": 35},
    {"q": 0.78, "b": 0.3, "tan_beta": 2.2, "m": 2.5, "H": 150, "alpha": 5},
    {"q": 0.5, "b": 0.2, "tan_beta": 1.5, "m": 6.0, "H": 500, "alpha": 12},
]
_NOISE_GROUPS = [
    {"source_type": "point", "source_level_dBA": 95, "distances_m": [50, 100, 200]},
    {"source_type": "line", "source_level_dBA": 85, "distances_m": [30, 60, 120], "atmospheric_absorption": 2, "ground_factor": 3, "day_limit_dBA": 65, "night_limit_dBA": 55},
    {"source_type": "point", "source_level_dBA": 105, "distances_m": [100, 400, 1000], "atmospheric_absorption": 1, "day_limit_dBA": 70, "night_limit_dBA": 60},
]
_WBALANCE_GROUPS = [
    {
        "supply": [{"name": "矿井水", "volume_m3d": 4800}, {"name": "自来水", "volume_m3d": 200}],
        "demand": [{"name": "生产", "volume_m3d": 2200}, {"name": "生活", "volume_m3d": 600}, {"name": "生态", "volume_m3d": 300}],
        "reuse": [{"name": "回用", "volume_m3d": 1500}],
        "discharge": [{"name": "外排", "volume_m3d": 800}],
    },
    {
        "supply": [{"name": "涌水", "volume_m3d": 12000}],
        "demand": [{"name": "生产", "volume_m3d": 8000}, {"name": "生活", "volume_m3d": 1000}],
        "reuse": [{"name": "选煤", "volume_m3d": 3000}, {"name": "除尘", "volume_m3d": 500}],
        "discharge": [{"name": "外排", "volume_m3d": 2500}],
    },
    {
        "supply": [{"name": "a", "volume_m3d": 900.5}, {"name": "b", "volume_m3d": 99.5}],
        "demand": [{"name": "x", "volume_m3d": 600.25}, {"name": "y", "volume_m3d": 199.75}],
        "reuse": [{"name": "r", "volume_m3d": 100}],
        "discharge": [{"name": "d", "volume_m3d": 50}],
    },
]
_AIRSCREEN_GROUPS = [
    {"emission_rate_gs": 2.5, "stack_height_m": 35, "stack_diameter_m": 1.2, "exit_velocity_ms": 8, "exit_temp_K": 453.15},
    {"emission_rate_gs": 0.8, "stack_height_m": 25, "stack_diameter_m": 0.8, "exit_velocity_ms": 6, "exit_temp_K": 423.15, "wind_speed_ms": 2.0, "stability_class": "B"},
    {"emission_rate_gs": 12, "stack_height_m": 60, "stack_diameter_m": 2.4, "exit_velocity_ms": 12, "exit_temp_K": 493.15, "wind_speed_ms": 4.5, "stability_class": "E"},
]
_CAPACITY_GROUPS = [
    {"type": "air", "area_km2": 86.4, "target_conc_ugm3": 150, "background_conc_ugm3": 45, "A_value": 4.5},
    {"type": "air", "area_km2": 25, "target_conc_ugm3": 60, "background_conc_ugm3": 18, "A_value": 3.5},
    {"type": "air", "area_km2": 120.5, "target_conc_ugm3": 100, "background_conc_ugm3": 30, "A_value": 7.4},
]
_CAPACITY_WATER_GROUPS = [
    {"type": "water", "river_flow_m3s": 1.85, "target_conc_mgL": 20, "background_conc_mgL": 12, "decay_coefficient": 0.15},
    {"type": "water", "river_flow_m3s": 0.42, "target_conc_mgL": 1.0, "background_conc_mgL": 0.3, "decay_coefficient": 0},
    {"type": "water", "river_flow_m3s": 6.7, "target_conc_mgL": 250, "background_conc_mgL": 98, "decay_coefficient": 0.8},
]


class TestCalcRegressionVsOriginal:
    """5 原脚本 × 3 组：同参同果（容差=原 float 出口舍入界）。"""

    def test_subsidence(self):
        import formula_runner as fr

        for i, params in enumerate(_SUBSIDENCE_GROUPS):
            old = _run_calc("calc_subsidence.py", params)
            new = fr.calc_subsidence(params)
            worst = _assert_same(old, new, _SUBS_DP, ctx=f"subsidence#{i}")
            print(f"subsidence#{i} W_max={old['W_max_mm']} max_dev={worst:.2e}")

    def test_noise(self):
        import formula_runner as fr

        for i, params in enumerate(_NOISE_GROUPS):
            old = _run_calc("calc_noise.py", params)
            new = fr.calc_noise(params)
            for j, (po, pn) in enumerate(zip(old["predictions"], new["predictions"])):
                _assert_same(po, pn, {"distance_m": 1, "predicted_dBA": 1}, ctx=f"noise#{i}.pred{j}")
                assert po["day_compliant"] == pn["day_compliant"] and po["night_compliant"] == pn["night_compliant"]
            _assert_same({"d": old["max_compliant_distance_day_m"]}, {"d": new["max_compliant_distance_day_m"]}, {"d": 1}, ctx=f"noise#{i}.day")
            _assert_same({"d": old["max_compliant_distance_night_m"]}, {"d": new["max_compliant_distance_night_m"]}, {"d": 1}, ctx=f"noise#{i}.night")
            print(f"noise#{i} day_dist={old['max_compliant_distance_day_m']}")

    def test_water_balance(self):
        import formula_runner as fr

        for i, params in enumerate(_WBALANCE_GROUPS):
            old = _run_calc("calc_water_balance.py", params)
            new = fr.calc_water_balance(params)
            worst = _assert_same(old, new, _WBAL_DP, ctx=f"water_balance#{i}")
            print(f"water_balance#{i} balance={old['balance_m3d']} max_dev={worst:.2e}")

    def test_air_screen(self):
        import formula_runner as fr

        for i, params in enumerate(_AIRSCREEN_GROUPS):
            old = _run_calc("calc_air_screen.py", params)
            new = fr.calc_air_screen(params)
            _assert_same(old, new, _AIRSCREEN_DP, ctx=f"air_screen#{i}")
            for j, (po, pn) in enumerate(zip(old["concentration_profile"], new["concentration_profile"])):
                assert po["distance_m"] == pn["distance_m"], f"air_screen#{i} 网格点 {j} 错位"
                _assert_same(po, pn, {"concentration_ugm3": 4}, ctx=f"air_screen#{i}.prof{j}")
            print(f"air_screen#{i} max={old['max_conc_ugm3']}@{old['max_conc_distance_m']}m")

    def test_capacity_air(self):
        import formula_runner as fr

        for i, params in enumerate(_CAPACITY_GROUPS):
            old = _run_calc("calc_capacity.py", params)
            new = fr.calc_capacity(params)
            assert old["type"] == new["type"] == "air"
            _assert_same(old, new, _CAP_AIR_DP, ctx=f"capacity_air#{i}")
            _assert_same(old["details"], new["details"], {"A_value": 9, "area_km2": 9, "target_conc_ugm3": 9, "background_conc_ugm3": 9, "delta_C_ugm3": 2, "sqrt_area": 4}, ctx=f"capacity_air#{i}.details")
            print(f"capacity_air#{i} Qa={old['capacity_10kt_per_year']} 万吨/年")

    def test_capacity_water(self):
        import formula_runner as fr

        for i, params in enumerate(_CAPACITY_WATER_GROUPS):
            old = _run_calc("calc_capacity.py", params)
            new = fr.calc_capacity(params)
            assert old["type"] == new["type"] == "water"
            _assert_same(old, new, _CAP_WATER_DP, ctx=f"capacity_water#{i}")
            _assert_same(
                old["details"], new["details"], {"river_flow_m3s": 9, "target_conc_mgL": 9, "background_conc_mgL": 9, "delta_C_mgL": 4, "dilution_capacity_tpd": 4, "self_purification_capacity_tpd": 4}, ctx=f"capacity_water#{i}.details"
            )
            print(f"capacity_water#{i} W={old['capacity_tons_per_day']} 吨/天")


# ── ② fracture_zone 样例人工回代（无原脚本——单列）───────────────────────────


class TestFractureZoneBacksubst:
    """横城型样例正文数值回代（月儿湾 7.5.2.1 / 四季屯 表3.2-23/24 全部逐值精确）。"""

    CASES = [  # (source, seam, M, lithology, 期望 Hf m)
        ("月儿湾7.5.2.1", "1煤", 1.46, "软弱", "19.33"),
        ("月儿湾7.5.2.1", "3煤", 1.69, "软弱", "20.51"),
        ("四季屯表3.2-23", "3煤", 2.2, "极软弱", "14.58"),
        ("四季屯表3.2-23", "6上煤", 2.71, "软弱", "24.22"),
        ("四季屯表3.2-23", "6下煤", 0.86, "软弱", "15.22"),
        ("四季屯表3.2-23", "7煤", 3.72, "软弱", "26.5"),
        ("四季屯表3.2-23", "8煤", 1.58, "软弱", "19.96"),
        ("四季屯表3.2-23", "10煤", 1.43, "软弱", "19.16"),
    ]

    @pytest.mark.parametrize("source,seam,M,cls,expect", CASES)
    def test_hf_backsubst(self, source, seam, M, cls, expect):
        import formula_runner as fr

        got = fr.calc_fracture_zone({"M": M, "lithology": cls})
        assert abs(got["Hf"] - Decimal(expect)) <= Decimal("0.005"), f"{source} {seam} M={M} {cls}: 期望 {expect} 实得 {got['Hf']}"
        assert got["Hf_dev"] == Decimal({"软弱": "4.0", "极软弱": "3.0"}[cls])

    def test_hc_backsubst_and_table(self):
        import formula_runner as fr

        # 四季屯表3.2-24（方法二 MT/T1091 软弱 Hc=2M）：2.2→4.40 精确
        got = fr.calc_fracture_zone({"M": 2.2, "lithology": "软弱"})
        assert got["Hc"] == Decimal("4.40")
        # 类乘系数上界表：坚硬5M/中硬4M/软弱2M/极软弱2M
        assert fr.calc_fracture_zone({"M": 3.0, "lithology": "坚硬"})["Hc"] == Decimal("15.00")
        assert fr.calc_fracture_zone({"M": 3.0, "lithology": "中硬"})["Hc"] == Decimal("12.00")
        assert fr.calc_fracture_zone({"M": 3.0, "lithology": "极软弱"})["Hc"] == Decimal("6.00")

    def test_monotonic_and_asymptote(self):
        """规范公式自洽检验：Hf 随 M 单调增；巨厚段趋近渐近极限 100/a（83.33/62.5/32.26/20）。"""
        import formula_runner as fr

        for cls, limit in (("坚硬", "83.33"), ("中硬", "62.50"), ("软弱", "32.26"), ("极软弱", "20.00")):
            prev = None
            for m in ("0.5", "1.0", "2.0", "3.5", "8.0", "50.0", "5000.0"):
                hf = fr.calc_fracture_zone({"M": m, "lithology": cls})["Hf"]
                if prev is not None:
                    assert hf >= prev, f"{cls} M={m}: Hf 非单调"
                prev = hf
            got_limit = fr.calc_fracture_zone({"M": "500000", "lithology": cls})["Hf_limit"]
            assert abs(got_limit - Decimal(limit)) <= Decimal("0.01"), f"{cls} 渐近极限 {got_limit} ≠ {limit}"

    def test_class_formula_values(self):
        """三类系数独立锚点：M=2.0 各类 Hf 中值（100M/(aM+b)）。"""
        import formula_runner as fr

        assert fr.calc_fracture_zone({"M": 2.0, "lithology": "坚硬"})["Hf_base"] == Decimal("45.45")  # 200/(1.2·2+2)=200/4.4
        assert fr.calc_fracture_zone({"M": 2.0, "lithology": "中硬"})["Hf_base"] == Decimal("29.41")  # 200/(1.6·2+3.6)=200/6.8
        assert fr.calc_fracture_zone({"M": 2.0, "lithology": "软弱"})["Hf_base"] == Decimal("17.86")  # 200/(3.1·2+5.0)=200/11.2


# ── ③ CLI 链路：execute → check → trace → impacted → update（顺序铁律）───────

_DEMO_FORMS: dict[str, dict] = {
    # 月儿湾走查 §2.1 参数（q=0.8 重复采动 0.85/tgβ=2.4 重复采动 2.7/b=0.3；W_max 单层 2018.39 实证锚）
    "subsidence_params": {
        "q": 0.8,
        "b": 0.3,
        "tan_beta": 2.4,
        "q_repeat_mining": 0.85,
        "tan_beta_repeat_mining": 2.7,
        "param_source": "规范推荐值",
        "overburden_lithology": "软弱",
        "per_mine": [
            {"mine": "月儿湾", "seam": "3煤", "m": 3.08, "H": 250, "alpha": 35, "repeat_mining": False},
            {"mine": "月儿湾", "seam": "12-1煤", "m": 1.46, "H": 310, "alpha": 35, "repeat_mining": True},
        ],
        "software_results": {"i_max": 12.5, "eps_max": 6.8, "K_max": 0.35, "U_max": 605.5, "subsidence_area_km2": 2.89},
    },
    "water": {
        "mine_inflow": [{"mine": "月儿湾", "inflow_m3_d": 5800, "measured": False, "analog_source": "银星一号实测类比"}],
        "receiving_water": {"river_flow_m3s": 1.85, "target_conc_mgL": 20, "background_conc_mgL": 12, "decay_coefficient": 0.15},
        "demand": {"production": 2200, "domestic": 600, "ecological": 300},
        "balance": {"reuse": [{"name": "选煤补水", "volume_m3d": 1500}], "discharge": [{"name": "综合利用不外排", "volume_m3d": 0}]},
    },
    "air": {
        "boilers": [{"name": "锅炉房", "stack_h": 35, "stack_d": 1.2, "stack_v": 8, "stack_t": 180, "pollutants": {"SO2": 400, "PM10": 80}}],
        "meteorology": {"wind_speed": 3.0, "stability": "D"},
        "capacity_inputs": {"area": 86.4, "target_conc": 150, "background": 45, "a_value": 4.5},
    },
    "noise": {
        "sources": [{"source": "主通风机", "level": 95, "type": "点源"}, {"source": "运输公路", "level": 85, "type": "线源"}],
        "distances": {"point": [50, 100, 200], "line": [30, 60]},
        "limits": {"day": 65, "night": 55},
    },
    "solid_waste": {"gangue_rate": 15},
    "mine_plan": {"total_scale_mt_a_after": 1.8},
    "investment": {"env_investment": 3200, "total_investment": 180000},
}


@pytest.fixture(scope="module")
def cli_ws(tmp_path_factory):
    """execute 就绪的工作区：data/ 表单 + 冻结层 + manifest。"""
    from types import SimpleNamespace

    root = tmp_path_factory.mktemp("coal_t2_cli") / "ws"
    data, state = root / "data", root / "state"
    data.mkdir(parents=True)
    state.mkdir()
    stage_doc = json.loads(STAGE.read_text(encoding="utf-8"))
    for fam, payload in _DEMO_FORMS.items():
        (data / stage_doc["forms"][fam]["file"]).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    r = _run_script(SCRIPTS / "formula_runner.py", ["execute", "--stage", str(STAGE), "--data-dir", str(data), "--state-dir", str(state)])
    assert r.returncode == 0, f"execute rc={r.returncode}\n{r.stdout[-600:]}\n{r.stderr[:400]}"
    rm = _run_script(SCRIPTS / "chapter_planner.py", ["manifest", "--stage", str(STAGE), "--output", str(state / "chapter_manifest.json")])
    assert rm.returncode == 0, rm.stderr[:300]
    return SimpleNamespace(root=root, data=data, state=state)


class TestCliChain:
    """② 验收：execute 冻结 → check/trace/impacted/update 四 CLI 跑通（update 顺序铁律）。"""

    def test_execute_slots_and_anchors(self, cli_ws):
        st = json.loads((cli_ws.state / "formula_state.json").read_text(encoding="utf-8"))
        v = st["values"]
        # 月儿湾 §2.1 锚：单层 W_max=2018.39（q=0.8/m=3.08/α=35°）；重复采动 q=0.85
        assert v["subsidence.W_max[月儿湾|3煤]"]["display"] == "2018.39"
        assert abs(v["subsidence.W_max[月儿湾|12-1煤]"]["value"] - 0.85 * 1.46 * 0.8191520442889918 * 1000) < 0.01
        # 7 域主槽位齐 + XS4 双口径 + 软件转录槽位（能力边界——source 非 formula）
        for key in (
            "subsidence.W_max",
            "subsidence.W_max[min]",
            "subsidence.i_max",
            "subsidence.eps_max",
            "subsidence.subsidence_area_km2",
            "fracture_zone.fracture_height",
            "fracture_zone.collapse_height",
            "capacity:air.capacity",
            "capacity:water.capacity",
            "water_balance.supply",
            "water_balance.demand",
            "water_balance.deficit",
            "noise.point_level",
            "noise.line_level",
            "noise.compliance_distance",
            "air_screen.max_ground_conc",
            "air_screen.max_conc_distance",
            "solid_waste.gangue_generation",
            "investment.env_investment_ratio",
            "water.mine_inflow",
        ):
            assert key in v, f"主槽位缺失: {key}"
        assert "软件成果转录" in v["subsidence.i_max"]["source"]
        assert v["solid_waste.gangue_generation"]["value"] == 27.0  # 15%×1.8Mt=27万t/a
        assert not st["anomalies"], f"demo 数据应零异常: {st['anomalies'][:3]}"

    def test_check_selfconsistent_and_anchors(self, cli_ws):
        r = _run_script(
            SCRIPTS / "formula_runner.py",
            ["check", "--stage", str(STAGE), "--data-dir", str(cli_ws.data), "--state", str(cli_ws.state / "formula_state.json"), "--anchors", json.dumps({"subsidence.W_max[月儿湾|3煤]": 2018.39, "solid_waste.gangue_generation": 27.0})],
        )
        assert r.returncode == 0, f"check rc={r.returncode}\n{r.stdout[-500:]}"
        assert "PASS" in r.stdout and "state_selfcheck" not in r.stdout

    def test_trace(self, cli_ws):
        r = _run_script(SCRIPTS / "formula_runner.py", ["trace", "--state", str(cli_ws.state / "formula_state.json"), "--formulas", str(FORMULAS), "--output", str(cli_ws.state / "traces.json")])
        assert r.returncode == 0, r.stderr[:300]
        tr = json.loads((cli_ws.state / "traces.json").read_text(encoding="utf-8"))["traces"]
        by_id = {t["formula_id"] for t in tr}
        # formulas.json ids 与 planning_eia.json formulas 声明对齐（不自创键名）
        assert {"subsidence", "fracture_zone", "capacity:air", "capacity:water", "noise", "air_screen", "water_balance"} <= by_id
        wmax = next(t for t in tr if t["slot"] == "subsidence.W_max[月儿湾|3煤]")
        assert wmax["name"] != "?" and wmax["precision"], "formulas.json 定义未命中 trace"

    def test_impacted_then_update_order_ironlaw(self, cli_ws):
        # 先 impacted（dry-run 零写盘）——q 0.8→0.85 只应影响 subsidence
        ri = _run_script(
            SCRIPTS / "formula_runner.py",
            [
                "impacted",
                "--stage",
                str(STAGE),
                "--data-dir",
                str(cli_ws.data),
                "--state",
                str(cli_ws.state / "formula_state.json"),
                "--field",
                "13.q",
                "--value",
                "0.85",
                "--manifest",
                str(cli_ws.state / "chapter_manifest.json"),
                "--output",
                str(cli_ws.state / "impacted.json"),
            ],
        )
        assert ri.returncode == 0, ri.stderr[:300]
        imp = json.loads((cli_ws.state / "impacted.json").read_text(encoding="utf-8"))
        assert imp["affected_formulas"] == ["subsidence"], imp["affected_formulas"]
        assert any("ch6" in c or "ch9" in c or "ch13" in c for c in imp["affected_chapters"]), imp["affected_chapters"]
        base = json.loads((cli_ws.state / "formula_state.json").read_text(encoding="utf-8"))
        assert "subsidence.W_max[月儿湾|3煤]" in imp["changes"], "真值差分应检出 W_max 变化"
        # update 缺 impacted-file → 拒绝（顺序铁律）
        rg = _run_script(
            SCRIPTS / "formula_runner.py",
            ["update", "--stage", str(STAGE), "--data-dir", str(cli_ws.data), "--state", str(cli_ws.state / "formula_state.json"), "--field", "13.q", "--value", "0.85", "--output", str(cli_ws.state / "fs2.json")],
        )
        assert rg.returncode in (1, 2) and "impacted-file" in rg.stderr  # argparse required 缺参=2 / 显式守卫=1
        # impacted-file 与实际差分不一致 → 拒绝
        bad = dict(imp, affected_formulas=["noise"])
        (cli_ws.state / "impacted_bad.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rb = _run_script(
            SCRIPTS / "formula_runner.py",
            [
                "update",
                "--stage",
                str(STAGE),
                "--data-dir",
                str(cli_ws.data),
                "--state",
                str(cli_ws.state / "formula_state.json"),
                "--field",
                "13.q",
                "--value",
                "0.85",
                "--impacted-file",
                str(cli_ws.state / "impacted_bad.json"),
                "--output",
                str(cli_ws.state / "fs2.json"),
            ],
        )
        assert rb.returncode == 1 and "不一致" in rb.stderr
        # 真 impacted-file → update 落盘（经 ingest 唯一写者）→ 新冻结值=0.85 口径
        ru = _run_script(
            SCRIPTS / "formula_runner.py",
            [
                "update",
                "--stage",
                str(STAGE),
                "--data-dir",
                str(cli_ws.data),
                "--state",
                str(cli_ws.state / "formula_state.json"),
                "--field",
                "13.q",
                "--value",
                "0.85",
                "--impacted-file",
                str(cli_ws.state / "impacted.json"),
                "--output",
                str(cli_ws.state / "formula_state.json"),
            ],
        )
        assert ru.returncode == 0, ru.stderr[:400]
        assert "CHANGED_FORMULAS: ['subsidence']" in ru.stdout
        post = json.loads((cli_ws.state / "formula_state.json").read_text(encoding="utf-8"))
        assert abs(post["values"]["subsidence.W_max[月儿湾|3煤]"]["value"] - 0.85 * 3.08 * 0.8191520442889918 * 1000) < 0.01
        # 表单确经 ingest 写回（唯一写者语义），基线冻结层未被 dry-run 污染
        form_q = json.loads((cli_ws.data / "13_subsidence_params.json").read_text(encoding="utf-8"))["q"]
        assert form_q == 0.85
        assert base["values"]["subsidence.W_max[月儿湾|3煤]"]["display"] == "2018.39"

    def test_progress_run_stage_freeze_linkage(self, tmp_path):
        """③ progress.py run-stage freeze（manifest+execute 合并命令）不破。"""
        ws = tmp_path / "pg"
        (ws / "data").mkdir(parents=True)
        stage_doc = json.loads(STAGE.read_text(encoding="utf-8"))
        for fam, payload in _DEMO_FORMS.items():
            (ws / "data" / stage_doc["forms"][fam]["file"]).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        ri = _run_script(SCRIPTS / "progress.py", ["init", "--stage", str(STAGE), "--state-dir", str(ws), "--data-dir", str(ws / "data")])
        assert ri.returncode == 0, ri.stderr[:300]
        rf = _run_script(SCRIPTS / "progress.py", ["run-stage", "freeze", "--state-dir", str(ws)])
        assert rf.returncode == 0, f"run-stage freeze rc={rf.returncode}\n{rf.stdout[-400:]}\n{rf.stderr[:300]}"
        assert (ws / "formula_state.json").exists() and (ws / "chapter_manifest.json").exists()

    def test_build_output_slot_keys_resolvable(self, cli_ws):
        """冻结槽位 key 与 stage {{SLOT:}} 引用闭合：ch6/ch7 引用的公式主槽位必须全部在册
        （防 T3 键名与 runner 发明键漂移——未知槽位=build FAIL）。"""
        st = json.loads((cli_ws.state / "formula_state.json").read_text(encoding="utf-8"))["values"]
        stage = json.loads(STAGE.read_text(encoding="utf-8"))
        referenced: set[str] = set()
        for ch in stage["chapters"].values():
            for sec in ch.get("sections", []):
                for s in sec.get("slots", []) + sec.get("uses", {}).get("slots", []):
                    if s.startswith("{{SLOT:"):
                        referenced.add(s[len("{{SLOT:") : -2])
        # runner 拥有的槽位域（公式 7 域主/明细槽位 + 派生 + XS12 转录合计）
        owned = ("subsidence.", "fracture_zone.", "capacity:water.", "capacity:air.", "noise.", "air_screen.", "water_balance.", "solid_waste.gangue_generation", "investment.env_investment_ratio", "water.mine_inflow")
        missing = sorted(s for s in referenced if s not in st and (s.startswith(owned[:-1]) or s in owned))
        assert not missing, f"stage 引用的公式域槽位缺失: {missing}"
        assert referenced, "stage 无任何槽位引用（读错文件？）"
        # 已知集成缺口（非 T2 范围）：表单值槽位（mine_plan.*/project.* 等）stage 以 {{SLOT:}} 引用、
        # build_output 只注 formula_state——须由 T3/build 侧合并表单转录或扩 runner 通用转录，此处仅可见化。
        residual = sorted(s for s in referenced if s not in st)
        print(f"formula-domain slots closed; form-value slots pending T3/build merge: {len(residual)}")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--no-header", "-x"]))
