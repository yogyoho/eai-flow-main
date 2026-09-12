"""e2e_bid_driver 纯逻辑单测(无网络): bug-3037 门轮空转停滞判定 stall_step +
bug-3313 确认门应答 pick_answer(门签名门控/表单字段回填/专行优先)。"""

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


class TestPickAnswer:
    def test_form_fields_get_concrete_first_option_answers(self):
        # bug-3313: clean5 turn1 实录门(3 required 字段, 无 ANSWERS 专行命中)——
        # 逐项回填第一选项替代泛化兜底("确认, 请继续。"导致 agent 自行其是:
        # 无人选"仅Markdown", 绕开 build_output 册集管线手拼 14 个 docx)
        q = (
            "🔀 阶段1提取已完成，需确认后续工作方向\n\n"
            "确认门1清单已生成，下一步如何处理？\n\n"
            "  1. 确认/补充条款 (required)\n"
            "  2. 输出格式 (required) — options: 仅Markdown（快速验证） / Markdown + Word转换（最终交付）\n"
            "  3. 技术卷处理 (required) — options: 占位页+章节大纲（最低评标价法，无主观项） / 仍需编制技术响应正文\n\n"
            "Please reply with a value for each field."
        )
        ans = drv.pick_answer(q)
        assert ans.startswith("逐项确认如下: ")
        assert "确认/补充条款=全部确认" in ans  # required 无选项 = 确认型 checkbox
        assert "输出格式=仅Markdown（快速验证）" in ans
        assert "技术卷处理=占位页+章节大纲（最低评标价法，无主观项）" in ans
        assert ans.endswith("; 请按此继续。")
        assert ans != drv.ANSWERS[-1][1]

    def test_form_unparseable_falls_back_to_default(self):
        # 带门签名但无可解析字段行(散文提及 (required) 不算) -> 原兜底行
        q = "确认门1清单已生成，请对以下各项 (required) 给出答复。"
        assert drv.pick_answer(q) == drv.ANSWERS[-1][1]

    def test_special_row_beats_form_filling(self):
        # 专行(补遗)命中优先于表单回填——表单只填无专行命中的空档(bug-3313)
        q = "确认门2: 补遗合并确认\n\n  1. 补遗diff表 (required) — options: 确认合并 / 逐项复核\n"
        assert drv.pick_answer(q) == drv.ANSWERS[1][1]
