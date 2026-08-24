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

    ingest.write_form_values(
        str(STAGE),
        str(data),
        "industrial_params",
        {"boundary_grade_cu": 0.3, "min_industrial_grade_cu": 0.5, "min_mining_thickness": 1.0, "waste_exclusion_thickness": 2.0, "grade_variation_coeff_range": [30, 50], "outlier_multiple": 3, "deposit_avg_grade": 1.41},
    )
    # 47d8c147 实喂结构：中文 category + 复合类别 + grade_class="工业矿"
    bm = {
        "granularity": "B",
        "aggregates": [
            {"orebody": "I-1", "category": "探明+控制", "grade_class": "工业矿", "ore_qty_wt": 485.6, "metal_t": 8352, "grade_pct": 1.72},
            {"orebody": "I-2", "category": "控制", "grade_class": "工业矿", "ore_qty_wt": 120.3, "metal_t": 1299, "grade_pct": 1.08},
            {"orebody": "II-1", "category": "推断", "grade_class": "低品位矿", "ore_qty_wt": 72.5, "metal_t": 624, "grade_pct": 0.86},
        ],
    }
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

        bm = {
            "granularity": "B",
            "aggregates": [
                {"orebody": "I-1", "category": "探明", "grade_class": "矿石", "ore_qty_wt": 100, "metal_t": 500, "grade_pct": 0.5},
            ],
        }
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

        bm = {
            "granularity": "B",
            "aggregates": [
                {"orebody": "I-1", "category": "推断", "grade_class": "低品位矿", "ore_qty_wt": 100, "metal_t": 500, "grade_pct": 0.3},
            ],
        }
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


# ── Task 3/4/5: build_output 三门共用 fixture ───────────────────────────────

PROJ_NAME = "东川区某铜银金多金属矿"
DELIV = f"{PROJ_NAME}-勘探-地质勘查报告.md"  # 规范交付名


@pytest.fixture(scope="module")
def build_ws(tmp_path_factory):
    """最小可 build 环境：project 表单 + 合规章节 + 带完整 source 的 formula_state。"""
    base = tmp_path_factory.mktemp("bug2223build")
    data, state, out = base / "data", base / "state", base / "out"
    for d in (data, state, state / "chapters", out):
        d.mkdir(parents=True)
    run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data)
    import ingest

    ingest.write_form_values(
        str(STAGE),
        str(data),
        "project",
        {
            "project_name": PROJ_NAME,
            "stage": "勘探",
            "commodity": "铜银金",
            "commissioning_unit": "某矿业公司",
            "undertaking_unit": "某地质大队",
            "work_start": "2023-01",
            "work_end": "2025-12",
            "purpose_tasks": ["查明矿体特征", "估算资源量"],
            "cutoff_date": "2025-12-31",
        },
    )
    # 合规章节：每块 ≥3 句 + 每章 ≥1000 有效字符（供 Task 4 深度门正例）。
    # 合成内容只验管线不验文学性——SEC 2 句×64字 ×12 重复 = 24句/768字/块，每章 2 块=~1536字（对 1000 阈值留余量），确定性凑量。
    SEC = "本段叙述勘查工作部署与质量情况，内容完整表述规范，满足深度门要求。每次工程布置依据充分且间距合理，资料经检查验收合格可用于估算。"
    SEC *= 12
    for n in range(1, 11):
        md = f"## {n} 第{n}章\n\n{SEC}\n\n### {n}.1 小节\n\n{SEC}\n"
        (state / "chapters" / f"ch{n}.md").write_text(md, encoding="utf-8")
    # formula_state：全部槽位带 source（公式产物特征）
    fs = {
        "version": 2,
        "values": {"L9.total_ore_wt": {"value": 899.0, "display": "899.00", "unit": "万吨", "source": "formula:L9"}, "L9.TM_ore_wt": {"value": 339.92, "display": "339.92", "unit": "万吨", "source": "formula:L9"}},
        "anomalies": [],
    }
    (state / "formula_state.json").write_text(json.dumps(fs, ensure_ascii=False), encoding="utf-8")
    return {"data": data, "state": state, "out": out}


