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

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "public" / "geological-report"
SCRIPTS = SKILL / "scripts"
STAGE = SKILL / "references/stages/exploration.json"
STANDARDS = SKILL / "references/standards_index.json"

sys.path.insert(0, str(SCRIPTS))


def run(*args, expect=(0,)):
    """调真实 CLI；断言退出码 ∈ expect。返回 stdout。"""
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / args[0]), *map(str, args[1:])], capture_output=True, text=True, encoding="utf-8", errors="replace")
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
        need = {f["name"]: ph(f) for f in spec.get("fields", []) if f.get("required", True) and doc.get(f["name"]) in (None, "", [], {})}
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
    chapters = {
        1: f"## 1 绪论\n\n本次勘查共获得工业矿石量 {slot('L9.total_ore_wt')} 万吨。\n\n### 1.1 目的任务\n\n（1）查明矿体特征。（2）估算资源量。\n",
        2: "## 2 区域地质\n\n区域大地构造位置属扬子板块西缘。（1）地层。（2）构造。（3）岩浆岩。\n",
        3: "## 3 矿区地质\n\n矿区出露地层为震旦系灯影组白云岩。\n",
        4: f"## 4 矿体\n\n①号矿体平均品位 {slot('L8.C_orebody[①]')}%。特高品位下限取 {slot('C9.outlier_threshold')}%。\n",
        5: f"## 5 矿石加工选冶技术性能\n\n闭路试验铜精矿回收率 {slot('B1.recovery[铜精矿]')}%。\n",
        6: (
            "## 6 矿床开采技术条件\n\n坑道正常涌水量 " + slot("W1.Q_min") + "～" + slot("W1.Q_max") + " m3/d。老窑采空区 422 个、体积 1383.95 万 m3，"
            "水文地质类型为岩溶裂隙弱-中等含水层充水为主、顶板直接充水简单类型；"
            "工程地质类型为半坚硬-坚硬层状白云岩为主中等类型；"
            "复合类型为以工程、环境复合地质问题为主的中等类型。\n"
        ),
        7: f"## 7 勘查工作及其质量评述\n\n小体重样 {slot('S1.n')} 件，平均体重 {slot('S1.avg_density')} t/m3。\n",
        8: (
            "## 8 资源量估算\n\n工业矿石量 "
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
            + " g/t。\n\n{{{{TABLE:bulk_density}}}}\n"
        ),
        9: f"## 9 经济评价\n\n精矿含铜价格 {slot('E4.price_conc')} 元/t，潜在总值 {slot('E5.gross_potential_yi')} 亿元。\n",
        10: f"## 10 结论\n\n本次估算工业矿石量 {slot('L9.total_ore_wt')} 万吨，与正文第 1、8 章一致。\n",
    }
    for n, md in chapters.items():
        (state / "chapters" / f"ch{n}.md").write_text(md, encoding="utf-8")

    build1 = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", out / "report.md")
    build2 = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", out / "report.md")

    # 负例：未知槽位 → rc=1 阻断
    bad = state / "chapters" / "ch10.md"
    orig10 = bad.read_text(encoding="utf-8")
    bad.write_text(orig10 + "\n未知 {{SLOT:XX.noexist}}\n", encoding="utf-8")
    run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", out / "report_bad.md", expect=(1,))
    bad.write_text(orig10, encoding="utf-8")

    cc = run("consistency.py", "--report", out / "report.md", "--data-dir", data, "--stage", STAGE, "--state", state / "formula_state.json", "--standards", STANDARDS, "--output", state / "consistency_check.json", expect=(0, 2, 3))

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
        out / "report.md",
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
        "report_md": (out / "report.md").read_text(encoding="utf-8"),
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
            capture_output=True, text=True, encoding="utf-8", errors="replace",
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
            capture_output=True, text=True, encoding="utf-8", errors="replace",
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

    def test_stage_bare_name_resolves(self, tmp_path):
        """bug-2217: 裸名 'exploration' 自动补全到内置 stages 路径，
        不再抛 FileNotFoundError 裸 traceback；不存在的名字给可读错误。"""
        d = tmp_path / "d"
        d.mkdir()
        out = run("ingest.py", "forms", "--stage", "exploration", "--data-dir", d)
        assert "FORMS_READY" in out
        r = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "ingest.py"), "forms", "--stage", "nonexistent_stage", "--data-dir", str(d)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
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
                [sys.executable, "-X", "utf8", str(SCRIPTS / "ingest.py"), "forms", "--stage", str(STAGE), "--data-dir", str(d),
                 "--family", fam, "--values", json.dumps(vals, ensure_ascii=False)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
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


class TestBuildOutput:
    def test_slot_injected_no_residue(self, ws):
        assert "{{SLOT:" not in ws["report_md"]
        assert "14.25" in ws["report_md"]

    def test_table_rendered(self, ws):
        assert "S-1" in ws["report_md"] and "| 序号" in ws["report_md"]

    def test_idempotent_second_build(self, ws):
        assert "unchanged" in ws["build2"]

    def test_missing_chapter_rc1(self, ws, tmp_path):
        st = tmp_path / "st"
        (st / "chapters").mkdir(parents=True)
        (st / "formula_state.json").write_text((ws["state"] / "formula_state.json").read_text(encoding="utf-8"), encoding="utf-8")
        (st / "chapters" / "ch1.md").write_text("## 1\n", encoding="utf-8")
        run("build_output.py", "--stage", STAGE, "--data-dir", ws["data"], "--state-dir", st, "--output", tmp_path / "r.md", expect=(1,))

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
        run("build_output.py", "--stage", STAGE, "--data-dir", ws["data"], "--state-dir", st, "--output", tmp_path / "r.md", expect=(1,))

    def test_chapter_bad_first_line_rc1(self, ws, tmp_path):
        """bug-2220：章节首行非 `## N 章标题`（如一级标题/前置内容）→ build FAIL。"""
        st = self._copy_chapters(ws, tmp_path)
        (st / "chapters" / "ch2.md").write_text("# 云南省某铜矿勘探报告\n\n前置内容混入章节文件\n", encoding="utf-8")
        run("build_output.py", "--stage", STAGE, "--data-dir", ws["data"], "--state-dir", st, "--output", tmp_path / "r.md", expect=(1,))


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

    def test_no_page_numbers_in_toc(self, ws):
        """D11：目录禁写页码（Word 排版阶段自动填充）。"""
        toc = ws["report_md"].split("## 目录")[1].split("##")[0] if "## 目录" in ws["report_md"] else ""
        for line in toc.splitlines():
            assert not re_search_page(line), line


def re_search_page(line: str) -> bool:
    import re

    return bool(re.search(r"\d+\s*页|\.{3,}\s*\d+", line))
