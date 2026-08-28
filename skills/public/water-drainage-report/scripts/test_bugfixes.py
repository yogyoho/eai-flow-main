#!/usr/bin/env python3
"""bug-2198/2199 修复回归检查（与 test_snapshot.py 同风格，subprocess 实跑 CLI）。

覆盖：
1. bug-2199 — build_manifest 产出 ch11_compliance 且 formula_ids=全量公式；
   impacted_chapters 在任一公式受影响时必含 ch11。
2. bug-2198 — snapshot save 拒绝非正典文件名（旁路文件守卫）。
3. bug-2199 — update --params-output 把改参后的用户参数写回（check 数据源不陈旧）。
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SP = Path(__file__).parent
sys.path.insert(0, str(SP))
import chapter_planner  # noqa: E402


def test_ch11_compliance_in_manifest_and_impacted() -> None:
    formulas = [
        {"id": "Qe", "section": "6.1.1"},
        {"id": "Qb", "section": "6.2"},
        {"id": "filter_count", "section": "9.1"},
    ]
    m = chapter_planner.build_manifest(formulas)
    ch11 = [c for c in m["chapters"] if c["id"] == "ch11_compliance"]
    assert ch11, "manifest 缺 ch11_compliance 章"
    assert set(ch11[0]["formula_ids"]) == {"Qe", "Qb", "filter_count"}, ch11[0]["formula_ids"]

    hit = chapter_planner.impacted_chapters(["Qb"], m)
    assert "ch11_compliance" in hit, f"改 Qb 未标记合规附录: {hit}"
    assert "ch5_calc" in hit, f"改 Qb 未标记计算章: {hit}"
    assert chapter_planner.impacted_chapters([], m) == [], "空受影响集不应命中任何章"


def test_snapshot_rejects_side_filename() -> None:
    with tempfile.TemporaryDirectory() as d:
        side = Path(d) / "project_snapshot_N5.json"
        r = subprocess.run(
            [sys.executable, str(SP / "snapshot.py"), "save", "--task", "增量更新N=5", "--output", str(side)],
            capture_output=True, text=True,
        )
        assert r.returncode != 0, "save 写旁路文件名应当失败"
        assert "SNAPSHOT_ERROR" in r.stdout, r.stdout
        assert not side.exists(), "旁路文件不应被写出"


def test_update_params_output() -> None:
    formulas_path = SP.parent / "references" / "formulas.json"
    with tempfile.TemporaryDirectory() as d:
        state = {"all_params": {"Q": 12000, "delta_t": 9, "N": 4, "pool_area": 520, "V_suction": 1200,
                                "KZF": 0.001461, "drift_rate": 0.001, "sf_ratio": 0.05,
                                "effective_depth": 1.5, "backwash_intensity": 15.0, "backwash_duration": 2.0,
                                "pump_motor_spacing": 3.0, "filter_unit_capacity": 100,
                                "filter_area": 10.0, "concurrent_backwash": 1}}
        state_path = Path(d) / "formula_state.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        params_out = Path(d) / "params.json"
        r = subprocess.run(
            [sys.executable, str(SP / "formula_runner.py"), "update",
             "--formulas", str(formulas_path), "--state", str(state_path),
             "--param", "N", "--value", "5",
             "--output", str(state_path), "--params-output", str(params_out)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        assert "PARAMS_READY" in r.stdout, r.stdout
        fresh = json.loads(params_out.read_text(encoding="utf-8"))
        assert fresh["N"] == 5, f"params.json 未刷新: N={fresh.get('N')}"
        assert fresh["Q"] == 12000
        assert all("." not in k for k in fresh), "params.json 不应含公式输出键"


def test_snapshot_warns_on_missing_params() -> None:
    """bug-2203：--params 显式指定但文件缺失 → 必须打 SNAPSHOT_WARN（锚点参数回显降级要可见）。"""
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run(
            [sys.executable, str(SP / "snapshot.py"), "save", "--task", "t",
             "--output", str(Path(d) / "project_snapshot.json"),
             "--params", str(Path(d) / "no_such_params.json")],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        assert "SNAPSHOT_WARN" in r.stdout, r.stdout


def test_skill_text_guards() -> None:
    """bug-2202/2203/2198变体：SKILL 文本必须含并行竞态禁令 / params.json 落盘令 / 直改正典禁令。"""
    text = (SP.parent / "SKILL.md").read_text(encoding="utf-8")
    for needle in [
        "同一文件的读/写禁止并行 tool_call",
        "params.json 文件必须真实落盘",
        "直改正典文件本体",
        "render_calc_blocks.py",
        "禁止手写 KaTeX 公式块/计算过程折叠块替代脚本注入",
        "<!-- CALC_BLOCKS -->",
    ]:
        assert needle in text, f"SKILL.md 缺铁律文本: {needle}"


def test_render_calc_blocks_details() -> None:
    """反馈3 用户样例格式：$$公式+结果$$ 可见 + <details> 紧凑过程（公式/取值/代入/结果 bullets）。"""
    traces = {"traces": [
        {
            "id": "Qe", "name": "蒸发水量", "section": "6.1.1",
            "expression": "Q * KZF * delta_t", "source": "蒸发损失系数",
            "substituted": "16000 * 0.001461 * 9", "result": 210.38400000000001, "unit": "m3/h",
            "inputs": [
                {"name": "Q", "value": 16000, "unit": "m3/h", "source": "循环水设计水量", "needs_verification": False},
                {"name": "KZF", "value": 0.001461, "unit": "1/℃", "source": "参考值库", "needs_verification": True},
            ],
        },
        {
            "id": "filter_count", "name": "过滤器台数", "section": "9.1.2",
            "expression": "math.ceil(Qsf / filter_unit_capacity)", "source": "",
            "substituted": "math.ceil(800 / 45)", "result": 18.0, "unit": "台",
            "inputs": [
                {"name": "Qsf", "value": 800.0, "unit": "", "source": "formula:Qsf.Qsf", "needs_verification": False},
                {"name": "filter_unit_capacity", "value": 45, "unit": "m3/h", "source": "单台过滤器处理能力", "needs_verification": False},
            ],
        },
    ]}
    with tempfile.TemporaryDirectory() as d:
        tp = Path(d) / "traces.json"
        tp.write_text(json.dumps(traces, ensure_ascii=False), encoding="utf-8")
        out = Path(d) / "calc_blocks.md"
        r = subprocess.run(
            [sys.executable, str(SP / "render_calc_blocks.py"), "--traces", str(tp), "--output", str(out)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        assert "CALCBLOCKS_READY: 2" in r.stdout, r.stdout
        text = out.read_text(encoding="utf-8")
        for needle in [
            "### [6.1.1] 蒸发水量",
            # $$ 可见公式块：符号=表达式=代入=结果+latex单位；浮点收敛 210.38400000000001→210.384
            "$$Q_{e} = Q \\times KZF \\times \\Delta t = 16000 \\times 0.001461 \\times 9 = 210.384\\ \\text{m}^3/\\text{h}$$",
            "<details><summary>计算过程</summary>",
            "- 公式：$Q_{e} = Q \\times KZF \\times \\Delta t$",
            "- 取值：Q = 16000 m³/h；KZF = 0.001461 1/℃【待核实】",
            "- 代入：$16000 \\times 0.001461 \\times 9$",
            "- 结果：**210.384 m³/h**",
            # ceil → \lceil \frac \rceil；上游公式输出参数标注来源
            "### [9.1.2] 过滤器台数",
            "\\lceil \\frac{Qsf}{filter\\_unit\\_capacity} \\rceil",
            "\\lceil \\frac{800}{45} \\rceil = 18\\ \\text{台}$$",
            "Qsf = 800（由 [Qsf] 求得）",
            "- 结果：**18 台**",
            "</details>",
        ]:
            assert needle in text, f"calc_blocks 缺: {needle}"


def test_render_calc_blocks_inject() -> None:
    """反馈3 注入：占位符 <!-- CALC_BLOCKS --> 被替换为公式折叠块；缺占位符报 CALC_INJECT_ERROR 且文件不动；
    已注入（含签名）重跑 → CALC_INJECT_SKIP 幂等。"""
    traces = {"traces": [{
        "id": "Qe", "name": "蒸发水量", "expression": "Q * KZF * delta_t", "source": "蒸发损失系数",
        "substituted": "16000 * 0.001461 * 9", "result": 210.384, "unit": "m3/h", "inputs": [],
    }]}
    with tempfile.TemporaryDirectory() as d:
        tp = Path(d) / "traces.json"
        tp.write_text(json.dumps(traces, ensure_ascii=False), encoding="utf-8")
        rp = Path(d) / "report.md"
        rp.write_text("# 报告\n\n## 第5章 工艺计算\n\n<!-- CALC_BLOCKS -->\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(SP / "render_calc_blocks.py"), "inject", "--traces", str(tp), "--report", str(rp)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        assert "CALC_INJECT_READY: 1" in r.stdout, r.stdout
        injected = rp.read_text(encoding="utf-8")
        assert injected.count("<details>") == 1 and "<!-- CALC_BLOCKS -->" not in injected
        assert "<!-- CALC_BLOCKS_INJECTED:v2 count=1 -->" in injected, "注入后必须落带块数的 v2 签名（快照门禁依据）"

        # 幂等：已注入报告重跑 inject → SKIP 不重复注入
        r = subprocess.run(
            [sys.executable, str(SP / "render_calc_blocks.py"), "inject", "--traces", str(tp), "--report", str(rp)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        assert "CALC_INJECT_SKIP" in r.stdout, r.stdout
        assert rp.read_text(encoding="utf-8").count("<details>") == 1, "SKIP 不得重复注入"

        rp.write_text("# 报告（无占位符无签名）\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(SP / "render_calc_blocks.py"), "inject", "--traces", str(tp), "--report", str(rp)],
            capture_output=True, text=True,
        )
        assert r.returncode == 1
        assert "CALC_INJECT_ERROR" in r.stdout
        assert "<details>" not in rp.read_text(encoding="utf-8"), "缺占位符时不得改动报告"


def test_snapshot_gate_calc_blocks() -> None:
    """R8/R9 快照门禁：save --report 校验注入契约——占位符残留 / 无签名手写 <details> /
    签名块数与 <details> 总数不符（混合手写）→ SNAPSHOT_ERROR；已注入（签名数==块数）→ SNAPSHOT_READY。"""
    snap_out = {"task": "t", "report": None}  # placeholder, real args below
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        traces = {"traces": [{"id": "Qe", "name": "蒸发水量", "expression": "Q * KZF", "substituted": "1 * 2",
                              "result": 2, "unit": "m3/h", "inputs": []}]}
        tp = d / "traces.json"
        tp.write_text(json.dumps(traces, ensure_ascii=False), encoding="utf-8")
        rp = d / "report.md"
        out = d / "project_snapshot.json"

        def save() -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, str(SP / "snapshot.py"), "save", "--task", "t",
                 "--report", str(rp), "--output", str(out)],
                capture_output=True, text=True,
            )

        # ① 占位符未注入 → 拒绝
        rp.write_text("# 报告\n\n<!-- CALC_BLOCKS -->\n", encoding="utf-8")
        r = save()
        assert r.returncode == 1 and "SNAPSHOT_ERROR" in r.stdout, r.stdout
        assert "CALC_BLOCKS" in r.stdout, r.stdout
        assert not out.exists(), "门禁打回时不得写快照"

        # ② 手写 <details> 无签名 → 拒绝（R8 实测形态）
        rp.write_text("# 报告\n\n<details><summary>计算过程</summary>\n- 公式：$x$\n</details>\n", encoding="utf-8")
        r = save()
        assert r.returncode == 1 and "SNAPSHOT_ERROR" in r.stdout, r.stdout
        assert "手写" in r.stdout, r.stdout
        assert not out.exists()

        # ③ 走正道：占位符 → inject → save 通过
        rp.write_text("# 报告\n\n<!-- CALC_BLOCKS -->\n", encoding="utf-8")
        subprocess.run(
            [sys.executable, str(SP / "render_calc_blocks.py"), "inject", "--traces", str(tp), "--report", str(rp)],
            capture_output=True, text=True, check=True,
        )
        r = save()
        assert r.returncode == 0 and "SNAPSHOT_READY" in r.stdout, r.stdout
        assert out.exists()

        # ④ R9 混合违约：已注入（1 块）+ 正文又手写 1 块 → 块数对不上，拒绝
        cur = rp.read_text(encoding="utf-8")
        rp.write_text(cur + "\n<details><summary>计算过程</summary>\n- 公式：$y$\n</details>\n", encoding="utf-8")
        r = save()
        assert r.returncode == 1 and "SNAPSHOT_ERROR" in r.stdout, r.stdout
        assert "手写" in r.stdout or "R9" in r.stdout, r.stdout
        # 快照不得被 v2 的失败覆盖：仍只有 ③ 的版本
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert snap["version"] == 1, "④ 打回时不得写新快照版本"


def test_impacted_must_run_before_update() -> None:
    """impacted 是对磁盘旧状态的 dry-run 值差分：update 落盘后再跑 impacted 必得空集。

    2026-08-20 线程 9509c508：agent 先 update(N=5) 后 impacted → affected_formulas=[]
    （差分基准已被覆盖）。SKILL 步骤2 因此规定 impacted 先于 update——本测试锁死该依据。
    """
    formulas_path = SP.parent / "references" / "formulas.json"
    base_params = {"Q": 12000, "delta_t": 9, "N": 4, "pool_area": 520, "V_suction": 1200,
                   "KZF": 0.001461, "drift_rate": 0.001, "sf_ratio": 0.05,
                   "effective_depth": 1.5, "backwash_intensity": 15.0, "backwash_duration": 2.0,
                   "pump_motor_spacing": 3.0, "filter_unit_capacity": 100,
                   "filter_area": 10.0, "concurrent_backwash": 1}
    with tempfile.TemporaryDirectory() as d:
        state_path = Path(d) / "formula_state.json"
        manifest_path = Path(d) / "chapter_manifest.json"
        formulas = json.loads(formulas_path.read_text(encoding="utf-8"))["formulas"]
        manifest_path.write_text(json.dumps(chapter_planner.build_manifest(formulas), ensure_ascii=False), encoding="utf-8")

        def run_impacted() -> dict:
            r = subprocess.run(
                [sys.executable, str(SP / "formula_runner.py"), "impacted",
                 "--formulas", str(formulas_path), "--state", str(state_path),
                 "--param", "N", "--value", "5", "--manifest", str(manifest_path)],
                capture_output=True, text=True,
            )
            assert r.returncode == 0, r.stderr
            return json.loads(r.stdout)

        # 对旧状态（N=4）dry-run 改 N=5 → 非空且 ch11/ch5 必在（SKILL 步骤2 的正确顺序）
        state_path.write_text(json.dumps({"all_params": dict(base_params)}), encoding="utf-8")
        before = run_impacted()
        assert "Qb" in before["affected_formulas"], before
        assert "ch5_calc" in before["affected_chapters"], before
        assert "ch11_compliance" in before["affected_chapters"], before

        # update 落盘后，同样的 impacted 差分基准已被覆盖 → 空集（文档化既有语义）
        subprocess.run(
            [sys.executable, str(SP / "formula_runner.py"), "update",
             "--formulas", str(formulas_path), "--state", str(state_path),
             "--param", "N", "--value", "5", "--output", str(state_path)],
            capture_output=True, text=True, check=True,
        )
        after = run_impacted()
        assert after["affected_formulas"] == [], after


if __name__ == "__main__":
    test_ch11_compliance_in_manifest_and_impacted()
    test_snapshot_rejects_side_filename()
    test_update_params_output()
    test_impacted_must_run_before_update()
    test_snapshot_warns_on_missing_params()
    test_skill_text_guards()
    test_render_calc_blocks_details()
    test_render_calc_blocks_inject()
    test_snapshot_gate_calc_blocks()
    print("PASS: bug-2198 守卫 / bug-2199 ch11+params 刷新 / update --params-output / impacted 先于 update / SNAPSHOT_WARN / SKILL 文本守卫 / 反馈3 公式可见+过程折叠（用户样例格式）+注入+幂等 / R8+R9 快照门禁（占位符/手写/块数不符）")
