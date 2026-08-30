"""geological-report v2 六脚本测试矩阵（设计决策 5A 全矩阵；T5）。

规格: docs/superpowers/specs/2026-08-20-geological-report-v2-design.md

结构: 一个 session 级 fixture 跑通全链路（合成数据 forms→CSV→GATE1→manifest→
execute→impacted→chapters→build→consistency→snapshot→update，同冒烟脚本
Temp/geo_smoke/smoke.py），七类测试对产物逐项断言——管线任何一环断裂会让
整组测试变红（诚实信号）。CLI 全部 subprocess 调真实脚本，退出码语义
0/1/2/3 是被测合约的一部分。

运行: cd backend && PYTHONPATH=. uv run pytest tests/test_geological_report_v2_scripts.py -v
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "public" / "geological-report"
SCRIPTS = SKILL / "scripts"
STAGE = SKILL / "references/stages/exploration.json"
STANDARDS = SKILL / "references/standards_index.json"

sys.path.insert(0, str(SCRIPTS))


_FLOOR_TARGETS: Path | None = None


def _floor_targets() -> Path:
    """permissive targets（median 全 1 → L2 目标 <1 必过）：既有负例只测各自关心的门，不被 L2 截胡（真实 targets 于 Task 4 入库）。"""
    global _FLOOR_TARGETS
    if _FLOOR_TARGETS is None:
        d = Path(tempfile.mkdtemp(prefix="geo_floor_targets_"))
        _FLOOR_TARGETS = d / "floor.json"
        _FLOOR_TARGETS.write_text(
            json.dumps({"per_chapter": {f"ch{i}": {"median_eff": 1, "median_table_rows": 0, "median_paragraphs": 1} for i in range(1, 11)}}, ensure_ascii=False),
            encoding="utf-8",
        )
    return _FLOOR_TARGETS


def run(*args, expect=(0,)):
    """调真实 CLI；断言退出码 ∈ expect。返回 stdout。build_output 未显式传 --targets 时注入 permissive targets。"""
    argv = [str(SCRIPTS / args[0]), *map(str, args[1:])]
    if argv[0].endswith("build_output.py") and "--targets" not in argv:
        argv += ["--targets", str(_floor_targets())]
    r = subprocess.run([sys.executable, "-X", "utf8", *argv], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout[-800:]}\n{r.stderr[:400]}"
    return r.stdout


# ── 合成数据 + 全链路（每 session 一次） ─────────────────────────────────────


@pytest.fixture(scope="session")
def ws(tmp_path_factory):
    import ingest

    base = tmp_path_factory.mktemp("geov2")
    data, state, ind, out = base / "data", base / "state", base / "in", base / "out"
    for d in (data, state, ind, out, state / "chapters"):
        d.mkdir(parents=True, exist_ok=True)
    S = str(STAGE)
    D = str(data)

    run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data)

    def fill(fam, values):
        ingest.write_form_values(S, D, fam, values)

    def try_fill(fam, values):
        """类型不合 schema 的键逐个重试丢弃（合成数据只验管线不验内容）。"""
        try:
            fill(fam, values)
        except ValueError:
            for k in list(values):
                try:
                    fill(fam, {k: values[k]})
                except ValueError:
                    pass

    fill(
        "project",
        {
            "project_name": "东川区某铜银金多金属矿",
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
    fill("tenement", {"tenement_no": "T5300002023001", "tenement_type": "探矿权", "holder": "某矿业公司", "area_km2": 5.2})
    fill("industrial_params", {"boundary_grade_cu": 0.2, "min_industrial_grade_cu": 0.4, "min_mining_thickness": 1, "waste_exclusion_thickness": 2, "grade_variation_coeff_range": [40, 120], "outlier_multiple": 7, "deposit_avg_grade": 0.85})
    try_fill(
        "block_model",
        {
            "granularity": "A",
            "blocks": [
                {"orebody": "①", "block_no": "TM-1", "category": "TM", "grade_class": "工业", "area_s_m2": 10000, "avg_thickness_m": 2.0, "grade_c_pct": 0.50},
                {"orebody": "①", "block_no": "KZ-1", "category": "KZ", "grade_class": "工业", "area_s_m2": 20000, "avg_thickness_m": 1.5, "grade_c_pct": 0.45},
                {"orebody": "②", "block_no": "TD-1", "category": "TD", "grade_class": "低品位", "area_s_m2": 30000, "avg_thickness_m": 1.0, "grade_c_pct": 0.30},
            ],
        },
    )
    fill("prior_estimate", {"split_extent": {"332": {"ore_wt": 5.0, "metal_t": 250.0}, "333": {"ore_wt": 3.0, "metal_t": 140.0}}, "code_mapping": {"332": "KZ", "333": "TD"}})
    fill("verification", {"method": "块段面积权衡法", "rows": [{"orebody": "①", "category": "TM", "ore_qty_wt": 5.6, "metal_t": 280}]})
    try_fill("beneficiation", {"locked_cycle": {"feed_grade_cu": 0.47, "products": [{"name": "铜精矿", "yield": 2.55, "grade_cu": 15.7, "recovery_cu": 85.2}]}})
    try_fill(
        "hydro_eng_env",
        {
            "hydro.inflow_analogy": {"Q0_min": 908, "Q0_max": 5531, "F": 0.55, "F0": 0.30, "S": 3.0, "S0": 1.6},
            "type_verdicts": {
                "hydro_type": "岩溶裂隙弱-中等含水层充水为主、顶板直接充水简单类型",
                "engineering_type": "半坚硬-坚硬层状白云岩为主中等类型",
                "environment_type": "中等",
                "combined_type": "以工程、环境复合地质问题为主的中等类型",
            },
            "engineering.goaf": {"count": 422, "volume_wm3": 1383.95},
        },
    )
    fill(
        "economics",
        {
            "credibility": {"TM": 1.0, "KZ": 1.0, "TD": 0.6},
            "rates": {"loss_rate": 10, "dilution_rate": 8},
            "recovery": {"recovery_cu": 85},
            "concentrate": {"grade_cu_pct": 17.46, "grade_ag_gpt": 98.07},
            "prices": {"cu_yuan_t": 51000, "ag_yuan_kg": 3500},
            "costs": {"mining_yuan_t": 45, "beneficiation_yuan_t": 60, "other_yuan_t": 20.75},
            "capacity_10kt_a": 80,
        },
    )
    try_fill("figures_tables", {"figures": [{"no": "附图1", "title": "交通位置图", "scale": "1:50000"}], "tables": [{"no": "附表1", "title": "勘查工程坐标表"}]})
    # 其余必填按 schema 类型自动占位
    _stage = json.loads(STAGE.read_text(encoding="utf-8"))

    def ph(f):
        t = f.get("type", "string")
        if t.startswith("enum:"):
            return t[5:].split("|")[0]
        return {"number": 1.0, "integer": 1, "bool": True}.get(t, [{"占位": 1}] if t.startswith("array") else {"占位": 1} if t == "object" else "占位")

    for fam, spec in _stage["forms"].items():
        if spec.get("format") == "csv" or "columns" in spec:
            continue
        p = data / spec["file"]
        doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        obj_names = {g["name"] for g in spec.get("fields", []) if g.get("type") == "object"}
        need = {
            f["name"]: ph(f)
            for f in spec.get("fields", [])
            if f.get("required", True)
            and doc.get(f["name"]) in (None, "", [], {})
            and not ("." in f["name"] and f["name"].partition(".")[0] in obj_names)
        }  # F5(C6b): 仅跳过可归并点分子键——ph 占位 1.0 经 _expand_dotted 深合并会覆盖已真填的嵌套值；
        # hydro 族扁平点分键（前缀不命中 object 字段名）照常占位落盘
        if need:
            fill(fam, need)

    # CSV 乱序列 → file 子命令列匹配入库
    (ind / "density.csv").write_text(
        "湿度_pct,样品编号,体重_t_m3,矿石类型,品位Cu_pct,序号,送样编号\n"
        "2.0,s1,2.80,氧化矿,0.50,1,S-1\n2.5,s2,2.90,硫化矿,0.60,2,S-2\n"
        "1.5,s3,2.70,氧化矿,0.30,3,S-3\n1.2,s4,2.65,硫化矿,0.25,4,S-4\n"
        "1.0,s5,2.60,氧化矿,0.10,5,S-5\n1.0,s6,3.00,硫化矿,6.00,6,S-6\n",
        encoding="utf-8",
    )
    run("ingest.py", "file", "--stage", STAGE, "--data-dir", data, "--input", ind / "density.csv", "--family", "bulk_density", expect=(0, 3))
    (ind / "assays.csv").write_text(
        "品位Ag_gpt,备注,品位Cu_pct,样长_m,止深度_m,起深度_m,样品编号,矿体编号,工程类型,工程号\n"
        "8.0,,0.45,1.2,120.0,118.8,A-1,①,钻孔,ZK101\n9.0,,0.50,1.0,121.0,120.0,A-2,①,钻孔,ZK101\n7.5,,0.42,0.8,122.0,121.2,A-3,①,钻孔,ZK101\n"
        "10.0,,0.55,1.5,200.0,198.5,B-1,①,钻孔,ZK102\n8.5,,0.48,1.0,201.0,200.0,B-2,①,钻孔,ZK102\n5.0,,0.30,0.5,202.0,201.5,B-3,①,钻孔,ZK102\n",
        encoding="utf-8",
    )
    run("ingest.py", "file", "--stage", STAGE, "--data-dir", data, "--input", ind / "assays.csv", "--family", "sample_assays", expect=(0, 3))

    gate1 = run("ingest.py", "check", "--stage", STAGE, "--data-dir", data)
    run("chapter_planner.py", "manifest", "--stage", STAGE, "--output", state / "chapter_manifest.json")
    run("formula_runner.py", "execute", "--stage", STAGE, "--data-dir", data, "--output", state / "formula_state.json", expect=(0, 3))
    formula_state_pre = json.loads((state / "formula_state.json").read_text(encoding="utf-8"))

    run(
        "formula_runner.py",
        "impacted",
        "--stage",
        STAGE,
        "--data-dir",
        data,
        "--state",
        state / "formula_state.json",
        "--field",
        "13a:体重_t_m3",
        "--value",
        "2.90",
        "--manifest",
        state / "chapter_manifest.json",
        "--output",
        state / "impacted.json",
    )

    # 章节（LLM 叙述产物模拟：槽位 + 表 + 段内序号 + 判定词逐字 + 历史编码 332）
    slot = lambda k: "{{SLOT:" + k + "}}"  # noqa: E731
    # 章节合规内容（bug-2223 深度门：每块 ≥3 句 + 每章 ≥1000 有效字符；槽位引用保留原断言能力）
    # SEC 合成凑量同 bug2223 fixture：2 句×64字 ×12 重复 = 24句/768字/块，每章 2 块+叙述句 ≈1536+ 有效字符（ch8 仅 1 块→SEC 双份 ≈1780；合成数据只验管线）
    SEC = "本段叙述勘查工作部署与质量情况，内容完整表述规范，满足深度门要求。每次工程布置依据充分且间距合理，资料经检查验收合格可用于估算。"
    SEC *= 12
    chapters = {
        1: f"## 1 绪论\n\n{SEC}\n\n本次勘查共获得工业矿石量 {slot('L9.total_ore_wt')} 万吨。\n\n### 1.1 目的任务\n\n（1）查明矿体特征。（2）估算资源量。（3）评价开采技术条件。\n\n### 1.2 工作部署\n\n{SEC}\n",
        2: f"## 2 区域地质\n\n{SEC}\n\n区域大地构造位置属扬子板块西缘。（1）地层。（2）构造。（3）岩浆岩。\n\n### 2.1 区域地层\n\n{SEC}\n",
        3: f"## 3 矿区地质\n\n{SEC}\n\n矿区出露地层为震旦系灯影组白云岩。\n\n### 3.1 矿区地层\n\n{SEC}\n",
        4: f"## 4 矿体\n\n{SEC}\n\n①号矿体平均品位 {slot('L8.C_orebody[①]')}%。特高品位下限取 {slot('C9.outlier_threshold')}%。\n\n### 4.1 矿体特征\n\n{SEC}\n",
        5: f"## 5 矿石加工选冶技术性能\n\n{SEC}\n\n闭路试验铜精矿回收率 {slot('B1.recovery[铜精矿]')}%。\n\n### 5.1 选矿试验\n\n{SEC}\n",
        6: (
            "## 6 矿床开采技术条件\n\n" + SEC + "\n\n坑道正常涌水量 " + slot("W1.Q_min") + "～" + slot("W1.Q_max") + " m3/d。老窑采空区 422 个、体积 1383.95 万 m3，"
            "水文地质类型为岩溶裂隙弱-中等含水层充水为主、顶板直接充水简单类型；"
            "工程地质类型为半坚硬-坚硬层状白云岩为主中等类型；"
            "复合类型为以工程、环境复合地质问题为主的中等类型。\n\n### 6.1 水文地质\n\n" + SEC + "\n"
        ),
        7: f"## 7 勘查工作及其质量评述\n\n{SEC}\n\n小体重样 {slot('S1.n')} 件，平均体重 {slot('S1.avg_density')} t/m3。\n\n### 7.1 质量评述\n\n{SEC}\n",
        8: (
            "## 8 资源量估算\n\n"
            + SEC
            + SEC
            + "\n\n工业矿石量 "
            + slot("L9.total_ore_wt")
            + " 万吨、金属量 "
            + slot("L9.total_metal_t")
            + " t、平均品位 "
            + slot("L9.total_grade")
            + "%。其中探明资源量 "
            + slot("L9.TM_ore_wt")
            + " 万吨、控制资源量 "
            + slot("L9.KZ_ore_wt")
            + " 万吨。历史备案（332）保有 5.0 万吨。\n\n### 8.1 伴生组分\n\n伴生银品位 "
            + slot("L11.ag_grade")
            + " g/t。\n\n组合样分析结果显示伴生组分分布均匀，品位稳定，可在冶炼过程中综合回收。选矿试验闭路流程顺畅，指标稳定，表格试验数据如下。\n\n{{{{TABLE:bulk_density}}}}\n"
        ),
        9: f"## 9 经济评价\n\n{SEC}\n\n精矿含铜价格 {slot('E4.price_conc')} 元/t，潜在总值 {slot('E5.gross_potential_yi')} 亿元。\n\n### 9.1 概略评价\n\n{SEC}\n",
        10: f"## 10 结论\n\n{SEC}\n\n本次估算工业矿石量 {slot('L9.total_ore_wt')} 万吨，与正文第 1、8 章一致。\n\n### 10.1 主要成果\n\n{SEC}\n",
    }
    # bug-2225 目录覆盖门：补齐 STAGE toc 全部节号骨架（手写章节保留槽位/断言内容）
    _num_re = re.compile(r"\d+\.\d+(?:\.\d+)?")
    _heading_re = re.compile(r"^#{2,4}\s+(\d+(?:\.\d+)+)")
    for n, md in list(chapters.items()):
        have = {m.group(1) for ln in md.splitlines() if (m := _heading_re.match(ln.strip()))}
        extra = []
        for sub in _stage["chapters"][f"ch{n}"].get("toc", []):
            for no in _num_re.findall(sub):
                if no in have:
                    continue
                have.add(no)
                extra.append(f"{'###' if no.count('.') == 1 else '####'} {no} 小节\n\n{SEC}")
        if extra:
            chapters[n] = md.rstrip("\n") + "\n\n" + "\n\n".join(extra) + "\n"
    for n, md in chapters.items():
        (state / "chapters" / f"ch{n}.md").write_text(md, encoding="utf-8")

    DELIV = f"{json.loads((data / '00_project.json').read_text(encoding='utf-8')).get('project_name', '东川区某铜银金多金属矿')}-勘探-地质勘查报告.md"
    # （project_name 在 Step 之前已 fill 为 "东川区某铜银金多金属矿"；DELIV 即 "东川区某铜银金多金属矿-勘探-地质勘查报告.md"）
    build1 = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", out / DELIV)
    build2 = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", out / DELIV)

    # 负例：未知槽位 → rc=1 阻断（输出名保持规范名，隔离槽位门本身）
    bad = state / "chapters" / "ch10.md"
    orig10 = bad.read_text(encoding="utf-8")
    bad.write_text(orig10 + "\n未知 {{SLOT:XX.noexist}}\n", encoding="utf-8")
    run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", out / DELIV, expect=(1,))
    bad.write_text(orig10, encoding="utf-8")

    cc = run("consistency.py", "--report", out / DELIV, "--data-dir", data, "--stage", STAGE, "--state", state / "formula_state.json", "--standards", STANDARDS, "--output", state / "consistency_check.json", expect=(0, 2, 3))

    run(
        "snapshot.py",
        "save",
        "--task",
        "测试: 初版生成",
        "--stage",
        "勘探",
        "--data-dir",
        data,
        "--state-dir",
        state,
        "--state-manifest",
        data / "state_manifest.json",
        "--formula-state",
        state / "formula_state.json",
        "--manifest",
        state / "chapter_manifest.json",
        "--report",
        out / DELIV,
        "--output",
        out / "project_snapshot.json",
    )
    verify_ok = run("snapshot.py", "show", "--input", out / "project_snapshot.json", "--verify")
    csv_path = data / "13a_bulk_density.csv"
    orig_csv = csv_path.read_text(encoding="utf-8")
    csv_path.write_text(orig_csv.replace("2.80", "2.81"), encoding="utf-8")
    run("snapshot.py", "show", "--input", out / "project_snapshot.json", "--verify", expect=(3,))
    csv_path.write_text(orig_csv, encoding="utf-8")

    # update 顺序铁律负例：impacted-file 不存在 → rc=1
    run(
        "formula_runner.py",
        "update",
        "--stage",
        STAGE,
        "--data-dir",
        data,
        "--state",
        state / "formula_state.json",
        "--field",
        "13.outlier_multiple",
        "--value",
        "8",
        "--impacted-file",
        state / "nope.json",
        "--output",
        state / "fs2.json",
        expect=(1,),
    )
    # 真链路：impacted → update → C9 5.95→6.80
    run(
        "formula_runner.py",
        "impacted",
        "--stage",
        STAGE,
        "--data-dir",
        data,
        "--state",
        state / "formula_state.json",
        "--field",
        "13.outlier_multiple",
        "--value",
        "8",
        "--manifest",
        state / "chapter_manifest.json",
        "--output",
        state / "imp2.json",
    )
    upd = run(
        "formula_runner.py",
        "update",
        "--stage",
        STAGE,
        "--data-dir",
        data,
        "--state",
        state / "formula_state.json",
        "--field",
        "13.outlier_multiple",
        "--value",
        "8",
        "--impacted-file",
        state / "imp2.json",
        "--output",
        state / "formula_state.json",
        expect=(0, 3),
    )

    return {
        "base": base,
        "data": data,
        "state": state,
        "out": out,
        "deliv": DELIV,
        "gate1": gate1,
        "build1": build1,
        "build2": build2,
        "cc": cc,
        "verify_ok": verify_ok,
        "upd": upd,
        "formula_state": formula_state_pre,
        "formula_state_post": json.loads((state / "formula_state.json").read_text(encoding="utf-8")),
        "impacted": json.loads((state / "impacted.json").read_text(encoding="utf-8")),
        "consistency": json.loads((state / "consistency_check.json").read_text(encoding="utf-8")),
        "report_md": (out / DELIV).read_text(encoding="utf-8"),
        "manifest": json.loads((state / "chapter_manifest.json").read_text(encoding="utf-8")),
    }


# ── 1. ingest：门1 + CSV 列匹配 + 字段名校验 ────────────────────────────────


class TestIngest:
    def test_gate1_complete(self, ws):
        assert "GATE1_COMPLETE" in ws["gate1"]

    def test_csv_column_matching(self, ws):
        """乱序列 CSV 入库后按 schema 规范列序落盘。"""
        header = (ws["data"] / "13a_bulk_density.csv").read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",")[0] == "序号" or "体重_t_m3" in header

    def test_typo_field_rejected(self, ws, tmp_path):
        import ingest

        with pytest.raises(ValueError):
            ingest.write_form_values(str(STAGE), str(ws["data"]), "project", {"project_nme": "x"})

    def test_gate1_missing_required_rc2(self, tmp_path):
        """空白表单（仅生成未填值）→ 门1 rc=2 列缺项。"""
        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        run("ingest.py", "check", "--stage", STAGE, "--data-dir", d, expect=(2,))

    def test_check_list_shaped_doc_no_crash(self, tmp_path):
        """bug-3004: 清单族文件顶层为行数组（CSV 摄入形状，如 08_orebody_list）时
        check 曾崩溃 AttributeError: 'list' object has no attribute 'get'——
        agent 据此误判「数据损坏」转而手写 data/。行数组按非空判完备。"""
        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        (d / "01_tenement.json").write_text(json.dumps([{"矿权编号": "T-1"}, {"矿权编号": "T-2"}]), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "ingest.py"), "check", "--stage", str(STAGE), "--data-dir", str(d)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert "AttributeError" not in r.stdout + r.stderr, f"list 顶层 doc 不应崩溃\n{r.stdout[-500:]}\n{r.stderr[:300]}"
        assert r.returncode == 2  # 其余空白表单仍报缺项
        assert "tenement" not in r.stdout  # 非空行数组 → 该族视为就绪，不列缺
        (d / "01_tenement.json").write_text("[]", encoding="utf-8")
        out = run("ingest.py", "check", "--stage", STAGE, "--data-dir", d, expect=(2,))
        assert "tenement" in out  # 空清单仍要报缺

    def test_null_required_field_passthrough(self, tmp_path):
        """bug-2216: 必填字段 null 直通写入（部分收集落盘），门1 仍报缺——
        写入路径若拒绝 null，agent 会被迫用 0/示例值填结构冒充（页面实测）。"""
        import ingest

        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        ingest.write_form_values(str(STAGE), str(d), "tenement", {"tenement_no": "T-1", "holder": None})
        doc = json.loads((d / "01_tenement.json").read_text(encoding="utf-8"))
        assert doc["tenement_no"] == "T-1" and doc["holder"] is None
        out = run("ingest.py", "check", "--stage", STAGE, "--data-dir", d, expect=(2,))
        assert "holder" in out

    def test_empty_values_rejected_no_wipe(self, tmp_path):
        """bug-2217: --values 空串（$(cat 不存在文件) 静默展开）必须报错退出，
        绝不落入空白生成路径把已收集数据清掉（页面实测 21 表单全灭）。"""
        import ingest

        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        ingest.write_form_values(str(STAGE), str(d), "tenement", {"tenement_no": "T-1"})
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "ingest.py"), "forms", "--stage", str(STAGE), "--data-dir", str(d), "--family", "tenement", "--force", "--values", ""],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 1, f"空 --values 应报错\n{r.stdout}\n{r.stderr}"
        assert json.loads((d / "01_tenement.json").read_text(encoding="utf-8"))["tenement_no"] == "T-1"

    def test_force_requires_scope(self, tmp_path):
        """bug-2217: 无 --only/--family 的 --force 会整目录重置空白——必须拒绝。"""
        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "ingest.py"), "forms", "--stage", str(STAGE), "--data-dir", str(d), "--force"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 1 and "--force" in r.stderr

    def test_force_scoped_to_family(self, tmp_path):
        """bug-2217: --family X --force 只重置 X 族，其余族已收集数据保留
        （此前空白生成路径无视 --family，21 张表单全被重置）。"""
        import ingest

        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        ingest.write_form_values(str(STAGE), str(d), "tenement", {"tenement_no": "T-1"})
        ingest.write_form_values(str(STAGE), str(d), "project", {"project_name": "P"})
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d, "--family", "tenement", "--force")
        assert json.loads((d / "01_tenement.json").read_text(encoding="utf-8"))["tenement_no"] is None
        assert json.loads((d / "00_project.json").read_text(encoding="utf-8"))["project_name"] == "P"


class TestIngestDotted:
    """F5: economics 对象族拆平——点分子键经 _expand_dotted 深合并为嵌套 dict，
    消灭「子键无权威名→agent 猜键→formula_runner .get(k,0) 静默 0」的错误数值通道。"""

    def test_ingest_forms_dotted_keys_expand_to_nested(self, tmp_path):
        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        run(
            "ingest.py", "forms", "--stage", STAGE, "--data-dir", d, "--family", "economics",
            "--values", json.dumps({"prices.cu_yuan_t": 51000, "prices.ag_yuan_kg": 3500, "rates.loss_rate": 15, "costs.other_yuan_t": 20.75}, ensure_ascii=False),
        )
        doc = json.loads((d / "16_economics.json").read_text(encoding="utf-8"))
        assert doc["prices"]["cu_yuan_t"] == 51000
        assert "prices.cu_yuan_t" not in doc  # 顶层不留扁平点分键
        # 第二批补答（指标+可信度）：深合并——第一批子键必须仍在
        run(
            "ingest.py", "forms", "--stage", STAGE, "--data-dir", d, "--family", "economics",
            "--values", json.dumps({"credibility.TM": 1.0, "credibility.KZ": 1.0, "credibility.TD": 0.6, "rates.dilution_rate": 10}, ensure_ascii=False),
        )
        doc = json.loads((d / "16_economics.json").read_text(encoding="utf-8"))
        assert doc["prices"]["cu_yuan_t"] == 51000
        assert doc["rates"]["loss_rate"] == 15 and doc["rates"]["dilution_rate"] == 10
        assert doc["credibility"] == {"TM": 1.0, "KZ": 1.0, "TD": 0.6}

    def test_ingest_forms_nested_object_still_accepted(self, tmp_path):
        """回归守卫：顶层整对象传法（存量合约，ws 夹具即此形状）保持合法且落盘形状不变。"""
        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d, "--family", "economics", "--values", '{"prices": {"cu_yuan_t": 51000}}')
        doc = json.loads((d / "16_economics.json").read_text(encoding="utf-8"))
        assert doc["prices"] == {"cu_yuan_t": 51000}

    def test_ingest_forms_dotted_unknown_key_rejected(self, tmp_path):
        """未知点分键 rc=1（不在 schema 字段清单）——猜键在写入层即被拦，不再静默丢字段。"""
        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "ingest.py"), "forms", "--stage", str(STAGE), "--data-dir", str(d), "--family", "economics", "--values", '{"prices.cu_typo": 1}'],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert r.returncode == 1 and "不在 schema 字段清单" in r.stderr, f"{r.stdout}\n{r.stderr}"

    def test_ingest_hydro_dotted_stays_flat(self, tmp_path):
        """锁归并判据：hydro 前缀不命中任何 object 字段名 → 保持扁平键落盘（formula_runner 合约）。"""
        import ingest

        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        hv = {"Q0_min": 908, "Q0_max": 5531, "F": 0.55, "F0": 0.30, "S": 3.0, "S0": 1.6}
        ingest.write_form_values(str(STAGE), str(d), "hydro_eng_env", {"hydro.inflow_analogy": hv})
        doc = json.loads((d / "11_hydro_eng_env.json").read_text(encoding="utf-8"))
        assert doc["hydro.inflow_analogy"] == hv  # 扁平
        assert not isinstance(doc.get("hydro"), dict)  # 未被误归并为嵌套

    def test_ingest_check_missing_dotted_subkey_reports(self, tmp_path):
        """门1 缺项走查到逐子字段：只填部分子键 → rc=2 且点名 economics.prices.ag_yuan_kg。"""
        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d, "--family", "economics", "--values", '{"prices.cu_yuan_t": 51000}')
        out = run("ingest.py", "check", "--stage", STAGE, "--data-dir", d, expect=(2,))
        assert "economics.prices.ag_yuan_kg" in out
        assert "economics.concentrate.grade_cu_pct" in out

    def test_formula_runner_e4_from_dotted_ingest(self, tmp_path):
        """端到端锁死 E4=0 缺陷：点分路径落盘 → execute → E4.price_conc > 0。"""
        import ingest

        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        ingest.write_form_values(
            str(STAGE), str(d), "industrial_params",
            {"boundary_grade_cu": 0.2, "min_industrial_grade_cu": 0.4, "min_mining_thickness": 1, "waste_exclusion_thickness": 2, "grade_variation_coeff_range": [40, 120], "outlier_multiple": 7, "deposit_avg_grade": 0.85},
        )
        ingest.write_form_values(
            str(STAGE), str(d), "block_model",
            {"granularity": "A", "blocks": [{"orebody": "①", "block_no": "TM-1", "category": "TM", "grade_class": "工业", "area_s_m2": 10000, "avg_thickness_m": 2.0, "grade_c_pct": 0.5, "bulk_density": 2.85}]},
        )
        run(
            "ingest.py", "forms", "--stage", STAGE, "--data-dir", d, "--family", "economics",
            "--values",
            json.dumps(
                {
                    "prices.cu_yuan_t": 51000, "prices.ag_yuan_kg": 3500,
                    "concentrate.grade_cu_pct": 17.46, "concentrate.grade_ag_gpt": 98.07,
                    "credibility.TM": 1.0, "credibility.KZ": 1.0, "credibility.TD": 0.6,
                    "rates.loss_rate": 15, "rates.dilution_rate": 10,
                    "costs.mining_yuan_t": 45, "costs.beneficiation_yuan_t": 60, "costs.other_yuan_t": 20.75,
                    "capacity_10kt_a": 80,
                },
                ensure_ascii=False,
            ),
        )
        state = d.parent / "state"
        state.mkdir()
        run("formula_runner.py", "execute", "--stage", STAGE, "--data-dir", d, "--output", state / "formula_state.json", expect=(0, 3))
        V = json.loads((state / "formula_state.json").read_text(encoding="utf-8"))["values"]
        assert float(V["E4.price_conc"]["value"]) > 8000  # 51000×17.46/100 + 3500/1000×98.07 ≈ 9247.8

    def test_exploration_schema_economics_flattened(self):
        """schema 静态断言：economics 每个 object 父条目必有非空 fields 子清单（recovery 不再裸奔），
        且每个子键存在对应点分字段条目（ask_clarification 可逐子字段发问）。"""
        stage = json.loads(STAGE.read_text(encoding="utf-8"))
        fields = stage["forms"]["economics"]["fields"]
        names = {f["name"] for f in fields}
        for f in fields:
            if f.get("type") == "object":
                assert f.get("fields"), f"object 条目 {f['name']} 缺子键清单"
                for sub in f["fields"]:
                    assert f"{f['name']}.{sub}" in names, f"缺点分条目 {f['name']}.{sub}"

    def test_stage_bare_name_resolves(self, tmp_path):
        """bug-2217: 裸名 'exploration' 自动补全到内置 stages 路径，
        不再抛 FileNotFoundError 裸 traceback；不存在的名字给可读错误。"""
        d = tmp_path / "d"
        d.mkdir()
        out = run("ingest.py", "forms", "--stage", "exploration", "--data-dir", d)
        assert "FORMS_READY" in out
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "ingest.py"), "forms", "--stage", "nonexistent_stage", "--data-dir", str(d)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 1 and "找不到阶段 schema" in r.stderr

    def test_parallel_writes_manifest_consistency(self, tmp_path):
        """bug-2217: 并行 ingest 进程共享 .tmp 名 → os.replace FileNotFoundError、
        manifest load-modify-write 丢条目。修复 = pid 唯一 tmp + manifest 互斥锁。"""
        d = tmp_path / "d"
        d.mkdir()
        run("ingest.py", "forms", "--stage", STAGE, "--data-dir", d)
        jobs = [
            ("tenement", {"tenement_no": "T-1"}),
            ("project", {"project_name": "P"}),
            ("geography", {"location_text": "L"}),
        ]
        procs = [
            subprocess.Popen(
                [sys.executable, "-X", "utf8", str(SCRIPTS / "ingest.py"), "forms", "--stage", str(STAGE), "--data-dir", str(d), "--family", fam, "--values", json.dumps(vals, ensure_ascii=False)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for fam, vals in jobs
        ]
        for fam, p in zip(jobs, procs):
            _, err = p.communicate()
            assert p.returncode == 0, f"{fam[0]} 并行写失败:\n{err.decode('utf-8', 'replace')}"
        m = json.loads((d / "state_manifest.json").read_text(encoding="utf-8"))
        for fname in ("01_tenement.json", "00_project.json", "04_geography.json"):
            assert fname in m["files"], f"manifest 丢条目: {fname}"


# ── 2. formula_runner：冻结计算 + 锚点 + ROUND_HALF_EVEN 红线 ───────────────


ANCHORS = {
    "C9.outlier_threshold": 5.95,
    "S1.avg_density": 2.76,
    "S1.avg_density_industrial": 2.85,
    "S1.avg_density_low": 2.68,
    "S1.n": 4,
    "L9.total_ore_wt": 14.25,
    "L9.total_metal_t": 670,
    "L9.TM_ore_wt": 5.70,
    "L9.KZ_ore_wt": 8.55,
    "L9.total_grade": 0.47,
    "L11.ag_grade": 8.75,
    "W1.Q_min": 2279,
    "E1.Q_usable_wt": 14.25,
    "E2.Q_mined_wt": 12.82,
    "E4.price_conc": 9248,
    "E5.gross_potential_yi": 0.41,  # bug-3051 锚：银项 /WAN 后 (0.067*51000 + 1948*3500/1e4)/1e4 ≈ 0.41（修前虚高 1e4 倍 = 682.14）
    "E7.years_added": 0.2,
    "B1.recovery[铜精矿]": 85.18,
}


class TestFormulaRunner:
    def test_execute_anchors(self, ws):
        for k, want in ANCHORS.items():
            got = ws["formula_state"]["values"].get(k, {}).get("value")
            assert got is not None and abs(got - want) < 0.006, f"{k}: got {got} want {want}"
        # update 真链路后 C9 已推进到 6.80（顺序铁律测试用 post 快照断言）

    def test_check_and_trace(self, ws):
        """check 锚点对当前盘上状态。C9=6.80 静态锚锁 update 级联：阈值 5.95→6.80
        重新纳入 s6 样(6.00<6.80) → S1 体重变 → L9 14.25→14.5（真级联，非回归）。"""
        anchors = {"C9.outlier_threshold": 6.80, "L9.total_ore_wt": ws["formula_state_post"]["values"]["L9.total_ore_wt"]["value"]}
        run("formula_runner.py", "check", "--stage", STAGE, "--data-dir", ws["data"], "--state", ws["state"] / "formula_state.json", "--anchors", json.dumps(anchors))
        run("formula_runner.py", "trace", "--state", ws["state"] / "formula_state.json", "--formulas", SKILL / "references/formulas.json", "--output", ws["state"] / "traces.json")

    def test_round_half_even(self):
        """银行家舍入红线：禁 float round（bug 系：数值一致性 SC-4）。q 的 dp 是 '0.01' 格式。"""
        import formula_runner as fr

        q = fr.q
        assert q(Decimal("2.675"), "0.01") == Decimal("2.68")  # 7 奇 → 远端偶
        assert q(Decimal("2.665"), "0.01") == Decimal("2.66")  # 6 偶 → 就近偶
        assert q(Decimal("0.125"), "0.01") == Decimal("0.12")

    def test_impacted_value_diff(self, ws):
        """值差分：D 改变 → 真 dependents 变；L8 品位=Σm/Σo 对 D 尺度不变（数学性质）。"""
        aff = set(ws["impacted"]["affected_formulas"])
        assert {"L9", "E1", "S1", "L11"} <= aff
        assert "L8" not in aff, "L8 对 D 尺度不变——若出现说明差分实现有误"

    def test_update_guard_and_chain(self, ws):
        assert "CHANGED_FORMULAS" in ws["upd"] and "C9" in ws["upd"]
        v = ws["formula_state_post"]["values"]["C9.outlier_threshold"]["value"]
        assert abs(v - 6.80) < 0.006, f"C9 应 5.95→6.80, got {v}"


# ── 3. stage schema：sections 逐节要素链与 toc 对齐（bug-2221 骨架防漂移）─────


class TestStageSections:
    def test_sections_cover_toc(self):
        """每章 toc 的全部二/三级节号必须存在于 sections 要素链（wave1 按节写作的数据前提）。"""
        import re

        num_re = re.compile(r"\d+\.\d+(?:\.\d+)?")
        stage = json.loads(STAGE.read_text(encoding="utf-8"))
        for ch_id, ch in stage["chapters"].items():
            toc_nos = {m for sub in ch.get("toc", []) for m in num_re.findall(sub)}
            sec_nos = {s["no"] for s in ch.get("sections", [])}
            assert toc_nos, f"{ch_id}: toc 未解析出节号"
            assert sec_nos == toc_nos, f"{ch_id}: sections↔toc 不对齐: {sorted(sec_nos ^ toc_nos)}"
            for s in ch["sections"]:
                assert len(s["elements"]) >= 2, f"{ch_id} {s['no']}: elements 过少"


# ── 3b. chapter_planner：manifest + 三路反查 ────────────────────────────────


class TestChapterPlanner:
    def test_manifest_covers_stage_chapters(self, ws):
        ids = {c["id"] if isinstance(c, dict) else c for c in ws["manifest"].get("chapters", [])} if isinstance(ws["manifest"].get("chapters"), list) else set(ws["manifest"].get("chapters", {}))
        assert any("ch8" == i or "8" in str(i) for i in ids) if ids else ws["manifest"]

    def test_impacted_chapters_include_dependents(self, ws):
        """公式∩chapter ∪ 表单族 ∪ 合约覆盖 → ch8/ch10/合规附录必在。"""
        assert {"ch8", "ch10", "compliance_appendix"} <= set(ws["impacted"]["affected_chapters"])


# ── 4. build_output：注入 + 幂等 + 负例 ─────────────────────────────────────


class TestEffectiveChars:
    """eff 口径单一来源：标题行/表格行/装饰符剔除（calibrate 与 L0/L2 门共用）。"""

    def test_excludes_headings_tables_and_decorations(self):
        import build_output

        text = "## 1 绪论\n\n正文第一句。正文第二句；正文第三句！\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- 要点：符号-与*#:{}剔除\n"
        # 18 = 三句正文（。；！ 保留）；8 = 「要点：符号与剔除」（全角：保留，ASCII - * # : { } 与空白剔除）
        assert build_output.effective_chars(text) == 26


class TestCalibrate:
    """calibrate.py：样例 → depth_targets.json（确定性幂等；无节号样例 rc=1 拒产）。"""

    @staticmethod
    def _mini_samples(base):
        d = base / "samples"
        d.mkdir()
        (d / "ch1_sample.md").write_text(
            "## 1 绪论\n\n### 1.1 目的目的\n\n本次勘查目的明确。任务安排合理。经费保障到位。\n\n| 项目 | 数量 |\n|---|---|\n| 钻探 | 1000 |\n",
            encoding="utf-8",
        )
        (d / "ch2_sample.md").write_text("## 2 区域地质\n\n### 2.1 地层\n\n区域地层出露齐全。由老至新分述。各岩性组特征各异。\n", encoding="utf-8")
        (d / "source.md").write_text("来源说明，非样例，须被过滤。\n", encoding="utf-8")
        return d

    @staticmethod
    def _run(*argv):
        return subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "calibrate.py"), *map(str, argv)], capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_mini_targets_deterministic(self, tmp_path):
        d = self._mini_samples(tmp_path)
        out1, out2 = tmp_path / "t1.json", tmp_path / "t2.json"
        for out in (out1, out2):
            r = self._run("--samples-dir", d, "--output", out)
            assert r.returncode == 0, r.stderr
        assert out1.read_bytes() == out2.read_bytes()
        doc = json.loads(out1.read_text(encoding="utf-8"))
        assert (doc["coefficient"], doc["scale_floor"], doc["per_signal_penalty"], doc["missing_table_weight"]) == (0.6, 0.25, 0.05, 8)
        assert set(doc["per_chapter"]) == {"ch1", "ch2"}  # source.md 被过滤
        assert doc["per_chapter"]["ch1"] == {"median_eff": 23, "median_table_rows": 2, "median_paragraphs": 1}
        assert doc["per_chapter"]["ch2"] == {"median_eff": 25, "median_table_rows": 0, "median_paragraphs": 1}

    def test_sample_without_numbered_headings_rc1(self, tmp_path):
        d = tmp_path / "samples"
        d.mkdir()
        (d / "ch1_sample.md").write_text("# 概述\n\n没有节号标题的文档。\n", encoding="utf-8")
        r = self._run("--samples-dir", d, "--output", tmp_path / "t.json")
        assert r.returncode == 1 and "ch1_sample.md" in r.stderr, r.stderr
        assert not (tmp_path / "t.json").exists()  # 绝不静默产出空 targets


class TestDepthTargetGate:
    """L2 深度目标门（spec 2026-08-25 §4）：eff ≥ median×0.6×覆盖缩放；缺 targets 回退地板门。"""

    @staticmethod
    def _targets(tmp_path, ch="ch2", median_eff=999999):
        p = tmp_path / "tg.json"
        p.write_text(
            json.dumps({"coefficient": 0.6, "scale_floor": 0.25, "per_signal_penalty": 0.05, "missing_table_weight": 8, "per_chapter": {ch: {"median_eff": median_eff, "median_table_rows": 0, "median_paragraphs": 1}}}, ensure_ascii=False),
            encoding="utf-8",
        )
        return p

    @staticmethod
    def _build(ws, st, out, targets=None):
        argv = [sys.executable, "-X", "utf8", str(SCRIPTS / "build_output.py"), "--stage", str(STAGE), "--data-dir", str(ws["data"]), "--state-dir", str(st), "--output", str(out)]
        if targets is not None:
            argv += ["--targets", str(targets)]
        return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_thin_chapter_fail(self, ws, tmp_path):
        """数据齐全但薄：scale=1，eff < median×0.6 → FAIL，报错含公式因子与覆盖缩放。"""
        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        r = self._build(ws, st, tmp_path / ws["deliv"], self._targets(tmp_path, "ch2", 999999))
        assert r.returncode == 1 and "深度目标门" in r.stderr and "覆盖缩放" in r.stderr, r.stderr

    def test_met_target_pass(self, ws, tmp_path):
        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        r = self._build(ws, st, tmp_path / ws["deliv"], self._targets(tmp_path, "ch2", 100))
        assert r.returncode == 0 and "BUILD_READY" in r.stdout, r.stderr

    def test_missing_targets_fallback_floor(self, ws, tmp_path):
        """--targets 指向不存在文件 → stderr 退回地板门，继续跑成功（spec §8）。"""
        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        r = self._build(ws, st, tmp_path / ws["deliv"], tmp_path / "nope.json")
        assert r.returncode == 0 and "BUILD_READY" in r.stdout
        assert "退回地板门" in r.stderr, r.stderr

    def test_missing_data_signals_scale_down_pass(self, ws, tmp_path):
        """缺数章（E2E 防误拦）：40×[待确认]+1×数据未提供 → 49 signals → scale 触底 0.25 → 目标 8000×0.6×0.25=1200 < eff → 放行。"""
        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        raw = (st / "chapters" / "ch2.md").read_text(encoding="utf-8")
        raw += "\n\n补充说明 [待确认] " * 40 + "\n（某族: 数据未提供——[待确认] 槽位，缺参不编造）\n"
        (st / "chapters" / "ch2.md").write_text(raw, encoding="utf-8")
        r = self._build(ws, st, tmp_path / ws["deliv"], self._targets(tmp_path, "ch2", 8000))
        assert r.returncode == 0 and "BUILD_READY" in r.stdout, r.stderr

    def test_coverage_scale_floor_unit(self):
        import build_output

        t = {"scale_floor": 0.25, "per_signal_penalty": 0.05, "missing_table_weight": 8}
        assert build_output.coverage_scale("[待确认]" * 100, t) == 0.25
        assert build_output.coverage_scale("全数据完整叙述。", t) == 1.0


class TestGateHardening:
    """门硬化三锚（页面实测线程 03e18e4a 死循环取证）：L1 父节豁免 / 失败一次报齐 / --targets 收口+直调防绕。"""

    def test_parent_section_with_children_exempt(self):
        """## 父节 2 句引言+子节充实 → 不再误拦（线程 03e18e4a ch5「## 5=2句」结构陷阱：句子写进子节却报父节）。

        压到 eff<1000 只允许 eff 门报错——若父节瘦块误拦会先报「## 5=2句」，match 即失败。
        """
        import build_output

        md = "## 5 矿石加工技术性能\n\n矿石加工技术性能是矿床勘查与开发的重要环节。本次工作对矿石工业利用性能进行了系统评价。\n\n### 5.1 试验研究\n\n试样采自勘查区矿体。试样覆盖三种工业类型。试验结果可靠。\n"
        with pytest.raises(ValueError, match="有效字符"):
            build_output.validate_depth("ch5", md)  # 唯一允许的报错=eff 门；「## 5=2句」不得出现

    def test_leaf_section_still_enforced_with_location_hint(self):
        """叶子节（无子节）<3 句仍拦，报错带位置指引（句子写在该节正文、下一级子标题之前）。"""
        import build_output

        md = "## 5 矿石加工技术性能\n\n引言句一。引言句二。\n\n### 5.1 试验研究\n\n试样一。试样二。\n"
        with pytest.raises(ValueError, match=r"下一级子标题之前.*5\.1 试验研究=2句"):
            build_output.validate_depth("ch5", md)

    def test_aggregate_reports_all_chapters_one_run(self, ws, tmp_path):
        """两章重写压薄 → 同一次 build stderr 同时列出两章（不再逐章打回喂 60 次熔断）。"""
        import subprocess

        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        for n in (2, 3):
            (st / "chapters" / f"ch{n}.md").write_text(f"## {n} 章\n\n引言句。引言句二。\n\n### {n}.1 小节\n\n句子一。句子二。\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "build_output.py"), "--stage", str(STAGE), "--data-dir", str(ws["data"]), "--state-dir", str(st), "--output", str(tmp_path / ws["deliv"]), "--targets", str(_floor_targets())],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 1
        assert "ch2.md" in r.stderr and "ch3.md" in r.stderr, r.stderr
        assert "一次报齐" in r.stderr, r.stderr

    def test_custom_targets_warn_and_manifest_trace(self, ws, tmp_path):
        """--targets 非技能基准：stderr 高声警告（调试专用）+ delivery_manifest 记 path/sha256 留痕。"""
        import hashlib
        import subprocess

        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        out = tmp_path / ws["deliv"]
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "build_output.py"), "--stage", str(STAGE), "--data-dir", str(ws["data"]), "--state-dir", str(st), "--output", str(out), "--targets", str(_floor_targets())],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 0 and "BUILD_READY" in r.stdout, r.stderr
        assert "警告" in r.stderr and "调试基准" in r.stderr, r.stderr
        m = json.loads((out.parent / "delivery_manifest.json").read_text(encoding="utf-8"))
        ft = _floor_targets()
        assert m["targets"]["sha256"] == hashlib.sha256(ft.read_bytes()).hexdigest()

    def test_direct_assemble_call_enforces_canonical(self, ws, tmp_path):
        """直调 assemble（targets=None）不再绕 L2——强制吃技能真基准（线程 03e18e4a 直调绕门 ~10 次）。"""
        import build_output

        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        self._thin_ch10(st)
        stage = json.loads(STAGE.read_text(encoding="utf-8"))
        with pytest.raises(ValueError, match="深度目标门"):
            build_output.assemble(stage, ws["data"], st, targets=None)

    @staticmethod
    def _thin_ch10(st):
        """ch10 压到 (1000, 真实目标) 区间：L0/L1/toc 全过、只被 L2 拦（同 test_probe_finds_real_targets 合成法，从 stage toc 程序生成）。"""
        import re as _re

        filler = "本章为防绕回归专用的合成薄章节正文，语句仅用于满足每节三句的深度门下限，不承载地质含义。全段不含缺数标记，覆盖缩放恒为一点零，目标固定为样例中位数乘以系数。有效字符总量压到该目标之下，用于验证直调也吃真基准。"
        stage = json.loads(STAGE.read_text(encoding="utf-8"))
        num_re = _re.compile(r"\d+\.\d+(?:\.\d+)?")
        md = ["## 10 结论", "", filler]
        seen: set[str] = set()
        for sub in stage["chapters"]["ch10"]["toc"]:
            for no in num_re.findall(sub):
                if no in seen:
                    continue
                seen.add(no)
                md += [f"{'###' if no.count('.') == 1 else '####'} {no} 小节", "", filler]
        (st / "chapters" / "ch10.md").write_text("\n".join(md) + "\n", encoding="utf-8")


class TestDepthTargetsFile:
    """提交的 references/depth_targets.json：结构/量级锚（calibrate 产物回归）。"""

    def test_structure_and_magnitude(self):
        doc = json.loads((SKILL / "references" / "depth_targets.json").read_text(encoding="utf-8"))
        assert (doc["coefficient"], doc["scale_floor"]) == (0.6, 0.25)
        pc = doc["per_chapter"]
        assert set(pc) == {f"ch{i}" for i in range(1, 11)}
        assert all(c["median_eff"] > 1000 for c in pc.values())
        assert max(pc, key=lambda k: pc[k]["median_eff"]) == "ch6"  # 证据表：ch6 样例最厚
        assert pc["ch6"]["median_eff"] > 15000

    def test_probe_finds_real_targets(self, ws, tmp_path):
        """不传 --targets → 探测命中 references/depth_targets.json → 合成薄章节被真实目标拦截（探测链路端到端锚）。"""
        st = TestBuildOutput._copy_chapters(ws, tmp_path)
        # ws 固定样章本就厚到能过真实目标（BUILD_READY），须手工压薄一章：ch10 目标最低（2498×0.6≈1499），
        # 合成 ch10：全 toc 节号落标题+每节 3 句过 L0，零缺数信号 scale=1，eff≈1232 ∈ (1000, 目标) → 只被 L2 拦。
        filler = (
            "本章为回归锚定专用的合成薄章节正文，语句仅用于满足每节三句的深度门下限，不承载地质含义。全段不含缺数标记，覆盖缩放恒为一点零，目标固定为样例中位数乘以系数。有效字符总量压到该目标之下，用于验证省略参数时探测命中真实目标文件。"
        )
        heads = [
            "## 10 结论",
            "### 10.1 矿床勘查和研究程度",
            "#### 10.1.1 矿床勘查程度",
            "#### 10.1.2 矿床研究程度",
            "### 10.2 矿床成矿规律及远景评价",
            "#### 10.2.1 矿床成矿规律",
            "#### 10.2.2 找矿远景评价",
            "### 10.3 开采技术条件和地质环境问题",
            "### 10.4 矿床开采的经济效果",
            "### 10.5 地质工作的经验教训和存在问题",
            "### 10.6 下步地质勘查及矿床开采的建议",
        ]
        (st / "chapters" / "ch10.md").write_text("".join(h + "\n" + filler + "\n\n" for h in heads), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "build_output.py"), "--stage", str(STAGE), "--data-dir", str(ws["data"]), "--state-dir", str(st), "--output", str(tmp_path / ws["deliv"])],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 1 and "深度目标门" in r.stderr, r.stderr


class TestBuildOutput:
    def test_slot_injected_no_residue(self, ws):
        assert "{{SLOT:" not in ws["report_md"]
        assert "14.25" in ws["report_md"]

    def test_table_rendered(self, ws):
        assert "S-1" in ws["report_md"] and "| 序号" in ws["report_md"]

    def test_idempotent_second_build(self, ws):
        assert "unchanged" in ws["build2"]

    def test_missing_chapter_rc1(self, ws, tmp_path):
        """ch2 缺失 → rc=1；ch1 须整体拷 fixture（自身须过卫生/深度门）才能走到缺失分支。"""
        st = tmp_path / "st"
        (st / "chapters").mkdir(parents=True)
        (st / "formula_state.json").write_text((ws["state"] / "formula_state.json").read_text(encoding="utf-8"), encoding="utf-8")
        (st / "chapters" / "ch1.md").write_text((ws["state"] / "chapters" / "ch1.md").read_text(encoding="utf-8"), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "build_output.py"), "--stage", str(STAGE), "--data-dir", str(ws["data"]), "--state-dir", str(st), "--output", str(tmp_path / ws["deliv"]), "--targets", str(_floor_targets())],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 1 and "章节产物缺失" in r.stderr, r.stderr

    @staticmethod
    def _copy_chapters(ws, tmp_path):
        st = tmp_path / "st"
        (st / "chapters").mkdir(parents=True)
        (st / "formula_state.json").write_text((ws["state"] / "formula_state.json").read_text(encoding="utf-8"), encoding="utf-8")
        for f in (ws["state"] / "chapters").glob("*.md"):
            (st / "chapters" / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        return st

    def test_front_matter_pollution_rc1(self, ws, tmp_path):
        """bug-2220：章节文件混入脚本保留标题（如目录）→ build FAIL 阻断，不产出重复前置。"""
        st = self._copy_chapters(ws, tmp_path)
        (st / "chapters" / "ch2.md").write_text("## 2 区域地质\n\n## 目录\n\n- 手写目录（污染）\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "build_output.py"), "--stage", str(STAGE), "--data-dir", str(ws["data"]), "--state-dir", str(st), "--output", str(tmp_path / ws["deliv"]), "--targets", str(_floor_targets())],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 1 and "含脚本保留标题" in r.stderr, r.stderr

    def test_chapter_bad_first_line_rc1(self, ws, tmp_path):
        """bug-2220：章节首行非 `## N 章标题`（如一级标题/前置内容）→ build FAIL。"""
        st = self._copy_chapters(ws, tmp_path)
        (st / "chapters" / "ch2.md").write_text("# 云南省某铜矿勘探报告\n\n前置内容混入章节文件\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "build_output.py"), "--stage", str(STAGE), "--data-dir", str(ws["data"]), "--state-dir", str(st), "--output", str(tmp_path / ws["deliv"]), "--targets", str(_floor_targets())],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 1 and "首行必须是" in r.stderr, r.stderr


# ── 5. consistency：四类合约 + SL2 历史编码回归 ──────────────────────────────


class TestConsistency:
    def test_no_fail_severity(self, ws):
        fails = [i for i in ws["consistency"]["items"] if i["severity"] == "fail"]
        assert not fails, fails

    def test_summary_counts(self, ws):
        s = ws["consistency"]["summary"]
        assert s["pass"] >= 20 and s["fail"] == 0

    def test_sl2_historical_code_whitelisted(self, ws):
        """bug-2211 回归：332 是历史分类编码（红线 P4 原样保留），不得打不可溯源。"""
        sl2 = [i for i in ws["consistency"]["items"] if i.get("contract", "").startswith("SL2")]
        assert all("332" not in i["detail"] for i in sl2), sl2

    def test_historical_code_regex(self):
        import consistency as cons

        wl = cons.WHITELIST_RE[-1]
        for code in ("332", "333", "111b", "122b", "2M22", "331", "334", "B+C+D"):
            assert wl.search(code), code
        assert not wl.search("422"), "422 是采空区数量（须走 numeric_pool 溯源），不得被此白名单豁免"

    def test_sl1_wide_match_deformed_slots(self):
        """bug-3040/N19 回归：畸形 SLOT 形（单开括号/错配收形）必须被宽匹配拦为残留。"""
        import consistency as cons

        rep = cons.Report()
        cons.check_sl(rep, [("## 1 章", "## 1 章\n{SLOT:L9.total_ore_wt} 万吨 … {{SLOT:L9.total_metal_t}t} …")], set())
        sl1 = [i for i in rep.items if i["contract"] == "SL1"]
        assert sl1 and sl1[0]["severity"] == "fail", sl1

    def test_make_inject_deformity_repair(self, tmp_path):
        """bug-3040/N19 回归：注入前归一化 {{SLOT:k}m}→{{SLOT:k}}m、{SLOT:k}→{{SLOT:k}}；未知键仍走 FAIL 门。"""
        import build_output

        state = {"values": {
            "L9.total_ore_wt": {"value": 1234.5, "display": "1234.5", "source": "t"},
            "L9.total_metal_t": {"value": 8.9, "display": "8.9", "source": "t"},
        }}
        unknown: set[str] = set()
        out = build_output.make_inject({"forms": {}}, tmp_path, state, unknown)(
            "矿石量 {{SLOT:L9.total_ore_wt}} 万吨；金属量 {SLOT:L9.total_metal_t} t；错配 {{SLOT:L9.total_ore_wt}万吨}")
        assert "SLOT" not in out, out
        assert "1234.5 万吨" in out and "8.9 t" in out and "1234.5万吨" in out, out
        unknown2: set[str] = set()
        out2 = build_output.make_inject({"forms": {}}, tmp_path, state, unknown2)("坏键 {SLOT:XX.nope}")
        assert "XX.nope" in unknown2 and "{{SLOT:XX.nope}}" in out2

    def test_sl3_sample_fingerprint(self, tmp_path):
        """N18/SL3 回归：范文数值泄漏→fail；数值在池→pass；样例库缺失→warn 跳过；范文专名→warn。"""
        from decimal import Decimal
        from types import SimpleNamespace

        import consistency as cons

        stage_path = tmp_path / "references" / "stages" / "exploration.json"
        samples = tmp_path / "references" / "samples" / "exploration"
        samples.mkdir(parents=True)
        (samples / "ch1_sample.md").write_text("范文数据 7700 万吨 灯影组\n", encoding="utf-8")
        data = SimpleNamespace(forms={}, csvs={})
        ch = [("## 1 章", "## 1 章\n全区 7700 万吨\n灯影组出露")]
        rep = cons.Report()
        cons.check_sl3(rep, ch, data, stage_path, set())
        items = [i for i in rep.items if i["contract"] == "SL3"]
        assert any(i["severity"] == "fail" and "7700" in i["detail"] for i in items), items
        assert any(i["severity"] == "warn" and "灯影组" in i["detail"] for i in items), items
        rep2 = cons.Report()
        cons.check_sl3(rep2, ch, data, stage_path, {Decimal("7700")})
        assert not any(i["severity"] == "fail" for i in rep2.items if i["contract"] == "SL3"), rep2.items
        rep3 = cons.Report()
        cons.check_sl3(rep3, ch, data, tmp_path / "nonexistent.json", set())
        assert any(i["contract"] == "SL3" and i["severity"] == "warn" and "跳过" in i["detail"] for i in rep3.items), rep3.items

    def test_fc9_potential_magnitude(self):
        """N26/FC9 回归：potential 量级 10× 带宽——虚高（33209 亿型）→fail；同量级→pass；缺输入→跳过。"""
        from types import SimpleNamespace

        import consistency as cons

        eco = {"concentrate": {"grade_cu_pct": 10.0}}
        data = SimpleNamespace(form=lambda name: eco if name == "economics" else {})
        base = {"L9.total_metal_t": {"value": "8.9", "display": "8.9", "source": "t"},
                "E4.price_conc": {"value": "60000", "display": "60000", "source": "t"}}
        # implied = 8.9 × 60000 / (10/100) = 534 万元；0.0534 亿 × 1e8 = 同量级
        bad = {**base, "E5.gross_potential_yi": {"value": "534000000000", "display": "53.4万亿", "source": "t", "unit": "亿元"}}
        rep = cons.Report()
        cons.check_fc(rep, {"values": bad}, data)
        fc9 = [i for i in rep.items if i["contract"] == "FC9"]  # FC7 在假价格下另有噪声 fail，按合约过滤
        assert fc9 and fc9[0]["severity"] == "fail" and "E5.gross_potential_yi" in fc9[0]["detail"], fc9
        ok = {**base, "E5.gross_potential_yi": {"value": "0.0534", "display": "0.0534亿元", "source": "t", "unit": "亿元"}}
        rep2 = cons.Report()
        cons.check_fc(rep2, {"values": ok}, data)
        fc9b = [i for i in rep2.items if i["contract"] == "FC9"]
        assert fc9b and fc9b[0]["severity"] == "pass", fc9b
        rep3 = cons.Report()
        cons.check_fc(rep3, {"values": {k: v for k, v in ok.items() if not k.startswith("L9.")} | {"E5.gross_potential_yi": ok["E5.gross_potential_yi"]}}, data)
        fc9c = [i for i in rep3.items if i["contract"] == "FC9"]
        assert fc9c and fc9c[0]["severity"] == "pass" and "跳过" in fc9c[0]["detail"], fc9c

    def test_xs6_same_label_conflict(self):
        """N27/XS6 回归：同一中文指标标签跨章绑定两个不同槽位显示值→fail。"""
        from types import SimpleNamespace

        import consistency as cons

        state = {"values": {
            "L9.total_ore_wt": {"value": 1234.5, "display": "1234.5", "source": "t"},
            "L10.diff_wt": {"value": 999, "display": "999", "source": "t"},
        }}
        ch = [("## 1 章", "## 1 章\n工业矿石量 1234.5 万吨"), ("## 8 章", "## 8 章\n工业矿石量 999 万吨")]
        data = SimpleNamespace(form=lambda n: {})
        rep = cons.Report()
        cons.check_xs(rep, ch, state, data)
        xs6 = [i for i in rep.items if i["contract"] == "XS6"]
        assert xs6 and xs6[0]["severity"] == "fail" and "工业矿石量" in xs6[0]["detail"], xs6


# ── 6. snapshot：正典 + 篡改检测 ────────────────────────────────────────────


class TestSnapshot:
    def test_verify_intact(self, ws):
        assert "SNAPSHOT_VERIFIED" in ws["verify_ok"]

    def test_snapshot_has_file_hashes(self, ws):
        snap = json.loads((ws["out"] / "project_snapshot.json").read_text(encoding="utf-8"))
        assert snap.get("file_hashes"), "SHA-256 清单（设计决策 2B）必须在场"


# ── 7. E2E：全链路已在 fixture 中真实执行，此处锁组装产物结构 ───────────────


class TestE2E:
    def test_report_structure(self, ws):
        md = ws["report_md"]
        assert md.index("## 外封面") < md.index("## 1 绪论") < md.index("## 10 结论") < md.index("## 合规性附录")

    def test_front_matter_from_forms(self, ws):
        assert "东川区某铜银金多金属矿" in ws["report_md"] and "某地质大队" in ws["report_md"]

    def test_cover_title_no_stage_duplication(self, ws):
        """bug-2227 回归：题名=矿种组合+阶段+报告，阶段词不得重复（勘探勘探）。"""
        assert "铜银金勘探报告" in ws["report_md"]
        assert "勘探勘探" not in ws["report_md"]

    def test_cover_title_type_word_follows_stage(self, tmp_path):
        """bug-2227：类型词随 stage 走（详查→铜详查报告），不硬编码「勘探报告」。"""
        import build_output

        data = tmp_path / "data"
        data.mkdir()
        (data / "p.json").write_text(json.dumps({"commodity": "铜", "stage": "详查"}, ensure_ascii=False), encoding="utf-8")
        md = build_output.render_front_matter(
            {"stage": "详查", "forms": {"project": {"file": "p.json"}, "tenement": {"file": "t.json"}, "figures_tables": {"file": "ft.json"}}, "front_matter": {"outer_cover": ["报告题名（矿种组合+阶段+报告）"]}},
            data,
        )
        assert "铜详查报告" in md and "勘探报告" not in md

    def test_no_page_numbers_in_toc(self, ws):
        """D11：目录禁写页码（Word 排版阶段自动填充）。"""
        toc = ws["report_md"].split("## 目录")[1].split("##")[0] if "## 目录" in ws["report_md"] else ""
        for line in toc.splitlines():
            assert not re_search_page(line), line


def re_search_page(line: str) -> bool:
    import re

    return bool(re.search(r"\d+\s*页|\.{3,}\s*\d+", line))


class TestDataExpectations:
    """按章数据预告：10 章全覆盖、族名必须是 stage forms 实有键、CSV 列样例在场。"""

    def test_covers_all_chapters_and_valid_families(self):
        doc = json.loads((SKILL / "references" / "data_expectations.json").read_text(encoding="utf-8"))
        pc = doc["per_chapter"]
        assert set(pc) == {f"ch{i}" for i in range(1, 11)}
        known = set(json.loads(STAGE.read_text(encoding="utf-8"))["forms"])
        for ch, entry in pc.items():
            assert set(entry["families"]) <= known, (ch, set(entry["families"]) - known)
        assert "样品编号" in doc["csv_columns"]["sample_assays"]
        assert any("小体重" in col for col in doc["csv_columns"]["bulk_density"])


# ── 8. progress gate / run-stage：批量子命令（平台预算规避，bug-3040/3048）────


def run_raw(*args) -> tuple[int, str, str]:
    """同 run() 但返回 (rc, stdout, stderr)——gate/run-stage 的失败语义本身就是被测合约。"""
    argv = [str(SCRIPTS / args[0]), *map(str, args[1:])]
    if argv[0].endswith("build_output.py") and "--targets" not in argv:
        argv += ["--targets", str(_floor_targets())]
    r = subprocess.run([sys.executable, "-X", "utf8", *argv], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


def _mk_prog_state(base: Path, stage_copy: Path, ws, *, corrupt: str | None = None) -> Path:
    """控制器沙盒 state dir：formula_state + chapters 拷自 ws，init 后 wave1 全 DRAFTED（模拟收章）。"""
    st = base / "state"
    (st / "chapters").mkdir(parents=True)
    shutil.copy(ws["state"] / "formula_state.json", st / "formula_state.json")
    for md in (ws["state"] / "chapters").glob("*.md"):
        shutil.copy(md, st / "chapters" / md.name)
    if corrupt:
        (st / "chapters" / f"{corrupt}.md").write_text(f"## {corrupt[2:]} 薄章\n\n只有一句话。\n", encoding="utf-8")
    run("progress.py", "init", "--stage", stage_copy, "--state-dir", st, "--data-dir", ws["data"])
    for i in range(1, 10):
        run("progress.py", "mark", f"ch{i}", "DRAFTED", "--state-dir", st)
    return st


@pytest.fixture(scope="session")
def prog(ws, tmp_path_factory):
    """ws 之上的 gate/run-stage 沙盒：stage 副本 + 地板基准放 stage 探测路径（resolve_targets
    沿 stage 向上三级探测——gate 与 build_output 子进程都吃同一基准，不传 --targets，同生产语义）。"""
    base = tmp_path_factory.mktemp("geov2prog")
    (base / "references" / "stages").mkdir(parents=True)
    stage_copy = base / "references" / "stages" / "exploration.json"
    stage_copy.write_text(STAGE.read_text(encoding="utf-8"), encoding="utf-8")
    (base / "references" / "depth_targets.json").write_text(_floor_targets().read_text(encoding="utf-8"), encoding="utf-8")
    st = _mk_prog_state(base, stage_copy, ws)
    return {"base": base, "stage": stage_copy, "state": st, "data": ws["data"], "deliv": ws["deliv"]}


class TestGateBatch:
    def test_batch_gate_promotes_all_drafts(self, prog):
        """缺省一次跑完全部 DRAFTED 章门禁，PASS 章自动转 VERIFIED（唯一写者仍是 progress.py）。"""
        out = run("progress.py", "gate", "--state-dir", prog["state"])
        assert "GATE_BATCH_DONE: passed=9 failed=0" in out
        doc = json.loads((prog["state"] / "progress.json").read_text(encoding="utf-8"))
        assert all(doc["chapters"][f"ch{i}"]["status"] == "VERIFIED" and doc["chapters"][f"ch{i}"]["last_gate"] == "PASS" for i in range(1, 10))
        assert doc["phase"] == "KEY_POINTS"  # wave1 收口且无 BLOCKED → 进要点包相位

    def test_gate_without_drafts_errors(self, prog):
        """全部 VERIFIED 后再跑 gate：没有 DRAFTED 章 → rc=1（不空转）。"""
        rc, _, err = run_raw("progress.py", "gate", "--state-dir", prog["state"])
        assert rc == 1 and "没有 DRAFTED 章" in err

    def test_batch_gate_fail_keeps_chapter_draft(self, ws, prog):
        """任一章 FAIL → rc=1、stderr 逐条差距、该章保持 DRAFTED，其余章照常转正。"""
        st = _mk_prog_state(prog["base"] / "neg", prog["stage"], ws, corrupt="ch3")
        rc, out, err = run_raw("progress.py", "gate", "--state-dir", st)
        assert rc == 1 and "CHAPTER_GATE_FAIL: ch3" in err and "failed=1" in out
        doc = json.loads((st / "progress.json").read_text(encoding="utf-8"))
        assert doc["chapters"]["ch3"]["status"] == "DRAFTED"
        assert all(doc["chapters"][f"ch{i}"]["status"] == "VERIFIED" for i in (1, 2, 4, 5, 6, 7, 8, 9))
        assert doc["phase"] == "WAVE1"  # 有 DRAFTED 未收口，不越相位

    def test_gate_unknown_chapter_rejected(self, prog):
        rc, _, err = run_raw("progress.py", "gate", "--state-dir", prog["state"], "--chapters", "ch99")
        assert rc == 1 and "未知章节" in err


class TestRunStage:
    def test_freeze_merges_manifest_and_execute(self, prog):
        """冻结二连一次 bash：manifest + execute，退出码语义透传（rc=3=anomalies，同门 2）。"""
        rc, out, _ = run_raw("progress.py", "run-stage", "freeze", "--state-dir", prog["state"])
        assert rc in (0, 3)
        assert (prog["state"] / "chapter_manifest.json").exists()
        assert (prog["state"] / "formula_state.json").exists()

    def test_finalize_merges_build_consistency_snapshot(self, ws, prog, tmp_path):
        """终验三连一次 bash：BUILD_READY/MANIFEST_READY 整行透传（交付铁律 #2 粘贴要求不丢），
        交付名由脚本从 data/ 直拼，报告+delivery_manifest+project_snapshot 落 outputs。"""
        outs = tmp_path / "outputs"
        outs.mkdir()
        rc, out, err = run_raw("progress.py", "run-stage", "finalize", "--state-dir", prog["state"], "--outputs-dir", outs, "--task", "测试终验")
        assert "BUILD_READY" in out, err  # build 子进程 stdout 原样透传
        assert (outs / prog["deliv"]).exists()
        assert (outs / "delivery_manifest.json").exists()
        if rc in (0, 3):  # rc=3=WARN/MANUAL 汇报后仍交付；rc=2 门拦 → snapshot 未执行
            assert "MANIFEST_READY" in out
            assert (outs / "project_snapshot.json").exists()
        else:
            assert rc == 2

    def test_finalize_requires_outputs_dir(self, prog):
        rc, _, err = run_raw("progress.py", "run-stage", "finalize", "--state-dir", prog["state"])
        assert rc == 1 and "--outputs-dir" in err

    def test_finalize_consistency_gate_stops_before_snapshot(self, prog, monkeypatch, tmp_path):
        """停门不变式（review 必修1）：consistency rc=1/2 → snapshot 绝不启动（带病不交付）。
        in-process 调 cmd_run_stage，_run_py 打桩按脚本名回放退出码，snapshot 被调即断言失败。"""
        import progress as progress_mod

        outs = tmp_path / "outputs"
        outs.mkdir()
        calls: list[str] = []

        def fake_run_py(script, *a):
            calls.append(script)
            if script == "build_output.py":
                (outs / prog["deliv"]).write_text("report\n", encoding="utf-8")
                return 0
            if script == "consistency.py":
                return 2
            raise AssertionError(f"consistency 门拦后不应再跑 {script}")

        monkeypatch.setattr(progress_mod, "_run_py", fake_run_py)
        ns = argparse.Namespace(stage_name="finalize", state_dir=str(prog["state"]), outputs_dir=str(outs), task="测试门拦", allow_partial=False)
        rc = progress_mod.cmd_run_stage(ns)
        assert rc == 2
        assert calls == ["build_output.py", "consistency.py"]
        assert not (outs / "project_snapshot.json").exists()