def _build(ws, out_name=DELIV, expect=(0,)):
    return run("build_output.py", "--stage", STAGE, "--data-dir", ws["data"], "--state-dir", ws["state"], "--output", ws["out"] / out_name, expect=expect)


class TestTamperGate:
    def test_happy_path_with_source(self, build_ws):
        """全槽位带 source → 通过（三门都不拦）。"""
        _build(build_ws)

    def test_missing_source_rejected(self, build_ws, tmp_path):
        """数值槽缺 source 键（=手改法医特征）→ rc=1。"""
        import shutil

        st = tmp_path / "state"
        shutil.copytree(build_ws["state"], st)
        p = st / "formula_state.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        del d["values"]["L9.TM_ore_wt"]["source"]  # 模拟 agent 手改丢 source
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        ws = {"data": build_ws["data"], "state": st, "out": tmp_path / "o"}
        ws["out"].mkdir()
        r = run("build_output.py", "--stage", STAGE, "--data-dir", ws["data"], "--state-dir", st, "--output", ws["out"] / DELIV, expect=(1,))
        assert "手改" in r.stderr and "L9.TM_ore_wt" in r.stderr

    def test_bare_number_slot_rejected(self, build_ws, tmp_path):
        """整槽位裸数值替换（非对象）→ rc=1 且消息含手改特征（非 AttributeError 崩溃）。"""
        import shutil

        st = tmp_path / "state"
        shutil.copytree(build_ws["state"], st)
        p = st / "formula_state.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["values"]["L9.TM_ore_wt"] = 339.92  # 模拟 agent 整槽位裸写
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        ws = {"data": build_ws["data"], "state": st, "out": tmp_path / "o"}
        ws["out"].mkdir()
        r = run("build_output.py", "--stage", STAGE, "--data-dir", ws["data"], "--state-dir", st, "--output", ws["out"] / DELIV, expect=(1,))
        assert "手改" in r.stderr and "L9.TM_ore_wt" in r.stderr


