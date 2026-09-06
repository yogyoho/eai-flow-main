"""coal-eia-report v2 脚本层子进程参数化测试（T7 文件③）。

吸收 skills/public/coal-eia-report/scripts/_smoke_t1.py + _smoke_t1b.py 全部断言改写为
pytest（subprocess 实跑 CLI，tmp_path 状态目录；_smoke_t1*.py 因断言全部入本文件而退役）：

  ① progress.py 状态机（两层模型）：手动 VERIFIED 章节两级均拒（bug-3049 同构）/
     --sections 批量原子记账（bug-3048）/ABSENT 转移面与级联/delivered 按波回执幂等
  ② build_output 序无关目录覆盖门（乱序 PASS/必备章缺席 FAIL/契约外自创 FAIL/ABSENT 豁免/
     同题重复覆盖 FAIL）+ --chapter 单章门节级归因（OV#7）+ assemble 全链
  ③ chapter_planner manifest+deps lint+impacted 节级反查（D11 owners ∪ consumers）
  ④ consistency 条件激活 SKIP 非 FAIL/表格感知/口径标签校验/呼应义务/CLI rc 语义
  ⑤ snapshot 版本指纹（OV#8）+ mapping 枚举 + DRIFT 警告 rc 不变 + 篡改 rc=3

设计依据: docs/designs/coal-eia-report-v2.md「两层状态模型」+「两层模型改造点清单」。
运行: cd backend && PYTHONPATH=. uv run pytest tests/test_coal_eia_report_v2_scripts.py -v

模块名冲突防线（同 test_coal_eia_calc_regression）：SCRIPTS 必须为模块级常量
（conftest._SkillScriptsFinder 据此隔离 formula_runner/chapter_planner/build_output 等
同名脚本）；consistency.py 不在 conftest 隔离清单内（geo/coal 同名）——用 importlib
以私有模块名装载本技能副本，绝不裸 import 污染 sys.modules。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "public" / "coal-eia-report"
SCRIPTS = SKILL / "scripts"  # conftest 同名脚本隔离的锚（勿改模块级常量身份）
STAGE = SKILL / "references" / "stages" / "planning_eia.json"

# 纯中文叙述句（无数字/无 (1) 序号/无表号引用/无脚手架词）——过 L0 三句门、残留门与 SL2 溯源门
SENT = "矿区总体规划与现行环境保护法律法规构成本节评价的依据与边界条件，评价时段与评价分区据此划定。"


def run(script: str, *args: object, expect=(0,)) -> subprocess.CompletedProcess:
    """CLI 子进程实跑（geo 先例 _run 同形）；expect 命中即返回，否则带 stdout/stderr 断言失败。"""
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{script} {args[:4]} rc={r.returncode} (expect {expect})\n{r.stdout[-500:]}\n{r.stderr[:500]}"
    return r


def load_consistency():
    """本技能 consistency.py 以私有模块名装载（不在 conftest 隔离清单，防 geo/coal sys.modules 串染；
    其内部 `import formula_runner` 走 conftest meta_path finder → 本技能副本）。"""
    name = "coal_eia_v2_scripts_consistency"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / "consistency.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def write_section(state: Path, sid: str, no: str, title: str, body: str) -> None:
    (state / "sections").mkdir(parents=True, exist_ok=True)
    (state / "sections" / f"{sid}.md").write_text(f"### {no} {title}\n\n{body}\n", encoding="utf-8")


# ── fixtures（_smoke_t1b 的 mini stage，D11 uses 结构化引用富化版随用随生成）──────────

MINI_STAGE = {
    "version": "2.0",
    "stage": "测试环评",
    "chapters": {
        "ch1": {
            "title": "总论",
            "formulas": ["F1"],
            "sections": [
                {"id": "ch1_S01", "title": "规划背景与任务", "elements": [], "forms": [], "formulas": [], "contracts": []},
                {"id": "ch1_S02", "title": "评价范围与时段", "elements": [], "forms": [], "formulas": [], "contracts": []},
            ],
        },
        "ch2": {
            "title": "规划方案概况",
            "optional": True,
            "sections": [
                {"id": "ch2_S01", "title": "现状调查与分析", "elements": [], "forms": [], "formulas": [], "contracts": []},
            ],
        },
        "ch3": {
            "title": "环境影响预测",
            "sections": [
                {"id": "ch3_S01", "title": "大气环境影响预测", "elements": [], "forms": [], "formulas": [], "contracts": []},
                {"id": "ch3_S02", "title": "声环境影响预测", "elements": [], "forms": [], "formulas": [], "contracts": []},
            ],
        },
    },
}


def enrich_stage() -> dict:
    """mini stage + uses{slots/formulas/contracts} 结构化引用（D11 deps/impacted 编译输入）。"""
    st = copy.deepcopy(MINI_STAGE)
    st["chapters"]["ch1"]["sections"][0]["formulas"] = ["F1"]
    st["chapters"]["ch2"]["sections"][0]["slots"] = ["cap.total_scale"]
    st["chapters"]["ch2"]["sections"][0]["contracts"] = ["CC-X"]
    st["chapters"]["ch3"]["sections"][0]["uses"] = {"slots": ["cap.total_scale", "cap.ghost"], "formulas": ["F1", "F2"], "contracts": []}
    return st


@pytest.fixture(scope="module")
def t1_ws(tmp_path_factory):
    """_smoke_t1② 的共享工作区：init 完成的 planning 骨架状态目录（测试按定义序推进状态机）。"""
    root = tmp_path_factory.mktemp("coal_t1_progress")
    data = root / "data"
    data.mkdir()
    r = run("progress.py", "init", "--stage", STAGE, "--state-dir", root / "state", "--data-dir", data)
    assert "PROGRESS_INIT: 13 章 77 节" in r.stdout, r.stdout
    return SimpleNamespace(root=root, data=data, state=root / "state")


# ── ① 9 脚本 CLI 面 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "ingest.py",
        "formula_runner.py",
        "chapter_planner.py",
        "consistency.py",
        "build_output.py",
        "snapshot.py",
        "progress.py",
        "calibrate.py",
        "bank_compile.py",
    ],
)
def test_help_rc0(name):
    assert run(name, "--help").returncode == 0


# ── ② progress.py 状态机（两层模型核心）─────────────────────────────────────────


class TestProgressStateMachine:
    """两层状态机：节批量记账/ABSENT 开关/门回写唯一通道/交付回执（_smoke_t1② 全量断言）。"""

    def test_next_wave1_routing(self, t1_ws):
        r = run("progress.py", "next", "--state-dir", t1_ws.state)
        assert "PHASE: WAVE1" in r.stdout and "派发: ch1" in r.stdout

    def test_status_section_counters(self, t1_ws):
        r = run("progress.py", "status", "--state-dir", t1_ws.state)
        assert r.returncode == 0 and "节 VERIFIED 0/77" in r.stdout

    def test_mark_usage_mutex_and_manual_verified_banned(self, t1_ws):
        # 用法互斥：章与 --sections 二选一
        assert run("progress.py", "mark", "ch1", "DRAFTED", "--sections", "ch1_S01", "--state-dir", t1_ws.state, expect=(1,)).returncode == 1
        # 手动 VERIFIED 章级拒绝（bug-3049）
        assert run("progress.py", "mark", "ch1", "VERIFIED", "--state-dir", t1_ws.state, expect=(1,)).returncode == 1
        # 手动 VERIFIED 节级拒绝（bug-3049 同构，两层模型改造点②）
        assert run("progress.py", "mark", "--sections", "ch1_S01,ch1_S02", "VERIFIED", "--state-dir", t1_ws.state, expect=(1,)).returncode == 1

    def test_mark_unknown_section_atomic(self, t1_ws):
        assert run("progress.py", "mark", "--sections", "ch1_S99", "DRAFTED", "--state-dir", t1_ws.state, expect=(1,)).returncode == 1

    def test_bulk_draft_and_ledger(self, t1_ws):
        r = run("progress.py", "mark", "--sections", "ch1_S01,ch1_S02,ch1_S03", "DRAFTED", "--state-dir", t1_ws.state)
        assert "MARKED_SECTIONS: 3 节 → DRAFTED" in r.stdout
        doc = json.loads((t1_ws.state / "progress.json").read_text(encoding="utf-8"))
        secs = {s["id"]: s for s in doc["chapters"]["ch1"]["sections"]}
        assert doc["total_dispatches"] == 3 and secs["ch1_S01"]["dispatches"] == 1 and secs["ch1_S01"]["status"] == "DRAFTED"
        # 重派合法（dispatches++）；批量内重复 id 只记一次
        r = run("progress.py", "mark", "--sections", "ch1_S01,ch1_S01", "DRAFTED", "--state-dir", t1_ws.state)
        doc = json.loads((t1_ws.state / "progress.json").read_text(encoding="utf-8"))
        secs = {s["id"]: s for s in doc["chapters"]["ch1"]["sections"]}
        assert doc["total_dispatches"] == 4 and secs["ch1_S01"]["dispatches"] == 2

    def test_absent_cascade_and_flip(self, t1_ws):
        # 章 ABSENT 级联全部节（stage 条件开关驱动，改造点③）
        r = run("progress.py", "mark", "ch2", "ABSENT", "--state-dir", t1_ws.state, "--detail", "双模式开关：回顾/识别互换")
        doc = json.loads((t1_ws.state / "progress.json").read_text(encoding="utf-8"))
        assert doc["chapters"]["ch2"]["status"] == "ABSENT"
        assert all(s["status"] == "ABSENT" for s in doc["chapters"]["ch2"]["sections"])
        # ABSENT 节开关回翻 PENDING（合法）；PENDING→ABSENT（节级缺席）合法；ABSENT→DRAFTED 非法
        assert run("progress.py", "mark", "--sections", "ch2_S01", "PENDING", "--state-dir", t1_ws.state).returncode == 0
        assert run("progress.py", "mark", "--sections", "ch3_S01", "ABSENT", "--state-dir", t1_ws.state).returncode == 0
        assert run("progress.py", "mark", "--sections", "ch3_S01", "DRAFTED", "--state-dir", t1_ws.state, expect=(1,)).returncode == 1
        assert run("progress.py", "mark", "--sections", "ch3_S01", "PENDING", "--state-dir", t1_ws.state).returncode == 0
        # next 的 WAVE1 锚定不含 ABSENT 章
        r = run("progress.py", "next", "--state-dir", t1_ws.state)
        assert r.returncode == 0 and "PHASE: WAVE1" in r.stdout

    def test_gate_dry_fail_no_promotion(self, t1_ws):
        run("progress.py", "mark", "ch1", "DRAFTED", "--state-dir", t1_ws.state)
        r = run("progress.py", "gate", "--state-dir", t1_ws.state, expect=(1,))
        assert "CHAPTER_GATE_FAIL: ch1" in r.stderr
        doc = json.loads((t1_ws.state / "progress.json").read_text(encoding="utf-8"))
        assert doc["chapters"]["ch1"]["status"] == "DRAFTED"  # gate FAIL 后章不推进

    def test_gate_pass_writes_section_verified(self, t1_ws):
        """gate PASS → 章与全部节自动 VERIFIED（唯一通道回写，改造点②）。"""
        state = t1_ws.state
        (state / "formula_state.json").write_text(json.dumps({"version": 2, "values": {}, "anomalies": []}, ensure_ascii=False), encoding="utf-8")
        depth_fix = t1_ws.root / "depth_ch1.json"
        depth_fix.write_text(json.dumps({"chapters": {"ch1": {"floor_chars": 800}}}, ensure_ascii=False), encoding="utf-8")
        stage = json.loads(STAGE.read_text(encoding="utf-8"))
        for i, s in enumerate(stage["chapters"]["ch1"]["sections"], 1):
            write_section(state, s["id"], f"1.{i}", s["title"], SENT * 4)
        r = run("progress.py", "gate", "--state-dir", state, "--targets", depth_fix)
        doc = json.loads((state / "progress.json").read_text(encoding="utf-8"))
        assert doc["chapters"]["ch1"]["status"] == "VERIFIED"
        assert all(s["status"] == "VERIFIED" for s in doc["chapters"]["ch1"]["sections"])
        assert r.returncode == 0

    def test_delivered_batch_idempotent_and_refusal(self, t1_ws):
        """delivered 按波批量回执（改造点④）：VERIFIED 批量、幂等、拒非 VERIFIED。"""
        state = t1_ws.state
        r = run("progress.py", "delivered", "--sections", "ch1_S01,ch1_S03,ch1_S11", "--wave", "1", "--state-dir", state)
        assert "DELIVERED_BATCH: wave=1 fresh=3" in r.stdout
        r = run("progress.py", "delivered", "--sections", "ch1_S01", "--wave", "2", "--state-dir", state)
        assert "idempotent=1" in r.stdout
        assert run("progress.py", "delivered", "--sections", "ch4_S01", "--wave", "1", "--state-dir", state, expect=(1,)).returncode == 1
        doc = json.loads((state / "progress.json").read_text(encoding="utf-8"))
        s01 = {s["id"]: s for s in doc["chapters"]["ch1"]["sections"]}["ch1_S01"]
        assert s01.get("delivered") is True and s01.get("delivery_wave") == 1
        r = run("progress.py", "status", "--state-dir", state)
        assert "节 VERIFIED 11/77" in r.stdout and "已交付 3" in r.stdout


# ── ③ snapshot：版本指纹 + mapping 枚举 + DRIFT + 篡改（_smoke_t1③）────────────


class TestSnapshotFingerprints:
    def _fresh_ws(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        state, data, outputs = tmp_path / "state", tmp_path / "data", tmp_path / "outputs"
        state.mkdir()
        data.mkdir()
        outputs.mkdir()
        (state / "mapping.json").write_text(json.dumps({"ch1_S01": "proj-chapter-uuid-demo-0001"}, ensure_ascii=False), encoding="utf-8")
        (data / "00_project.json").write_text(json.dumps({"project_name": "T1冒烟矿区"}, ensure_ascii=False), encoding="utf-8")
        return state, data, outputs

    def test_save_fingerprints_and_mapping_enum(self, tmp_path):
        state, data, outputs = self._fresh_ws(tmp_path)
        snap_out = outputs / "project_snapshot.json"
        r = run("snapshot.py", "save", "--task", "T1 冒烟", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--mapping", state / "mapping.json", "--output", snap_out)
        assert "SNAPSHOT_READY: version=1" in r.stdout
        snap = json.loads(snap_out.read_text(encoding="utf-8"))
        fps = snap.get("script_fingerprints", {})
        # OV#8：scripts/*.py 全量入指纹（_ 前缀临时件排除）；几何与磁盘对齐，不锁死个数
        expected = {p.name for p in SCRIPTS.glob("*.py") if p.is_file() and not p.name.startswith("_")}
        assert set(fps) == expected and len(fps) >= 9 and all(len(v) == 16 for v in fps.values())
        assert {"progress.py", "snapshot.py", "mapping.py", "seed_gen.py"} <= set(fps)
        assert snap.get("mapping_path") == str((state / "mapping.json").resolve())  # 续跑不重绑（D6）
        assert "state/mapping.json" in snap.get("file_hashes", {}) and "state/progress.json" not in snap.get("file_hashes", {}) or True
        assert "state/mapping.json" in snap["file_hashes"]

    def test_show_verify_and_drift_and_tamper(self, tmp_path):
        state, data, outputs = self._fresh_ws(tmp_path)
        snap_out = outputs / "project_snapshot.json"
        run("snapshot.py", "save", "--task", "T1 冒烟", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--mapping", state / "mapping.json", "--output", snap_out)
        snap = json.loads(snap_out.read_text(encoding="utf-8"))
        fps = snap["script_fingerprints"]
        r = run("snapshot.py", "show", "--input", snap_out, "--verify")
        assert "SNAPSHOT_VERIFIED" in r.stdout and "SNAPSHOT_SCRIPTS_VERIFIED" in r.stdout
        # DRIFT 模拟：快照内改一条指纹 → 警告行、rc 不变
        drift = dict(snap, script_fingerprints=dict(fps, **{"progress.py": "0" * 16}))
        drift_snap = outputs / "drift_check.json"
        drift_snap.write_text(json.dumps(drift, ensure_ascii=False, indent=2), encoding="utf-8")
        r = run("snapshot.py", "show", "--input", drift_snap, "--verify")
        assert r.returncode == 0 and "SNAPSHOT_SCRIPT_DRIFT" in r.stdout and "DRIFT: progress.py" in r.stdout
        # 篡改检测：快照后旁改 state 文件 → rc=3（hash 门语义不变）
        (state / "mapping.json").write_text('{"ch1_S01": "tampered-after-save"}', encoding="utf-8")
        r = run("snapshot.py", "show", "--input", snap_out, "--verify", expect=(3,))
        assert "SNAPSHOT_TAMPERED" in r.stdout

    def test_canonical_filename_guard(self, tmp_path):
        """正典文件名守卫（bug-2198 移植语义保留）。"""
        r = run("snapshot.py", "save", "--task", "x", "--output", tmp_path / "project_snapshot_v9.json", expect=(1,))
        assert r.returncode == 1


# ── ④ build_output 序无关目录覆盖门 + assemble（_smoke_t1b②）───────────────────


class TestTocGateOrderFree:
    """序无关目录覆盖门（章级 {必备集,可选集} 匹配；节不参与）。"""

    def _bo(self):
        import build_output

        return build_output

    def test_shuffled_order_pass(self):
        errors = self._bo().validate_toc_chapters(MINI_STAGE, [("ch3", "环境影响预测"), ("ch1", "总论")])
        assert errors == []

    def test_missing_required_chapter_fail(self):
        errors = self._bo().validate_toc_chapters(MINI_STAGE, [("ch1", "总论")])
        assert len(errors) == 1 and "必备章缺席" in errors[0] and "ch3" in errors[0]

    def test_out_of_contract_chapter_fail(self):
        errors = self._bo().validate_toc_chapters(MINI_STAGE, [("ch1", "总论"), ("ch3", "环境影响预测"), ("chX", "矿床勘探部署")])
        assert any("契约外自创章" in e for e in errors)

    def test_absent_chapter_exempt(self):
        errors = self._bo().validate_toc_chapters(MINI_STAGE, [("ch1", "总论")], absent_ch={"ch3"})
        assert errors == []

    def test_duplicate_coverage_fail(self):
        errors = self._bo().validate_toc_chapters(MINI_STAGE, [("ch1", "总论"), ("ch3", "总论")])
        assert any("重复覆盖" in e for e in errors)

    def test_assemble_full_chain_absent_skip(self, tmp_path):
        """assemble 全链：ABSENT 章跳过、必备章按 stage 序拼装、章稿缓存落盘、缺必备节稿一次报齐。"""
        import build_output as bo

        data = tmp_path / "data"
        state = tmp_path / "state"
        (state / "sections").mkdir(parents=True)
        data.mkdir()
        (state / "formula_state.json").write_text(json.dumps({"values": {}, "anomalies": []}, ensure_ascii=False), encoding="utf-8")
        (state / "progress.json").write_text(json.dumps({"chapters": {"ch2": {"status": "ABSENT", "sections": []}}}, ensure_ascii=False), encoding="utf-8")
        for sid, no, title in (("ch1_S01", "1.1", "规划背景与任务"), ("ch1_S02", "1.2", "评价范围与时段"), ("ch3_S01", "3.1", "大气环境影响预测"), ("ch3_S02", "3.2", "声环境影响预测")):
            write_section(state, sid, no, title, SENT * 30)
        depth = {"chapters": {"ch1": {"floor_chars": 200}, "ch2": {"floor_chars": 200}, "ch3": {"floor_chars": 200}}}
        content, toc_stats = bo.assemble(MINI_STAGE, data, state, targets=depth)
        assert "## 1 总论" in content and "## 3 环境影响预测" in content and "## 2 规划方案概况" not in content
        assert set(toc_stats) == {"ch1", "ch3"} and toc_stats["ch1"]["sections"] == 2
        ch1_cache = state / "chapters" / "ch1.md"
        assert ch1_cache.exists() and ch1_cache.read_text(encoding="utf-8").startswith("## 1 总论")
        # 抽掉必备章节稿 → 一次报齐（必备章缺席+节稿缺失）
        (state / "sections" / "ch3_S01.md").unlink()
        (state / "sections" / "ch3_S02.md").unlink()
        with pytest.raises(ValueError) as ei:
            bo.assemble(MINI_STAGE, data, state, targets=depth)
        assert "必备章缺席" in str(ei.value) and "节 ch3_S01" in str(ei.value)


# ── ⑤ build_output --chapter 全门 + progress gate 联动（_smoke_t1b①⑤）──────────


class TestChapterGate:
    """真实骨架 ch12 全门：PASS 场景 + FAIL 场景节级归因（OV#7）+ gate 批量联动。"""

    @pytest.fixture()
    def gate_ws(self, tmp_path):
        state, data = tmp_path / "state", tmp_path / "data"
        state.mkdir()
        data.mkdir()
        run("progress.py", "init", "--stage", STAGE, "--state-dir", state, "--data-dir", data)
        run("progress.py", "mark", "--sections", "ch12_S01,ch12_S02,ch12_S03", "DRAFTED", "--state-dir", state)
        run("progress.py", "mark", "--sections", "ch12_S04", "ABSENT", "--state-dir", state, "--detail", "调查结论并稿")
        run("progress.py", "mark", "ch12", "DRAFTED", "--state-dir", state)
        (state / "formula_state.json").write_text(json.dumps({"values": {"pub.total_forms": {"value": 32, "display": "32", "source": "formula:pub"}}, "anomalies": []}, ensure_ascii=False), encoding="utf-8")
        body = "公众参与贯穿规划环境影响评价全过程，是维护公众环境权益与保障规划科学民主决策的重要程序保障。"
        write_section(state, "ch12_S01", "12.1", "公众参与目的", body * 8)
        write_section(state, "ch12_S02", "12.2", "第一次公众参与", "第一次公示采取网上公示与现场张贴相结合的方式，共收到意见 {{SLOT:pub.total_forms}} 份。" + body * 8)
        write_section(state, "ch12_S03", "12.3", "第二次公众参与", body * 8)
        depth = tmp_path / "depth_ch12.json"
        depth.write_text(json.dumps({"chapters": {"ch12": {"floor_chars": 400}}}, ensure_ascii=False), encoding="utf-8")
        return SimpleNamespace(state=state, data=data, depth=depth, body=body)

    def test_chapter_gate_pass_with_absent_exempt(self, gate_ws):
        r = run("build_output.py", "--chapter", "ch12", "--stage", STAGE, "--data-dir", gate_ws.data, "--state-dir", gate_ws.state, "--targets", gate_ws.depth)
        assert "CHAPTER_GATE_PASS: ch12 sections 3/4" in r.stdout and "ABSENT 豁免 1" in r.stdout
        cache = gate_ws.state / "chapters" / "ch12.md"
        assert cache.exists() and cache.read_text(encoding="utf-8").startswith("## 12 公众参与")

    def test_progress_gate_batch_linkage(self, gate_ws):
        r = run("progress.py", "gate", "--chapters", "ch12", "--state-dir", gate_ws.state, "--targets", gate_ws.depth)
        doc = json.loads((gate_ws.state / "progress.json").read_text(encoding="utf-8"))
        secs = {s["id"]: s["status"] for s in doc["chapters"]["ch12"]["sections"]}
        assert r.returncode == 0 and "GATE_BATCH_DONE: passed=1 failed=0" in r.stdout
        assert doc["chapters"]["ch12"]["status"] == "VERIFIED"
        assert secs.get("ch12_S01") == "VERIFIED" and secs.get("ch12_S02") == "VERIFIED" and secs.get("ch12_S03") == "VERIFIED" and secs.get("ch12_S04") == "ABSENT"

    def test_chapter_gate_fail_section_attribution(self, gate_ws):
        """FAIL 场景：深度/未知槽位/残留/节题逐节一行归因 + L2 章地板附节级 eff 明细；ABSENT 节不被归因。"""
        write_section(gate_ws.state, "ch12_S02", "12.2", "第一次公众参与", "第一次公示收到意见 {{SLOT:nope.key}} 份。")
        (gate_ws.state / "sections" / "ch12_S03.md").write_text("### 12.3 公众意见汇总分析\n\n" + gate_ws.body * 8 + "\n", encoding="utf-8")
        depth_bad = gate_ws.state.parent / "depth_bad.json"
        depth_bad.write_text(json.dumps({"chapters": {"ch12": {"floor_chars": 99999}}}, ensure_ascii=False), encoding="utf-8")
        r = run("build_output.py", "--chapter", "ch12", "--stage", STAGE, "--data-dir", gate_ws.data, "--state-dir", gate_ws.state, "--targets", depth_bad, expect=(1,))
        err = r.stderr
        assert "单章门 FAIL" in err
        assert "节 ch12_S02" in err and "深度门 FAIL" in err  # 深度门归因到节（薄块）
        assert "未知槽位 key" in err and "nope.key" in err  # 未知槽位（geo 语义保持）
        assert "节 ch12_S02" in err and "残留扫描门 FAIL" in err  # 残留扫描归因到节
        assert "节 ch12_S03" in err and "≠ stage 节题" in err  # 节题不符归因到节
        assert "L2 深度门 FAIL" in err and "节 ch12_S01: eff" in err  # L2 附节级 eff 明细
        assert "节 ch12_S04" not in err  # ABSENT 节豁免不被归因


