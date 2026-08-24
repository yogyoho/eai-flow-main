"""bug-2223 回归：schema 归一化 / formula_state 手改检测 / 深度门 / 交付名门。

设计: docs/geological-report-bug2223-fix-2026-08-24.md
E2E 证据: 线程 47d8c147（L9 静默 0 → agent 手改编造 TM/KZ/TD 拆分）

运行: cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_bug2223.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "public" / "geological-report"
SCRIPTS = SKILL / "scripts"
STAGE = SKILL / "references/stages/exploration.json"

sys.path.insert(0, str(SCRIPTS))


def run(*args, expect=(0,)):
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / args[0]), *map(str, args[1:])], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout[-800:]}\n{r.stderr[:400]}"
    return r


# ── Task 2: 归一化单元测试（直调内部函数，不走 CLI） ────────────────────────


class TestNormalize:
    def test_grade_class_map(self):
        import formula_runner as fr
        assert fr.norm_grade_class("工业矿") == "工业"
        assert fr.norm_grade_class("工业") == "工业"
        assert fr.norm_grade_class("低品位矿") == "低品位"
        assert fr.norm_grade_class("低品位") == "低品位"
        assert fr.norm_grade_class("") == "工业"  # 缺省=工业（原行为）
        assert fr.norm_grade_class("矿石") is None  # 未知→None→anomaly

    def test_category_map(self):
        import formula_runner as fr
        assert fr.norm_category("探明") == "TM"
        assert fr.norm_category("控制") == "KZ"
        assert fr.norm_category("推断") == "TD"
        assert fr.norm_category("TM") == "TM"
        assert fr.norm_category("探明+控制") == "探明+控制"  # 复合：原样保留进 total，不进分类别
        assert fr.norm_category("探明＋控制") == "探明＋控制"  # 全角＋复合：同上（bug-2223 质量收口）
        assert fr.norm_category("xyz") is None  # 完全未知→None→anomaly


# ── Task 2: E2E 场景回归（47d8c147 实喂数据 → L9 不得再静默 0） ─────────────


@pytest.fixture(scope="module")
def l9_ws(tmp_path_factory):
    """复现 E2E 场景：aggregates 用中文类别+复合类别+「工业矿」——旧代码 L9 全 0。"""
    base = tmp_path_factory.mktemp("bug2223")
    data, state = base / "data", base / "state"
    data.mkdir(parents=True)
    state.mkdir(parents=True)
    run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data)
    import ingest

    ingest.write_form_values(str(STAGE), str(data), "industrial_params",
                             {"boundary_grade_cu": 0.3, "min_industrial_grade_cu": 0.5, "min_mining_thickness": 1.0,
                              "waste_exclusion_thickness": 2.0, "grade_variation_coeff_range": [30, 50],
                              "outlier_multiple": 3, "deposit_avg_grade": 1.41})
    # 47d8c147 实喂结构：中文 category + 复合类别 + grade_class="工业矿"
    bm = {"granularity": "B", "aggregates": [
        {"orebody": "I-1", "category": "探明+控制", "grade_class": "工业矿", "ore_qty_wt": 485.6, "metal_t": 8352, "grade_pct": 1.72},
        {"orebody": "I-2", "category": "控制", "grade_class": "工业矿", "ore_qty_wt": 120.3, "metal_t": 1299, "grade_pct": 1.08},
        {"orebody": "II-1", "category": "推断", "grade_class": "低品位矿", "ore_qty_wt": 72.5, "metal_t": 624, "grade_pct": 0.86},
    ]}
    ingest.write_form_values(str(STAGE), str(data), "block_model", bm)
    return {"data": data, "state": state}


class TestL9Normalization:
    def test_total_not_silent_zero(self, l9_ws):
        """修复前：六行全判低品位 → L9.total_*=0 静默。修复后 total=可归入行合计+复合行 anomaly。"""
        run("formula_runner.py", "execute", "--stage", STAGE, "--data-dir", l9_ws["data"], "--state-dir", l9_ws["state"], expect=(0, 3))
        st = json.loads((l9_ws["state"] / "formula_state.json").read_text(encoding="utf-8"))
        v = st["values"]
        # I-2(控制,工业矿→工业) 120.3 万吨进工业总量；复合行 I-1 也进总量（grade_class=工业）
        assert v["L9.total_ore_wt"]["value"] == 605.9  # 485.6+120.3
        assert v["L9.KZ_ore_wt"]["value"] == 120.3
        assert v["L9.TM_ore_wt"]["value"] == 0  # 数据里确无纯探明行——0 是诚实值
        # 低品位行 II-1（低品位矿→低品位）正常归类
        assert v["L9.low_TD_ore_wt"]["value"] == 72.5
        # 复合类别必须产 anomaly（问用户占比），未知 grade_class 不再静默
        assert any("复合类别" in a and "探明+控制" in a for a in st["anomalies"]), st["anomalies"]

    def test_unknown_grade_class_anomaly(self, l9_ws, tmp_path):
        """grade_class 完全未知 → 行跳过 + anomaly，不污染汇总。"""
        data = tmp_path / "d2"
        data.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data)
        import ingest
        bm = {"granularity": "B", "aggregates": [
            {"orebody": "I-1", "category": "探明", "grade_class": "矿石", "ore_qty_wt": 100, "metal_t": 500, "grade_pct": 0.5},
        ]}
        ingest.write_form_values(str(STAGE), str(data), "block_model", bm)
        st_dir = tmp_path / "s2"
        st_dir.mkdir()
        run("formula_runner.py", "execute", "--stage", STAGE, "--data-dir", data, "--state-dir", st_dir, expect=(0, 3))
        st = json.loads((st_dir / "formula_state.json").read_text(encoding="utf-8"))
        assert any("grade_class" in a and "矿石" in a for a in st["anomalies"])
        assert "L9.total_ore_wt" not in st["values"] or st["values"]["L9.total_ore_wt"]["value"] == 0

    def test_all_rows_low_anomaly(self, l9_ws, tmp_path):
        """rows 非空但工业行全空 → anomaly 提示核对 grade_class（防御，不再静默 0）。"""
        data = tmp_path / "d3"
        data.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data)
        import ingest
        bm = {"granularity": "B", "aggregates": [
            {"orebody": "I-1", "category": "推断", "grade_class": "低品位矿", "ore_qty_wt": 100, "metal_t": 500, "grade_pct": 0.3},
        ]}
        ingest.write_form_values(str(STAGE), str(data), "block_model", bm)
        st_dir = tmp_path / "s3"
        st_dir.mkdir()
        run("formula_runner.py", "execute", "--stage", STAGE, "--data-dir", data, "--state-dir", st_dir, expect=(0, 3))
        st = json.loads((st_dir / "formula_state.json").read_text(encoding="utf-8"))
        assert any("全部行被判为低品位" in a for a in st["anomalies"]), st["anomalies"]


# ── Task 2 质量收口：execute 旗标契约 + 空白表单降级 anomaly 钉住 ───────────────


class TestExecuteFlags:
    """--output/--state-dir argparse 互斥组；二者皆缺走显式 rc=1 报错（不触碰数据目录）。"""

    def test_neither_flag_errors(self, tmp_path):
        r = run("formula_runner.py", "execute", "--stage", STAGE, "--data-dir", tmp_path, expect=(1,))
        assert "--output" in r.stderr and "--state-dir" in r.stderr

    def test_both_flags_usage_error(self, tmp_path):
        run("formula_runner.py", "execute", "--stage", STAGE, "--data-dir", tmp_path, "--output", tmp_path / "s.json", "--state-dir", tmp_path, expect=(2,))


class TestBlankFormAnomalies:
    """空白表单（必填全 null 骨架）必须降级为显式 anomaly——契约钉住，不只锁 rc。"""

    def test_blank_forms_pinned_anomalies(self, tmp_path):
        data, state = tmp_path / "d6", tmp_path / "s6"
        data.mkdir()
        state.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data)  # 全空白骨架（必填 null，不 write 任何值）
        run("formula_runner.py", "execute", "--stage", STAGE, "--data-dir", data, "--state-dir", state, expect=(0, 3))
        st = json.loads((state / "formula_state.json").read_text(encoding="utf-8"))
        assert any("13_industrial_params" in a and "缺失/空白" in a for a in st["anomalies"]), st["anomalies"]
        assert any("16_economics" in a for a in st["anomalies"]), st["anomalies"]