class TestDepthGate:
    def test_thin_section_rejected(self, build_ws, tmp_path):
        """三级节 <3 句 → rc=1 + 缺节清单（提示参照范文补写）。"""
        import shutil

        st = tmp_path / "state"
        shutil.copytree(build_ws["state"], st)
        (st / "chapters" / "ch3.md").write_text("## 3 矿区地质\n\n矿区出露地层为震旦系灯影组白云岩。\n\n### 3.1 地层\n\n落雪组是主要含矿层。\n", encoding="utf-8")
        ws = {"data": build_ws["data"], "state": st, "out": tmp_path / "o"}
        ws["out"].mkdir()
        r = run("build_output.py", "--stage", STAGE, "--data-dir", ws["data"], "--state-dir", st, "--output", ws["out"] / DELIV, expect=(1,))
        assert "深度门" in r.stderr and "3.1" in r.stderr

    def test_thin_chapter_chars_rejected(self, build_ws, tmp_path):
        """每块 ≥3 句但全章 <1000 有效字符 → rc=1。"""
        import shutil

        st = tmp_path / "state"
        shutil.copytree(build_ws["state"], st)
        three = "第一句明确。第二句完整。第三句收束。\n"
        (st / "chapters" / "ch3.md").write_text(f"## 3 矿区地质\n\n{three}\n\n### 3.1 地层\n\n{three}\n", encoding="utf-8")
        ws = {"data": build_ws["data"], "state": st, "out": tmp_path / "o"}
        ws["out"].mkdir()
        r = run("build_output.py", "--stage", STAGE, "--data-dir", ws["data"], "--state-dir", st, "--output", ws["out"] / DELIV, expect=(1,))
        assert "有效字符" in r.stderr

    def test_table_rows_not_counted_as_sentences(self, build_ws, tmp_path):
        """表格行不算句（| 开头）；有表格的块仍需 3 句叙述。"""
        import shutil

        st = tmp_path / "state"
        shutil.copytree(build_ws["state"], st)
        (st / "chapters" / "ch3.md").write_text("## 3 矿区地质\n\n第一句。第二句。第三句。\n\n### 3.1 表\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
        ws = {"data": build_ws["data"], "state": st, "out": tmp_path / "o"}
        ws["out"].mkdir()
        r = run("build_output.py", "--stage", STAGE, "--data-dir", ws["data"], "--state-dir", st, "--output", ws["out"] / DELIV, expect=(1,))
        assert "3.1" in r.stderr  # 表格块 0 句 → FAIL（表格不豁免叙述）

    def test_table_heavy_chapter_fails_eff_chars(self, build_ws, tmp_path):
        """M3 钉：每块 ≥3 句但有效字符量全靠表格行 → 有效字符 FAIL（表格不计入 eff）。"""
        import shutil

        st = tmp_path / "state"
        shutil.copytree(build_ws["state"], st)
        # 200 行×~7 有效字符：M3 突变（表格计入 eff）时 eff≈1500 ≥1000 → 门放行 rc=0 → 本测试转 RED——钉住排除逻辑；真代码 eff=36 <1000 → FAIL
        table = "\n".join(f"| 参数{i} | 数值{i} |" for i in range(200))
        three = "第一句明确。第二句完整。第三句收束。\n"
        (st / "chapters" / "ch3.md").write_text(f"## 3 矿区地质\n\n{three}\n\n### 3.1 表\n\n{three}\n{table}\n", encoding="utf-8")
        out = tmp_path / "o"
        out.mkdir()
        r = run("build_output.py", "--stage", STAGE, "--data-dir", build_ws["data"], "--state-dir", st, "--output", out / DELIV, expect=(1,))
        assert "有效字符" in r.stderr


# ── Task 5: 交付名门（bug-2223②：文件名规范 + outputs/ 无散文件）──────────────


class TestDeliverableNameGate:
    def test_wrong_name_rejected_with_expected(self, build_ws):
        """E2E 实测的违规名 01-10_完整报告.md → rc=1 + stderr 打印规范名。"""
        r = _build(build_ws, out_name="01-10_完整报告.md", expect=(1,))
        assert "交付名门" in r.stderr and DELIV in r.stderr

    def test_stray_md_in_outputs_rejected(self, build_ws):
        """outputs/ 出现管线外散 .md → rc=1 列出文件（交付回路铁律）。"""
        stray = build_ws["out"] / "ch1_绪论.md"
        stray.write_text("散文件", encoding="utf-8")
        try:
            r = _build(build_ws, expect=(1,))
            assert "散文件" in r.stderr and "ch1_绪论.md" in r.stderr
        finally:
            stray.unlink()

    def test_canonical_name_passes_idempotent(self, build_ws):
        """规范名两连 build：第二次 unchanged（幂等，门不破坏 SC-4）。"""
        _build(build_ws)
        r = _build(build_ws)
        assert "unchanged" in r.stdout


# ── bug-2225 Task 1: 交付契约标记（ingest 落 outputs/.delivery-contract）────────


class TestDeliveryContract:
    def test_ingest_plants_marker_in_ancestor_outputs(self, tmp_path):
        """本地沙箱布局：data 在 user-data/workspace/geo-report/data → 标记落 user-data/outputs。"""
        outputs = tmp_path / "user-data" / "outputs"
        outputs.mkdir(parents=True)
        data = tmp_path / "user-data" / "workspace" / "geo-report" / "data"
        r = run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data)
        marker = outputs / ".delivery-contract"
        assert marker.exists(), "契约标记必须落线程 outputs"
        assert json.loads(marker.read_text(encoding="utf-8"))["skill"] == "geological-report"
        assert "DELIVERY_CONTRACT" in r.stdout
        before = marker.read_text(encoding="utf-8")
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data)  # 幂等：内容不变
        assert marker.read_text(encoding="utf-8") == before

    def test_no_outputs_ancestor_is_noop(self, tmp_path):
        """祖先链无 outputs/ → 不落盘不报错（其他技能/纯测试目录零影响）。"""
        data = tmp_path / "geo" / "data"
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data)
        assert not list(tmp_path.rglob(".delivery-contract"))