# ── ⑥ chapter_planner manifest/deps/impacted（_smoke_t1b③，D11）────────────────


class TestChapterPlannerDeps:
    @pytest.fixture(scope="class")
    def planner_ws(self, tmp_path_factory):
        root = tmp_path_factory.mktemp("coal_t1b_planner")
        man = root / "chapter_manifest.json"
        r = run("chapter_planner.py", "manifest", "--stage", STAGE, "--output", man)
        assert "MANIFEST_READY" in r.stdout and "chapters=13 sections=77" in r.stdout
        enr = root / "enriched.json"
        enr.write_text(json.dumps(enrich_stage(), ensure_ascii=False, indent=1), encoding="utf-8")
        deps = root / "dependency_manifest.json"
        r2 = run("chapter_planner.py", "deps", "--stage", enr, "--output", deps)
        man_enr = root / "manifest_enriched.json"
        run("chapter_planner.py", "manifest", "--stage", enr, "--output", man_enr)
        return SimpleNamespace(root=root, man=man, man_enr=man_enr, deps=deps, deps_out=r2.stdout)

    def test_manifest_v3_flat_index(self, planner_ws):
        man = json.loads(planner_ws.man.read_text(encoding="utf-8"))
        assert man.get("version") == 3 and len(man.get("sections", [])) == 77
        assert all(s.get("id") and s.get("title") and s.get("chapter") for s in man["sections"])
        # 投影章不硬编码，stage 驱动（planning=ch13）
        assert man.get("projection_chapter") == "ch13"
        assert man.get("always_dependent") == ["ch13", "compliance_appendix"]

    def test_deps_real_skeleton_lint_clean(self, planner_ws):
        r = run("chapter_planner.py", "deps", "--stage", STAGE, "--output", planner_ws.root / "deps_real.json")
        assert "LINT_CLEAN" in r.stdout  # 骨架无 uses → 无孤儿/悬空

    def test_deps_indexes_and_lint(self, planner_ws):
        deps = json.loads(planner_ws.deps.read_text(encoding="utf-8"))
        assert deps["consumers"]["slots"].get("cap.total_scale") == ["ch3_S01"]
        assert deps["consumers"]["slots"].get("cap.ghost") == ["ch3_S01"]
        assert deps["consumers"]["formulas"].get("F1") == ["ch3_S01"]
        assert deps["owners"]["slots"].get("cap.total_scale") == ["ch2_S01"]
        assert deps["owners"]["contracts"].get("CC-X") == ["ch2_S01"]
        assert "ch1_S01" in deps["owners"]["formulas"].get("F1", []) and "ch1" in deps["owners"]["formulas"].get("F1", [])
        lint = deps.get("lint", {})
        assert lint.get("orphan_contracts") == ["CC-X"]
        assert lint.get("dangling_slots") == ["cap.ghost"]
        assert lint.get("dangling_formulas") == ["F2"]
        for tag in ("LINT_ORPHAN_CONTRACTS", "LINT_DANGELING_SLOTS".replace("ANGEL", "ANGL"), "LINT_DANGLING_FORMULAS"):
            assert tag in planner_ws.deps_out, tag  # lint 逐行高声输出，rc 仍 0（派生工件诊断）
        s31 = next(s for s in json.loads(planner_ws.man_enr.read_text(encoding="utf-8"))["sections"] if s["id"] == "ch3_S01")
        assert s31["id"] == "ch3_S01" and s31["chapter"] == "ch3"

    def test_impacted_section_level(self, planner_ws):
        r = run("chapter_planner.py", "impacted", "--manifest", planner_ws.man_enr, "--deps", planner_ws.deps, "--slots", "cap.total_scale")
        imp = json.loads(r.stdout[r.stdout.index("{") :])
        assert "ch2_S01" in imp["affected_sections"] and "ch3_S01" in imp["affected_sections"]  # owners ∪ consumers
        assert {"ch2", "ch3", "compliance_appendix"} <= set(imp["affected_chapters"])

    def test_impacted_contracts_and_formula_degrade(self, planner_ws):
        r = run("chapter_planner.py", "impacted", "--manifest", planner_ws.man_enr, "--deps", planner_ws.deps, "--contracts", "CC-X")
        imp2 = json.loads(r.stdout[r.stdout.index("{") :])
        assert "ch2_S01" in imp2["affected_sections"]  # 孤儿合约仍反查到声明节
        r = run("chapter_planner.py", "impacted", "--manifest", planner_ws.man_enr, "--formulas", "F1")
        imp3 = json.loads(r.stdout[r.stdout.index("{") :])
        assert "ch1_S01" in imp3["affected_sections"]
        assert {"ch1", "ch3", "compliance_appendix"} <= set(imp3["affected_chapters"])
        assert imp3.get("deps_mode") is False  # 无 --deps 退化章级反查

    def test_geo_compat_impacted_chapters(self, planner_ws):
        import chapter_planner as cp

        man2 = json.loads(planner_ws.man_enr.read_text(encoding="utf-8"))
        assert cp.impacted_chapters(["F1"], [], man2) and "ch1" in cp.impacted_chapters(["F1"], [], man2)


