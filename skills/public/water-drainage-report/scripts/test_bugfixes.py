#!/usr/bin/env python3
"""bug-2198/2199 修复回归检查（与 test_snapshot.py 同风格，subprocess 实跑 CLI）。

覆盖：
1. bug-2199 — build_manifest 产出 ch10_compliance 且 formula_ids=全量公式；
   impacted_chapters 在任一公式受影响时必含 ch10（2026-08-29 体例对齐：ch11→ch10）。
2. bug-2198 — snapshot save 拒绝非正典文件名（旁路文件守卫）。
3. bug-2199 — update --params-output 把改参后的用户参数写回（check 数据源不陈旧）。
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Windows GBK 控制台：子进程输出统一 UTF-8 编解码（父解码 + 子写侧同锁，缺一则 UnicodeDecodeError）
RUNENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

SP = Path(__file__).parent
sys.path.insert(0, str(SP))
import chapter_planner  # noqa: E402


def test_ch10_compliance_in_manifest_and_impacted() -> None:
    formulas = [
        {"id": "Qe", "section": "6.1.1"},
        {"id": "Qb", "section": "6.2"},
        {"id": "filter_count", "section": "9.1"},
    ]
    m = chapter_planner.build_manifest(formulas)
    ch10 = [c for c in m["chapters"] if c["id"] == "ch10_compliance"]
    assert ch10, "manifest 缺 ch10_compliance 章"
    assert set(ch10[0]["formula_ids"]) == {"Qe", "Qb", "filter_count"}, ch10[0]["formula_ids"]

    hit = chapter_planner.impacted_chapters(["Qb"], m)
    assert "ch10_compliance" in hit, f"改 Qb 未标记合规附录: {hit}"
    assert "ch6_calc" in hit, f"改 Qb 未标记计算章: {hit}"
    assert chapter_planner.impacted_chapters([], m) == [], "空受影响集不应命中任何章"


def test_snapshot_rejects_side_filename() -> None:
    with tempfile.TemporaryDirectory() as d:
        side = Path(d) / "project_snapshot_N5.json"
        r = subprocess.run(
            [sys.executable, str(SP / "snapshot.py"), "save", "--task", "增量更新N=5", "--output", str(side)],
            capture_output=True, text=True, encoding="utf-8", env=RUNENV,
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
            capture_output=True, text=True, encoding="utf-8", env=RUNENV,
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
            capture_output=True, text=True, encoding="utf-8", env=RUNENV,
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
            capture_output=True, text=True, encoding="utf-8", env=RUNENV,
        )
        assert r.returncode == 0, r.stderr
        assert "CALCBLOCKS_READY: 2" in r.stdout, r.stdout
        text = out.read_text(encoding="utf-8")
        for needle in [
            # $$ 可见公式块：符号=表达式=代入=结果+latex单位；浮点收敛 210.38400000000001→210.384
            "$$Q_{e} = Q \\times KZF \\times \\Delta t = 16000 \\times 0.001461 \\times 9 = 210.384\\ \\text{m}^3/\\text{h}$$",
            "<details><summary>计算过程</summary>",
            "- 公式：$Q_{e} = Q \\times KZF \\times \\Delta t$",
            "- 取值：Q = 16000 m³/h；KZF = 0.001461 1/℃【待核实】",
            "- 代入：$16000 \\times 0.001461 \\times 9$",
            "- 结果：**210.384 m³/h**",
            # ceil → \lceil \frac \rceil；上游公式输出参数标注来源
            "\\lceil \\frac{Qsf}{filter\\_unit\\_capacity} \\rceil",
            "\\lceil \\frac{800}{45} \\rceil = 18\\ \\text{台}$$",
            "Qsf = 800（由 [Qsf] 求得）",
            "- 结果：**18 台**",
            "</details>",
        ]:
            assert needle in text, f"calc_blocks 缺: {needle}"
        # 用户定案 A：注入块不带标题——小节标题由报告 TOC 承担，登记表 section 号不得进正文
        assert "### [" not in text, "注入块不得自带 [section] 标题（双编号/双标题）"
        # v2.1 签名：每块各带 count=1，求和==块数（快照门禁依据）
        assert text.count("CALC_BLOCKS_INJECTED:v2 count=1") == 2, "每块应各带 count=1 签名"


def test_render_calc_blocks_inject() -> None:
    """反馈3 注入（用户定案 A）：按公式占位符 <!-- CALC:Qe --> 替换为无标题公式块；
    未知 id / 公式缺标记 / 重复标记 / 无任何占位符 → CALC_INJECT_ERROR 且文件不动；
    已注入重跑 → SKIP 幂等；旧式单一 <!-- CALC_BLOCKS --> 兼容。"""
    traces = {"traces": [{
        "id": "Qe", "name": "蒸发水量", "expression": "Q * KZF * delta_t", "source": "蒸发损失系数",
        "substituted": "16000 * 0.001461 * 9", "result": 210.384, "unit": "m3/h", "inputs": [],
    }]}
    with tempfile.TemporaryDirectory() as d:
        tp = Path(d) / "traces.json"
        tp.write_text(json.dumps(traces, ensure_ascii=False), encoding="utf-8")
        rp = Path(d) / "report.md"

        def inject() -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, str(SP / "render_calc_blocks.py"), "inject", "--traces", str(tp), "--report", str(rp)],
                capture_output=True, text=True, encoding="utf-8", env=RUNENV,
            )

        # ① 按公式占位符：块落标记处、无标题、count=1 签名
        rp.write_text("# 报告\n\n#### 5.1.1 蒸发水量计算\n\n<!-- CALC:Qe -->\n", encoding="utf-8")
        r = inject()
        assert r.returncode == 0, r.stderr
        assert "CALC_INJECT_READY: 1" in r.stdout, r.stdout
        injected = rp.read_text(encoding="utf-8")
        assert injected.count("<details>") == 1 and "<!-- CALC:Qe -->" not in injected
        assert "<!-- CALC_BLOCKS_INJECTED:v2 count=1 -->" in injected, "注入后必须落 v2 签名（快照门禁依据）"
        assert "### [" not in injected and "$$Q_{e}" in injected, "块不带标题，紧跟小节标题"

        # ② 幂等：已注入报告重跑 inject → SKIP 不重复注入
        r = inject()
        assert r.returncode == 0 and "CALC_INJECT_SKIP" in r.stdout, r.stdout
        assert rp.read_text(encoding="utf-8").count("<details>") == 1, "SKIP 不得重复注入"

        # ③ 未知公式 id → 打回且文件不动
        rp.write_text("# 报告\n\n<!-- CALC:Nope -->\n", encoding="utf-8")
        r = inject()
        assert r.returncode == 1 and "CALC_INJECT_ERROR" in r.stdout, r.stdout
        assert "未知公式" in r.stdout, r.stdout
        assert "<details>" not in rp.read_text(encoding="utf-8"), "打回时不得改动报告"

        # ④ 重复占位符 → 打回（防同公式注入两份）
        rp.write_text("# 报告\n\n<!-- CALC:Qe -->\n\n<!-- CALC:Qe -->\n", encoding="utf-8")
        r = inject()
        assert r.returncode == 1 and "CALC_INJECT_ERROR" in r.stdout, r.stdout
        assert "<details>" not in rp.read_text(encoding="utf-8"), "打回时不得改动报告"

        # ⑤ 公式缺占位符（traces 两公式只放一个标记）→ 打回：缺块会被门禁数量核对漏检
        two = {"traces": traces["traces"] + [{
            "id": "Qw", "name": "风吹损失水量", "expression": "Q * drift_rate", "source": "",
            "substituted": "16000 * 0.001", "result": 16.0, "unit": "m3/h", "inputs": [],
        }]}
        tp.write_text(json.dumps(two, ensure_ascii=False), encoding="utf-8")
        rp.write_text("# 报告\n\n<!-- CALC:Qe -->\n", encoding="utf-8")
        r = inject()
        assert r.returncode == 1 and "缺占位符" in r.stdout, r.stdout
        assert "<details>" not in rp.read_text(encoding="utf-8"), "打回时不得改动报告"

        # ⑥ 旧式单一占位符兼容：全块顺序注入
        rp.write_text("# 报告\n\n## 第5章 工艺计算\n\n<!-- CALC_BLOCKS -->\n", encoding="utf-8")
        r = inject()
        assert r.returncode == 0 and "CALC_INJECT_READY: 2" in r.stdout, r.stdout
        assert rp.read_text(encoding="utf-8").count("<details>") == 2

        # ⑦ 无任何占位符 → 打回
        rp.write_text("# 报告（无占位符无签名）\n", encoding="utf-8")
        r = inject()
        assert r.returncode == 1 and "CALC_INJECT_ERROR" in r.stdout, r.stdout
        assert "<details>" not in rp.read_text(encoding="utf-8"), "缺占位符时不得改动报告"


def test_render_calc_blocks_v2_fields() -> None:
    """v2 公式库新字段渲染：trace.symbol 替代代码键名（式中图例）、citation → 依据行、
    description → 取值行中文括注、L/s → m³/h 双单位（样例 84.75L/s=305.1m3/h 形态）。"""
    traces = {"traces": [{
        "id": "backwash_flow", "name": "反洗瞬时流量", "section": "9.1.3",
        "symbol": "q_{bw}",
        "citation": [
            {"code": "GB/T 50050-2017", "clause": "4.0.4", "text": "旁滤水量宜为循环水量的1%~5%"},
            {"code": "90S503", "clause": "", "text": "格网选用图集"},
        ],
        "expression": "filter_area * backwash_intensity * concurrent_backwash",
        "substituted": "11.3 * 15 * 5", "result": 84.75, "unit": "L/s",
        "inputs": [
            {"name": "filter_area", "symbol": "A", "value": 11.3, "unit": "m2",
             "description": "单罐过滤面积", "source": "厂家返资资料", "needs_verification": True},
            {"name": "backwash_intensity", "symbol": "q", "value": 15, "unit": "L/s·m2",
             "description": "反洗强度", "source": "GB/T 50050-2017", "needs_verification": False},
            {"name": "concurrent_backwash", "symbol": "", "value": 5, "unit": "台",
             "description": "", "source": "formula:filter_count.filter_count", "needs_verification": False},
        ],
    }]}
    with tempfile.TemporaryDirectory() as d:
        tp = Path(d) / "traces.json"
        tp.write_text(json.dumps(traces, ensure_ascii=False), encoding="utf-8")
        out = Path(d) / "calc_blocks.md"
        r = subprocess.run(
            [sys.executable, str(SP / "render_calc_blocks.py"), "--traces", str(tp), "--output", str(out)],
            capture_output=True, text=True, encoding="utf-8", env=RUNENV,
        )
        assert r.returncode == 0, r.stderr
        text = out.read_text(encoding="utf-8")
        for needle in [
            "$$q_{bw} = filter_{area} \\times backwash_{intensity} \\times concurrent_{backwash} = 11.3 \\times 15 \\times 5 = 84.75\\ \\text{L/s}$$",
            "- 公式：$q_{bw} = filter_{area} \\times backwash_{intensity} \\times concurrent_{backwash}$",
            # 依据行：clause 在场带条号、缺条号只写规范号（绝不编造），多条以"；"连接
            "- 依据：GB/T 50050-2017 第4.0.4条：旁滤水量宜为循环水量的1%~5%；90S503：格网选用图集",
            # 式中图例：symbol 替代代码键名 + description 中文括注 + 待核实；公式输出回落代码键名+来源标注
            "- 取值：A = 11.3 m²（单罐过滤面积）【待核实】；q = 15 L/(s·m²)（反洗强度）；concurrent_backwash = 5 台（由 [filter_count] 求得）",
            # L/s 双单位（脚本侧确定性 ×3.6）
            "- 结果：**84.75 L/s（= 305.1 m³/h）**",
        ]:
            assert needle in text, f"v2 渲染缺: {needle}"
        assert text.count("CALC_BLOCKS_INJECTED:v2 count=1") == 1


def test_formulas_v2_route_and_execute() -> None:
    """v2 公式库守卫：全部公式可路由（chapter_planner）且默认值+核心参数即可全量执行（无悬空 null 输入）。
    v3 起数量与顺序锁定移至 test_formulas_v3_sample_anchors（37→46）。"""
    formulas_path = SP.parent / "references" / "formulas.json"
    formulas = json.loads(formulas_path.read_text(encoding="utf-8"))["formulas"]
    assert len(formulas) >= 37, f"公式数漂移: {len(formulas)}"
    manifest = chapter_planner.build_manifest(formulas)
    routed = {fid for c in manifest["chapters"] for fid in c["formula_ids"]}
    missing = [f["id"] for f in formulas if f["id"] not in routed]
    assert not missing, f"公式缺章节路由: {missing}"
    # 核心用户参数（样例值）+ 全部带默认值的经验参数 → execute 必须零 KeyError
    core = {"Q": 20000, "delta_t": 9, "N": 5, "pool_area": 520, "V_suction": 1200,
            "pump_motor_spacing": 5.2, "filter_unit_capacity": 40,
            "filter_area": 1.13, "concurrent_backwash": 5}
    state_out = Path(formulas_path.parent.parent / ".." / ".." / ".." / ".tmp-geol" / "cmp" / "guard_state.json").resolve()
    state_out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [sys.executable, str(SP / "formula_runner.py"), "execute",
         "--formulas", str(formulas_path), "--params", json.dumps(core), "--output", str(state_out)],
        capture_output=True, text=True, encoding="utf-8", env=RUNENV,
    )
    assert r.returncode == 0, r.stderr or r.stdout
    state = json.loads(state_out.read_text(encoding="utf-8"))
    assert len(state["results"]) == len(formulas), f"执行结果缺公式: {set(f['id'] for f in formulas) - set(state['results'])}"
    # 抽查样例锚点值（vs sample.md 已核实）
    assert round(state["results"]["backwash_flow"]["backwash_flow"], 2) == 84.75
    assert round(state["results"]["backwash_volume"]["backwash_volume"], 2) == 50.85
    assert round(state["results"]["pumphouse_h1"]["pumphouse_h1"], 3) == 5.885
    assert state["results"]["screen_lift_height"]["screen_lift_height"] == 5.21


def test_snapshot_gate_calc_blocks() -> None:
    """R8/R9 快照门禁：save --report 校验注入契约——占位符残留 / 无签名手写 <details> /
    签名块数与 <details> 总数不符（混合手写）→ SNAPSHOT_ERROR；已注入（签名数==块数）→ SNAPSHOT_READY。"""
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
                capture_output=True, text=True, encoding="utf-8", env=RUNENV,
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
            capture_output=True, text=True, encoding="utf-8", env=RUNENV, check=True,
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
                capture_output=True, text=True, encoding="utf-8", env=RUNENV,
            )
            assert r.returncode == 0, r.stderr
            return json.loads(r.stdout)

        # 对旧状态（N=4）dry-run 改 N=5 → 非空且 ch10/ch6 必在（SKILL 步骤2 的正确顺序）
        state_path.write_text(json.dumps({"all_params": dict(base_params)}), encoding="utf-8")
        before = run_impacted()
        assert "Qb" in before["affected_formulas"], before
        assert "ch6_calc" in before["affected_chapters"], before
        assert "ch10_compliance" in before["affected_chapters"], before

        # update 落盘后，同样的 impacted 差分基准已被覆盖 → 空集（文档化既有语义）
        subprocess.run(
            [sys.executable, str(SP / "formula_runner.py"), "update",
             "--formulas", str(formulas_path), "--state", str(state_path),
             "--param", "N", "--value", "5", "--output", str(state_path)],
            capture_output=True, text=True, encoding="utf-8", env=RUNENV, check=True,
        )
        after = run_impacted()
        assert after["affected_formulas"] == [], after


def test_formulas_v3_sample_anchors() -> None:
    """v3 样例差距批（2026-08-29）：46 式 + pipe_compare，锁吉林院样例锚点。

    - 旧 37 式 id 顺序不变（v2 回归）；
    - 新式锚点：吸水池容积 34x8.5x6.1=1762.9、放空管 750/DN500≈1.06、
      舍维列夫坡降 7000/DN1200→0.0025、21000/DN1600→0.0049（样例比选表 i 列）；
    - 喇叭口几何 4 比值落在 GB/T 50746 §5.4.3 区间（0.698/1.099/0.901/1.50）；
    - pipe_compare：suction 分档判定（DN1000 偏大 / DN1200 满足）+ 显式区间。
    """
    formulas_path = SP.parent / "references" / "formulas.json"
    old37 = ["Qe", "Qw", "Qb", "Qm", "pipe_d_makeup", "pipe_v_makeup", "pipe_d_blowdown",
             "pipe_v_blowdown", "Q_connect", "pipe_v_connect", "V_pool", "V_system",
             "V_ratio_check", "screen_area", "screen_velocity_actual", "screen_drag",
             "screen_lift_weight", "screen_lift_height", "pipe_v_suction", "pipe_v_outlet",
             "pump_foundation_L", "pump_foundation_B", "pump_min_spacing", "bell_mouth_velocity",
             "bell_mouth_ratio", "lift_rope_len", "pumphouse_h1", "pumphouse_height", "Qsf",
             "filter_count", "pipe_v_sidefilter", "backwash_flow", "backwash_single_volume",
             "backwash_volume", "backwash_daily_volume", "backwash_pool_volume",
             "backwash_pump_flow"]
    data = json.loads(formulas_path.read_text(encoding="utf-8"))["formulas"]
    assert len(data) == 46, len(data)
    assert [f["id"] for f in data[:37]] == old37, "旧 37 式顺序被破坏"
    assert [f["id"] for f in data[37:]] == [
        "bell_clearance", "bell_submerge", "bell_rear_wall", "bell_side_wall",
        "V_suction_pool", "pipe_v_drain", "pipe_i_suction", "pipe_i_outlet", "pipe_i_sidefilter"]

    # execute 全量跑通（复用 impacted 测试的 base_params；新式输入均带库内默认值）
    with tempfile.TemporaryDirectory() as d:
        state_path = Path(d) / "formula_state.json"
        base_params = {"Q": 12000, "delta_t": 9, "N": 4, "pool_area": 520, "V_suction": 1200,
                       "KZF": 0.001461, "drift_rate": 0.001, "sf_ratio": 0.05,
                       "effective_depth": 1.5, "backwash_intensity": 15.0, "backwash_duration": 2.0,
                       "pump_motor_spacing": 3.0, "filter_unit_capacity": 100,
                       "filter_area": 10.0, "concurrent_backwash": 1}
        r = subprocess.run(
            [sys.executable, str(SP / "formula_runner.py"), "execute",
             "--formulas", str(formulas_path), "--params", json.dumps(base_params),
             "--output", str(state_path)],
            capture_output=True, text=True, encoding="utf-8", env=RUNENV,
        )
        assert r.returncode == 0, r.stderr
        assert "STATE_READY" in r.stdout, r.stdout
        ap = json.loads(state_path.read_text(encoding="utf-8"))["all_params"]

        def val(k: str) -> float:
            v = ap.get(k, ap.get(f"{k}.{k}"))
            assert v is not None, f"{k} 不在 all_params: {sorted(ap)[:10]}..."
            return float(v)

        assert abs(val("V_suction_pool") - 1762.9) < 0.01, val("V_suction_pool")
        assert abs(val("pipe_v_drain") - 1.061) < 0.01, val("pipe_v_drain")
        assert abs(val("pipe_i_suction") - 0.0025) < 0.0005, val("pipe_i_suction")
        assert abs(val("pipe_i_outlet") - 0.0049) < 0.0005, val("pipe_i_outlet")
        # 旁滤坡降跟随上游 Qsf；JSON 表达式为单分支（仅 v≥1.2 快流区公式，_note 已注明），
        # 低流速过渡区场景由 pipe_compare 的双分支覆盖——测试按同口径计算期望值
        qsf = val("Qsf")
        v_sf = qsf / (3600 * 3.141592653589793 * (500 / 2000) ** 2)
        expect_i = 0.00107 * v_sf ** 2 / 0.5 ** 1.3
        assert abs(val("pipe_i_sidefilter") - expect_i) < 1e-6, (val("pipe_i_sidefilter"), expect_i)
        # 喇叭口几何比值（§5.4.3：距底0.6~0.8 / 淹没>1.0 / 后墙0.8~1.0 / 侧墙1.5）
        assert 0.6 <= val("bell_clearance") <= 0.8, val("bell_clearance")
        assert val("bell_submerge") >= 1.0, val("bell_submerge")
        assert 0.8 <= val("bell_rear_wall") <= 1.0, val("bell_rear_wall")
        assert abs(val("bell_side_wall") - 1.5) < 0.05, val("bell_side_wall")

    # pipe_compare：样例 8.2.1 吸水管比选（suction 分档 DN>1000 → 1.5~2.0 m/s）
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "cmp.json"
        r = subprocess.run(
            [sys.executable, str(SP / "formula_runner.py"), "pipe_compare",
             "--q", "7000", "--dns", "1000,1200", "--mode", "suction", "--output", str(out)],
            capture_output=True, text=True, encoding="utf-8", env=RUNENV,
        )
        assert r.returncode == 0, r.stderr
        assert "PIPE_COMPARE_READY" in r.stdout, r.stdout
        rows = {row["DN"]: row for row in json.loads(out.read_text(encoding="utf-8"))["rows"]}
        assert rows[1200]["verdict"] == "满足" and abs(rows[1200]["v"] - 1.72) < 0.01, rows[1200]
        assert abs(rows[1200]["i"] - 0.0025) < 0.0005, rows[1200]
        assert rows[1000]["verdict"] == "偏大" and abs(rows[1000]["v"] - 2.48) < 0.01, rows[1000]
        # 显式区间优先于分档（旁滤 0.8~1.2 形态）
        r = subprocess.run(
            [sys.executable, str(SP / "formula_runner.py"), "pipe_compare",
             "--q", "7000", "--dns", "1400", "--min-v", "0.8", "--max-v", "1.2",
             "--output", str(out)],
            capture_output=True, text=True, encoding="utf-8", env=RUNENV,
        )
        assert r.returncode == 0, r.stderr
        row = json.loads(out.read_text(encoding="utf-8"))["rows"][0]
        # 7000/DN1400 v≈1.263 > 1.2 → 偏大；v_min/v_max 字段来自显式区间（优先于分档）
        assert row["v_min"] == 0.8 and row["v_max"] == 1.2, row
        assert row["verdict"] == "偏大" and abs(row["v"] - 1.26) < 0.01, row


if __name__ == "__main__":
    test_ch10_compliance_in_manifest_and_impacted()
    test_snapshot_rejects_side_filename()
    test_update_params_output()
    test_impacted_must_run_before_update()
    test_snapshot_warns_on_missing_params()
    test_skill_text_guards()
    test_render_calc_blocks_details()
    test_render_calc_blocks_v2_fields()
    test_formulas_v2_route_and_execute()
    test_formulas_v3_sample_anchors()
    test_render_calc_blocks_inject()
    test_snapshot_gate_calc_blocks()
    print("PASS: bug-2198 / bug-2199(ch10) / update --params-output / impacted 先于 update / SNAPSHOT_WARN / SKILL 守卫 / 反馈3 折叠渲染 / R8+R9 快照门禁 / v2 37式 / v3 样例锚点")
