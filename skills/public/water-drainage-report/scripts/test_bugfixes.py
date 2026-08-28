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
    ]:
        assert needle in text, f"SKILL.md 缺铁律文本: {needle}"


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
    print("PASS: bug-2198 守卫 / bug-2199 ch11+params 刷新 / update --params-output / impacted 先于 update / SNAPSHOT_WARN / SKILL 文本守卫")