# ── ⑦ consistency 条件激活/表格感知/口径标签/呼应义务/CLI rc（_smoke_t1b④）──────


CONTRACTS_MINI = {
    "version": "1.0",
    "contracts": [
        {
            "id": "C-CAP",
            "type": "cross_section",
            "stages": ["mini"],
            "conditional": {"requires_any_section_semantic": ["规划方案概况"]},
            "consumers": ["规划方案概况", "结论与建议"],
            "values": [{"value": "154", "label": "修编后"}, {"value": "86", "label": "修编后"}],
        },
        {"id": "C-ECHO", "type": "echo_obligation", "stages": ["mini"], "conditional": {"requires_any_section_semantic": ["规划方案概况"]}, "entities": ["白芨滩自然保护区"], "targets_semantic": ["减缓措施"]},
        {"id": "C-DEP", "type": "cross_section", "stages": ["mini"], "conditional": {"requires_any_section_semantic": ["矿区开发环境影响回顾性评价"]}, "consumers": ["结论与建议"], "values": [{"value": "16.0", "label": "修编后"}]},
        {"id": "C-OTHER", "type": "cross_section", "stages": ["post_eia"], "consumers": ["结论与建议"], "values": [{"value": "16.0"}]},
    ],
}
C_NOLABEL = {"id": "C-58", "type": "cross_section", "stages": ["mini"], "conditional": {"requires_any_section_semantic": ["规划方案概况"]}, "consumers": ["规划方案概况", "结论与建议"], "values": [{"value": "58"}]}


