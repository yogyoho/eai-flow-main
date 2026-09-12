"""e2e_bid_driver 纯逻辑单测(无网络): bug-3037 门轮空转停滞判定 stall_step。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "e2e" / "bid"))
import e2e_bid_driver as drv  # noqa: E402


def step(count=0, escalated=False, seen=None, tools=(), prev_tools=(), last_ai=""):
    return drv.stall_step(count, escalated, seen or set(), list(tools), list(prev_tools), last_ai)


class TestStallStep:
    def test_fresh_chain_new_tools_resets(self):
        # 链首种子(门轮自身工具∪上轮)算新进展, 计数保持 0
        count, escalated, seen, action = step(tools=["read_file", "bash"], prev_tools=["bash"])
        assert (count, escalated, action) == (0, False, "answer")
        assert seen == {"read_file", "bash"}

    def test_no_new_tools_accumulates(self):
        count, _, seen, action = step(count=1, seen={"bash", "present_files"}, tools=[], prev_tools=["bash"])
        assert (count, action) == (2, "answer")
        assert seen == {"bash", "present_files"}

    def test_new_tool_mid_chain_resets(self):
        count, _, _, action = step(count=2, seen={"bash"}, tools=["bash", "read_file"], prev_tools=["bash"])
        assert (count, action) == (0, "answer")

    def test_stall_with_present_files_in_seen_still_escalates(self):
        # present_files 是中段门工件信号(确认门1/2 呈现清单/diff 表), 链内出现过≠终稿已交付
        # -> 不直判完成, 走升级(对抗评审 wgu46e22u blocker 回归锚)
        count, escalated, seen, action = step(count=2, escalated=False, seen={"bash", "present_files"}, tools=[], prev_tools=[])
        assert action == "escalate"
        assert (count, escalated) == (0, True)

    def test_stall_without_evidence_escalates_once(self):
        count, escalated, seen, action = step(count=2, escalated=False, seen={"bash"}, tools=[], prev_tools=[])
        assert action == "escalate"
        assert (count, escalated) == (0, True)

    def test_post_escalation_still_no_evidence_aborts(self):
        # 模型在等 driver 给不了的真实输入(反复澄清), 停机防烧
        count, escalated, seen, action = step(count=2, escalated=True, seen={"bash"}, tools=[], prev_tools=[])
        assert action == "abort"
        assert escalated is True

    def test_post_escalation_aborts_even_with_past_delivery(self):
        # 升级后仍无进展, 链内曾有 present_files 也不改判(完成判定归 COMPLETION_RECAP)
        count, escalated, seen, action = step(count=2, escalated=True, seen={"bash", "present_files"}, tools=[], prev_tools=[])
        assert action == "abort"
        assert escalated is True

    def test_escalation_answer_with_new_tools_recovers(self):
        # bug-3308 新契约: 终结指令后裸 present_files 复读(终文无交付标记)不算进展——
        # 停滞计数照常累计; 未达 STALL_N 仍回自动应答, 升级态保持(再空转则 abort)
        count, escalated, seen, action = step(count=0, escalated=True, seen={"bash"}, tools=["present_files", "bash"], prev_tools=[])
        assert (count, action) == (1, "answer")
        assert escalated is True
        assert "present_files" in seen

    def test_present_files_with_delivery_marker_is_progress(self):
        # 终文带交付标记(DELIVERY_MARKERS)的 present_files 收口 = 交付证据 = 进展, 计数保持 0
        count, _, seen, action = step(count=2, escalated=True, seen={"bash"}, tools=["present_files"], prev_tools=[], last_ai="投标文件六件套已交付")
        assert (count, action) == (0, "answer")
        assert "present_files" in seen

    def test_prev_tools_seeded_into_window(self):
        # 上轮工具并入窗口: 链内首次出现的工具名 = 新进展, 计数清零且入 seen
        count, _, seen, _ = step(count=1, seen={"bash"}, tools=[], prev_tools=["bash", "read_file"])
        assert (count, "read_file" in seen) == (0, True)

    def test_stall_n_boundary_answer_below_threshold(self):
        count, _, _, action = step(count=drv.STALL_N - 2, seen={"bash"}, tools=[], prev_tools=[])
        assert action == "answer"
