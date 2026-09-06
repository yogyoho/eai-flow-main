"""coal-eia-report v2 回放测试（T7 文件⑥）。

两块（geo 先例 test_geological_report_v2_replay.py 形制）：
  ① KF found=false 兜底声明契约（bug-2231/3066 三件套纪律）：声明文本必须以 SKILL.md
     文字在场——LLM 面无法离线自动化，文档契约是离线可验的最低保障。
  ② 多 run 断点续跑回放：progress.py 状态持久在磁盘（progress.json 唯一事实源），
     新 run（仅子进程 + 磁盘状态，零内存承接）`next` 即恢复现场——已 VERIFIED 节不重派
     （路由越过 VERIFIED 章）、半途 DRAFTED 章先收口、重 init 拒绝抹进度。

设计依据: docs/designs/coal-eia-report-v2.md D10（停车契约加严，磁盘续跑=默认生存方式）。
运行: cd backend && PYTHONPATH=. uv run pytest tests/test_coal_eia_report_v2_replay.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "public" / "coal-eia-report"
SCRIPTS = SKILL / "scripts"  # conftest 同名脚本隔离锚
SKILL_FILE = SKILL / "SKILL.md"
STAGE = SKILL / "references" / "stages" / "planning_eia.json"

SENT = "矿区总体规划与现行环境保护法律法规构成本节评价的依据与边界条件，评价时段与评价分区据此划定。"


def run(*args: object, expect=(0,)) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / str(args[0])), *map(str, args[1:])], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout[-400:]}\n{r.stderr[:400]}"
    return r


# ── ① KF found=false 兜底声明契约 ──────────────────────────────────────────────


class TestKfFallbackContract:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = SKILL_FILE.read_text(encoding="utf-8")

    def test_fallback_declaration_text_present(self):
        """found=false 时向用户声明的兜底话术必须逐字在场（复测 bug-2231 三件套纪律）。"""
        assert "知识工厂未命中模板" in self.content
        assert "references/` 兜底" in self.content or "references/ 兜底" in self.content

    def test_real_call_required_not_verbal(self):
        """三件套①：必须留下真实工具调用记录，口头声称 = 未做（bug-2231 实测踩坑两次）。"""
        assert "kf_resolve_template" in self.content
        assert "口头声称" in self.content and "未做" in self.content
        assert "工具不可用或调用失败视同" in self.content or "视同 `found=false`" in self.content

    def test_domain_keywords_retry(self):
        """bug-3066：missing_keywords 时按 suggestion 补 domain_keywords 重试 ≤1 次才兜底。"""
        assert "domain_keywords" in self.content and "重试" in self.content

    def test_data_expectation_visible_to_user(self):
        """三件套③：数据预告必须用户可见，载体 = 首张表单 question 文本开头。"""
        assert "data_expectations.json" in self.content and "数据预告" in self.content
        assert "只说不做" in self.content and "question" in self.content

    def test_openpit_post_stage_not_runnable(self):
        """stage 文件未立的场景管线不可跑（禁拿其他 stage 凑数）。"""
        assert "二期" in self.content and "管线不可跑" in self.content


# ── ② 多 run 断点续跑回放 ──────────────────────────────────────────────────────


@pytest.fixture()
def replay_ws(tmp_path):
    """Run1：freeze → ch1 全节派发 → 章门 PASS（11 节 VERIFIED）→ run 中断。"""
    root = tmp_path / "ws"
    data, state = root / "data", root / "state"
    data.mkdir(parents=True)
    state.mkdir(parents=True)
    run("progress.py", "init", "--stage", STAGE, "--state-dir", state, "--data-dir", data)
    run("progress.py", "run-stage", "freeze", "--state-dir", state, expect=(0, 3))
    stage = json.loads(STAGE.read_text(encoding="utf-8"))
    sids = [s["id"] for s in stage["chapters"]["ch1"]["sections"]]
    run("progress.py", "mark", "--sections", ",".join(sids), "DRAFTED", "--state-dir", state)
    depth = root / "depth_ch1.json"
    depth.write_text(json.dumps({"chapters": {"ch1": {"floor_chars": 800}}}, ensure_ascii=False), encoding="utf-8")
    for i, s in enumerate(stage["chapters"]["ch1"]["sections"], 1):
        (state / "sections").mkdir(exist_ok=True)
        (state / "sections" / f"{s['id']}.md").write_text(f"### 1.{i} {s['title']}\n\n" + SENT * 4 + "\n", encoding="utf-8")
    run("progress.py", "mark", "ch1", "DRAFTED", "--state-dir", state)
    r = run("progress.py", "gate", "--state-dir", state, "--targets", depth)
    assert "GATE_BATCH_DONE: passed=1 failed=0" in r.stdout
    doc = json.loads((state / "progress.json").read_text(encoding="utf-8"))
    assert doc["chapters"]["ch1"]["status"] == "VERIFIED"
    assert sum(1 for s in doc["chapters"]["ch1"]["sections"] if s["status"] == "VERIFIED") == 11
    return SimpleNamespace(root=root, data=data, state=state, depth=depth)


class TestMultiRunResume:
    def test_reinit_refused_progress_immortal(self, replay_ws):
        """新 run 误重 init → 拒绝（progress 无损——磁盘续跑不靠对话记忆）。"""
        r = run("progress.py", "init", "--stage", STAGE, "--state-dir", replay_ws.state, "--data-dir", replay_ws.data, expect=(1,))
        assert "已存在" in r.stderr
        doc = json.loads((replay_ws.state / "progress.json").read_text(encoding="utf-8"))
        assert doc["chapters"]["ch1"]["status"] == "VERIFIED"  # 旧进度原封不动

    def test_next_skips_verified_no_redispatch(self, replay_ws):
        """Run2 首动作 `next` 恢复现场：已 VERIFIED 节不重派——路由指向下一 PENDING 章。"""
        doc_before = json.loads((replay_ws.state / "progress.json").read_text(encoding="utf-8"))
        r = run("progress.py", "next", "--state-dir", replay_ws.state)
        assert "PHASE: WAVE1" in r.stdout
        assert "派发: ch2" in r.stdout  # ch1 已收口，路由越过 VERIFIED 章
        assert "ch1" not in [ln for ln in r.stdout.splitlines() if "[NEXT]" in ln][0]
        # 纯路由不改记账（next 是只读决策）
        doc_after = json.loads((replay_ws.state / "progress.json").read_text(encoding="utf-8"))
        assert doc_after["total_dispatches"] == doc_before["total_dispatches"]

    def test_status_counters_survive_restart(self, replay_ws):
        r = run("progress.py", "status", "--state-dir", replay_ws.state)
        assert "节 VERIFIED 11/77" in r.stdout  # 节子表计数跨 run 持久

    def test_gate_without_drafted_refused(self, replay_ws):
        """无 DRAFTED 章 → gate 拒跑（已 VERIFIED 章不被重门重派）。"""
        r = run("progress.py", "gate", "--state-dir", replay_ws.state, expect=(1,))
        assert "没有 DRAFTED 章" in r.stderr

    def test_mid_wave_resume_gate_first(self, replay_ws):
        """Run2 半途接续：新派发 ch2 部分节后中断，`next` 先指引收口 DRAFTED 章再开新波。"""
        state = replay_ws.state
        run("progress.py", "mark", "--sections", "ch2_S01,ch2_S02,ch2_S03", "DRAFTED", "--state-dir", state)
        run("progress.py", "mark", "ch2", "DRAFTED", "--state-dir", state)
        r = run("progress.py", "next", "--state-dir", state)
        assert "批量跑门" in r.stdout and "ch2" in r.stdout  # drafted-first 路由
        # VERIFIED 节的 dispatches 不因续跑变化（不重派的账面不变式）
        doc = json.loads((state / "progress.json").read_text(encoding="utf-8"))
        assert all(s["dispatches"] == 1 for s in doc["chapters"]["ch1"]["sections"])