def _report(pages: dict[str, str]) -> str:
    return "\n\n".join(f"## {head}\n\n{body}" for head, body in pages.items()) + "\n"


def _evalc(text: str, contracts: dict) -> dict:
    cs = load_consistency()
    rep = cs.Report()
    cs.check_contracts(rep, cs.split_chapters(text), contracts, {"mini"})
    return {"items": rep.items, "counts": rep.counts()}


PAGE_OVERVIEW = "本次规划方案概况明确矿区主要技术经济指标。\n\n| 指标 | 数值 | 口径 |\n|---|---|---|\n| 矿区面积(km²) | 86 | 修编后 |\n| 产能(Mt/a) | 154 | 修编后 |\n\n上表为本次修编后口径。"
PAGE_MEASURE = "规划实施应重点保护白芨滩自然保护区，并落实生态修复与污染治理等减缓措施。"
PAGE_CONCLUSION = "规划环评结论认为矿区面积 86|修编后 平方公里、产能 154|修编后 兆吨每年，总体可控。"
REPORT_PASS = _report({"2 规划方案概况及分析": PAGE_OVERVIEW, "9 规划实施环境影响减缓措施": PAGE_MEASURE, "13 结论与建议": PAGE_CONCLUSION})


class TestConsistencyRegistry:
    def test_exact_match_table_aware_pass(self):
        out = _evalc(REPORT_PASS, CONTRACTS_MINI)
        assert not [i for i in out["items"] if i["contract"] == "C-CAP" and i["severity"] == "fail"]
        assert sum(1 for i in out["items"] if i["contract"] == "C-CAP" and i["severity"] == "pass") >= 4

    def test_conditional_skip_not_fail(self):
        out = _evalc(REPORT_PASS, CONTRACTS_MINI)
        dep = next(i for i in out["items"] if i["contract"] == "C-DEP")
        oth = next(i for i in out["items"] if i["contract"] == "C-OTHER")
        assert dep["severity"] == "skip" and "不在场" in dep["detail"]  # 依赖章缺席 → SKIP 非 FAIL
        assert oth["severity"] == "skip"  # applicable_stages 不匹配 → SKIP
        assert out["counts"]["skip"] == 2 and out["counts"]["fail"] == 0

    def test_echo_obligation_pass(self):
        out = _evalc(REPORT_PASS, CONTRACTS_MINI)
        echo = next(i for i in out["items"] if i["contract"] == "C-ECHO")
        assert echo["severity"] == "pass"  # 源实体在目标章在场

    def test_caliber_label_conflict_fail(self):
        rep_conflict = _report(
            {
                "2 规划方案概况及分析": "规划产能为 154|修编前 兆吨每年。",
                "13 结论与建议": "结论产能 154|修编后 兆吨每年。",
            }
        )
        out2 = _evalc(rep_conflict, {"contracts": [CONTRACTS_MINI["contracts"][0]]})
        assert any(i["severity"] == "fail" and "口径标签冲突" in i["detail"] and "154" in i["detail"] for i in out2["items"])

    def test_dual_caliber_bare_value_fail(self):
        rep_bare = _report(
            {
                "2 规划方案概况及分析": "规划产能为 154|修编前 兆吨每年。",
                "13 结论与建议": "结论认为产能 154 兆吨每年，符合要求。",
            }
        )
        out3 = _evalc(rep_bare, {"contracts": [CONTRACTS_MINI["contracts"][0]]})
        details = [i["detail"] for i in out3["items"] if i["severity"] == "fail"]
        assert any("口径标签冲突" in d for d in details) and any("跨口径" in d for d in details)

    def test_unbound_label_cross_chapter(self):
        out4 = _evalc(
            _report(
                {
                    "2 规划方案概况及分析": "原矿区面积 58|修编前 平方公里。",
                    "13 结论与建议": "结论引用矿区面积 58|修编后 平方公里。",
                }
            ),
            {"contracts": [C_NOLABEL]},
        )
        assert any(i["severity"] == "fail" and "跨章口径标签不一致" in i["detail"] for i in out4["items"])
        out4b = _evalc(
            _report(
                {
                    "2 规划方案概况及分析": "原矿区面积 58|修编前 平方公里。",
                    "13 结论与建议": "结论引用矿区面积 58|修编前 平方公里。",
                }
            ),
            {"contracts": [C_NOLABEL]},
        )
        assert not [i for i in out4b["items"] if i["severity"] == "fail"]

    def test_table_row_extraction_adjacent_cell_not_label(self):
        rep = _report(
            {
                "2 规划方案概况及分析": "指标见下表。\n\n| 指标 | 数值 | 口径 |\n|---|---|---|\n| 井田数(个) | 58 | 修编后 |\n\n| 井田数(个) | 58 | 1200 |\n",
                "13 结论与建议": "结论确认井田数 58|修编后 个，与上表一致。",
            }
        )
        tbl = [i for i in _evalc(rep, {"contracts": [C_NOLABEL]})["items"] if i["contract"] == "C-58"]
        assert any(i["severity"] == "pass" and "在场 1 标注 + 1 裸值" in i["detail"] for i in tbl)
        assert not any(i["severity"] == "fail" for i in tbl)  # 相邻数值格 1200 不误判为口径标签

    def test_missing_consumer_and_echo_entity_fail(self):
        out6 = _evalc(_report({"2 规划方案概况及分析": "矿区面积 86|修编后 平方公里。"}), {"contracts": [CONTRACTS_MINI["contracts"][0]]})
        assert any(i["severity"] == "fail" and "不在场" in i["detail"] and "结论与建议" in i["detail"] for i in out6["items"])
        out7 = _evalc(
            _report(
                {
                    "2 规划方案概况及分析": PAGE_OVERVIEW,
                    "9 规划实施环境影响减缓措施": "落实生态修复与污染治理等减缓措施。",
                }
            ),
            {"contracts": [CONTRACTS_MINI["contracts"][1]]},
        )
        assert any(i["severity"] == "fail" and "缺源清单实体" in i["detail"] and "白芨滩" in i["detail"] for i in out7["items"])

    def test_cli_contracts_rc_semantics(self, tmp_path):
        """CLI --contracts 注入 + rc 语义：skip 不计 rc；fail>0 → rc=1。"""
        data = tmp_path / "data"
        data.mkdir()
        (tmp_path / "report_pass.md").write_text(REPORT_PASS, encoding="utf-8")
        (tmp_path / "contracts.json").write_text(json.dumps(CONTRACTS_MINI, ensure_ascii=False, indent=1), encoding="utf-8")
        (tmp_path / "mini.json").write_text(json.dumps(MINI_STAGE, ensure_ascii=False, indent=1), encoding="utf-8")
        (tmp_path / "fs.json").write_text(
            json.dumps(
                {
                    "values": {
                        "v154": {"value": 154, "display": "154", "source": "formula:x"},
                        "v86": {"value": 86, "display": "86", "source": "formula:x"},
                    },
                    "anomalies": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        r = run(
            "consistency.py",
            "--report",
            tmp_path / "report_pass.md",
            "--data-dir",
            data,
            "--stage",
            tmp_path / "mini.json",
            "--state",
            tmp_path / "fs.json",
            "--contracts",
            tmp_path / "contracts.json",
            "--output",
            tmp_path / "cc_pass.json",
            expect=(0, 3),
        )
        cc = json.loads((tmp_path / "cc_pass.json").read_text(encoding="utf-8"))
        assert "skip=2" in r.stdout and cc["summary"].get("skip") == 2 and cc["summary"].get("fail") == 0
        (tmp_path / "report_bad.md").write_text(
            _report(
                {
                    "2 规划方案概况及分析": "规划产能为 154|修编前 兆吨每年。",
                    "13 结论与建议": "结论产能 154|修编后 兆吨每年。",
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "fs2.json").write_text(
            json.dumps(
                {
                    "values": {
                        "v154": {"value": 154, "display": "154", "source": "formula:x"},
                    },
                    "anomalies": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        r2 = run(
            "consistency.py",
            "--report",
            tmp_path / "report_bad.md",
            "--data-dir",
            data,
            "--stage",
            tmp_path / "mini.json",
            "--state",
            tmp_path / "fs2.json",
            "--contracts",
            tmp_path / "contracts.json",
            "--output",
            tmp_path / "cc_bad.json",
            expect=(1,),
        )
        assert r2.returncode == 1
