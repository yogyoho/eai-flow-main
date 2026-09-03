"""progress.py 状态机单元测试（spec 2026-08-28 控制器化改造 §5.1）。

覆盖：init 全 PENDING / next 五相位路由（WAVE1→NEGOTIATE→KEY_POINTS→WAVE2→FINAL）/
mark 转移合法性（bug-3049：手动 mark VERIFIED 一律拒，VERIFIED 唯一通道=progress.py gate
真跑单章门自动转正；非法转移拒）/ approve-downgrade 留痕 /
预算耗尽路由 / snapshot.hash_manifest 对 state/ 新文件的自动覆盖（spec §5.7）。

运行: cd backend && PYTHONPATH=. uv run pytest tests/test_geo_progress.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "public" / "geological-report" / "scripts"
STAGE = REPO_ROOT / "skills" / "public" / "geological-report" / "references/stages/exploration.json"

sys.path.insert(0, str(SCRIPTS))


def run(*args, expect=(0,)):
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "progress.py"), *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout}\n{r.stderr}"
    return r


def gate_pass(ws, chapters: list[str] | None = None) -> None:
    """bug-3049 后 VERIFIED 唯一合法通道 = `progress.py gate` 真跑单章门 PASS 自动转正。

    测试进程内替身：monkeypatch build_output.run_chapter_gate 为无异常返回（=门 PASS——
    cmd_gate 的推进凭据就是 run_chapter_gate 无异常）+ resolve_targets 为空基准（夹具无 data/ 树），
    走 cmd_gate 同一条「跑门 → PASS 章自动回写 VERIFIED → 记账」代码路径。
    不伪造 progress.json——VERIFIED 仍只由 progress.py 写入。
    """
    import argparse

    import build_output
    import progress

    real_gate, real_targets = build_output.run_chapter_gate, build_output.resolve_targets
    build_output.run_chapter_gate = lambda *a, **k: None
    build_output.resolve_targets = lambda *a, **k: ({}, "test-stub")
    try:
        rc = progress.cmd_gate(argparse.Namespace(state_dir=str(ws), chapters=",".join(chapters) if chapters else None, targets=None))
    finally:
        build_output.run_chapter_gate, build_output.resolve_targets = real_gate, real_targets
    assert rc == 0, "gate 替身应全 PASS（rc=0；failed>0 说明状态机前置不对）"


@pytest.fixture()
def ws(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    run("init", "--stage", STAGE, "--state-dir", state, "--data-dir", tmp_path / "data")
    return state


class TestInitAndNext:
    def test_init_all_pending(self, ws):
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        assert list(doc["chapters"]) == [f"ch{i}" for i in range(1, 11)]  # 插入序=数值序（save 不 sort_keys）
        assert all(s["status"] == "PENDING" for s in doc["chapters"].values())
        assert doc["phase"] == "WAVE1" and doc["total_dispatches"] == 0

    def test_double_init_refused(self, ws):
        r = run("init", "--stage", STAGE, "--state-dir", ws, expect=(1,))
        assert "已存在" in r.stderr

    def test_next_without_init_fails(self, tmp_path):
        r = run("next", "--state-dir", tmp_path / "nope", expect=(1,))
        assert "不存在" in r.stderr

    def test_next_dispatches_pending(self, ws):
        out = run("next", "--state-dir", ws).stdout
        assert "PHASE: WAVE1" in out and "[NEXT] 派发: ch1" in out and "≤3" in out

    def test_drafted_gating_priority_over_pending(self, ws):
        run("mark", "ch1", "DRAFTED", "--state-dir", ws)
        run("mark", "ch2", "DRAFTED", "--state-dir", ws)
        gate_pass(ws, chapters=["ch1"])
        out = run("next", "--state-dir", ws).stdout  # ch2 已起草 → 先跑门，不派 ch3
        assert "批量跑门: ch2" in out  # bug-3049 后门命令=批量 gate 渲染（无逐章 --chapter 旗标）
        assert "派发: ch3" not in out

    def test_gate_command_rendered_with_paths(self, ws):
        run("mark", "ch3", "DRAFTED", "--state-dir", ws)
        out = run("next", "--state-dir", ws).stdout
        # 断点续跑新会话可复制执行：命令渲染绝对 progress.py 路径 + state 路径（bug-3049 后=批量 gate）；
        # stage/data 路径由 init 记账进 progress.json，gate 真跑时从账本读。
        assert "批量跑门: ch3" in out
        assert str(SCRIPTS / "progress.py") in out and f"gate --state-dir {ws}" in out
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        assert Path(doc["stage_path"]) == STAGE and doc["data_dir"] and Path(doc["data_dir"]).is_absolute()

    def test_blocked_chapter_does_not_stall_wave1(self, ws):
        run("mark", "ch3", "BLOCKED", "--state-dir", ws, "--detail", "深度缺口 2400 eff")
        out = run("next", "--state-dir", ws).stdout
        assert "[NEXT] 派发: ch1" in out  # 单章 BLOCKED 不拖停全书（先写完能写的）

    def test_budget_exhaustion_routes_to_block(self, ws):
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        doc["total_dispatches"] = 16  # 测试直改（夹具特权；agent 面前唯一写者是 progress.py）
        (ws / "progress.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        out = run("next", "--state-dir", ws).stdout
        assert "额度耗尽" in out and "BLOCKED" in out

    def test_wave1_closed_with_unapproved_blocked_negotiates(self, ws):
        for i in range(1, 10):
            if i == 3:
                continue
            run("mark", f"ch{i}", "DRAFTED", "--state-dir", ws)
        gate_pass(ws)  # ch1..ch9（除 ch3）批量门 PASS 自动转 VERIFIED
        run("mark", "ch3", "BLOCKED", "--state-dir", ws, "--gate", "FAIL", "--detail", "eff 800 < 目标 2894")
        out = run("next", "--state-dir", ws).stdout
        assert "PHASE: NEGOTIATE" in out and "ch3" in out and "approve-downgrade" in out and "差距表" in out

    def test_key_points_then_wave2_then_clean_final(self, ws):
        for i in range(1, 10):
            run("mark", f"ch{i}", "DRAFTED", "--state-dir", ws)
        gate_pass(ws)
        out = run("next", "--state-dir", ws).stdout
        assert "PHASE: KEY_POINTS" in out and "key_points.json" in out
        (ws / "key_points.json").write_text(json.dumps({"chapters": {"ch1": ["要点"]}, "highlights": {}, "issues": []}, ensure_ascii=False), encoding="utf-8")
        run("confirm-key-points", "--state-dir", ws)
        out = run("next", "--state-dir", ws).stdout
        assert "PHASE: WAVE2" in out and "ch10" in out and "要点包" in out
        run("mark", "ch10", "DRAFTED", "--state-dir", ws)
        out = run("next", "--state-dir", ws).stdout
        assert "跑门: ch10" in out
        gate_pass(ws, chapters=["ch10"])
        out = run("next", "--state-dir", ws).stdout
        assert "PHASE: FINAL" in out and "--allow-partial" not in out  # 全 VERIFIED → 干净终验

    def test_final_with_approval_uses_allow_partial(self, ws):
        for i in range(1, 10):
            if i == 3:
                continue
            run("mark", f"ch{i}", "DRAFTED", "--state-dir", ws)
        gate_pass(ws)
        run("mark", "ch3", "BLOCKED", "--state-dir", ws, "--gate", "FAIL", "--detail", "eff 1200 < 2894")
        run("approve-downgrade", "--state-dir", ws, "--chapters", "ch3", "--note", "用户批准 2026-08-28")
        run("confirm-key-points", "--state-dir", ws)
        run("mark", "ch10", "DRAFTED", "--state-dir", ws)
        gate_pass(ws, chapters=["ch10"])
        out = run("next", "--state-dir", ws).stdout
        assert "PHASE: FINAL" in out and "--allow-partial" in out and "ch3" in out


class TestMarkValidation:
    def test_manual_mark_verified_rejected(self, ws):
        """bug-3049：--gate PASS 是调用方自证非官方凭据——手动 mark VERIFIED 一律拒（锁拒绝文案与 rc）。"""
        r = run("mark", "ch1", "VERIFIED", "--state-dir", ws, "--gate", "PASS", expect=(1,))
        assert "已禁用" in r.stderr and "progress.py gate" in r.stderr  # 只信产物；转正唯一通道=gate

    def test_illegal_transition_refused(self, ws):
        run("mark", "ch1", "DRAFTED", "--state-dir", ws)
        gate_pass(ws, chapters=["ch1"])  # VERIFIED 经 gate 真跑流取得
        r = run("mark", "ch1", "BLOCKED", "--state-dir", ws, expect=(1,))
        assert "非法转移" in r.stderr  # VERIFIED 只能回 DRAFTED（修改回路），不能直跳 BLOCKED

    def test_redispatch_increments_counters(self, ws):
        run("mark", "ch1", "DRAFTED", "--state-dir", ws)
        run("mark", "ch1", "DRAFTED", "--state-dir", ws)  # 重派：DRAFTED→DRAFTED 合法
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        assert doc["chapters"]["ch1"]["dispatches"] == 2 and doc["total_dispatches"] == 2

    def test_pending_to_blocked_allowed_budget_exhaustion(self, ws):
        run("mark", "ch9", "BLOCKED", "--state-dir", ws, "--detail", "派发额度耗尽")
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        assert doc["chapters"]["ch9"]["status"] == "BLOCKED"

    def test_blocked_revival_via_drafted(self, ws):
        run("mark", "ch3", "BLOCKED", "--state-dir", ws, "--gate", "FAIL")
        run("mark", "ch3", "DRAFTED", "--state-dir", ws)  # 补数据/批准后复活重写
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        assert doc["chapters"]["ch3"]["status"] == "DRAFTED"

    def test_unknown_chapter_refused(self, ws):
        r = run("mark", "ch99", "DRAFTED", "--state-dir", ws, expect=(1,))
        assert "未知章节" in r.stderr


class TestApproveDowngrade:
    def test_approval_recorded_with_note_and_timestamp(self, ws):
        run("approve-downgrade", "--state-dir", ws, "--chapters", "ch3,ch8", "--note", "对话确认 2026-08-28")
        doc = json.loads((ws / "progress.json").read_text(encoding="utf-8"))
        a = doc["downgrade_approvals"][-1]
        assert a["chapters"] == ["ch3", "ch8"] and a["note"] == "对话确认 2026-08-28"
        assert a["approved_at"]  # ISO 时间戳在场

    def test_unknown_chapter_refused(self, ws):
        r = run("approve-downgrade", "--state-dir", ws, "--chapters", "ch88", "--note", "x", expect=(1,))
        assert "未知章节" in r.stderr


class TestSnapshotCoverage:
    """spec §5.7：progress.json / key_points.json 落 state/ → snapshot rglob 自动纳哈希（零改码，锁定行为）。"""

    def test_state_files_hashed(self, tmp_path):
        import snapshot

        state = tmp_path / "state"
        state.mkdir()
        (state / "progress.json").write_text("{}", encoding="utf-8")
        (state / "key_points.json").write_text("{}", encoding="utf-8")
        m = snapshot.hash_manifest(tmp_path / "data", state)
        assert "state/progress.json" in m and "state/key_points.json" in m
