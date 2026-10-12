"""Translation extension S1 unit tests (pure state machine / defaults, no DB)."""

from app.extensions.translation.models import (
    STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    TranslationTask,
    validate_transition,
)


class TestStateMachine:
    def test_all_states_have_transition_entries(self):
        assert set(TRANSITIONS.keys()) == set(STATES)

    def test_happy_path_chain(self):
        for cur, nxt in [
            ("pending", "running"),
            ("running", "check_failed"),
            ("check_failed", "retrying"),
            ("retrying", "indexed"),
            ("indexed", "delivered"),
        ]:
            assert validate_transition(cur, nxt), f"{cur}->{nxt} must be legal"

    def test_retry_then_exceeded_then_review_edges(self):
        assert validate_transition("retrying", "exceeded")
        assert validate_transition("exceeded", "indexed")  # review_approved
        assert validate_transition("exceeded", "archived")  # review_rejected（仅未 delivered）

    def test_infra_failure_and_manual_rerun(self):
        assert validate_transition("running", "failed")
        assert validate_transition("indexed", "failed")  # 交付阶段基础设施失败（R7/A-1）
        assert validate_transition("failed", "pending")  # 人工重跑

    def test_delivered_not_manually_reachable(self):
        assert not validate_transition("exceeded", "delivered")
        assert not validate_transition("pending", "delivered")

    def test_r3_2_rejected_scoped_to_exceeded(self):
        # review_rejected 只存在于 exceeded 队列；delivered 后走重传即替换版本流
        assert validate_transition("exceeded", "archived")
        assert not validate_transition("delivered", "archived")

    def test_r3_1_supersede_paths(self):
        # 重传即替换：pending/retrying/cancelled 类取消路径在案
        assert validate_transition("pending", "superseded")
        assert validate_transition("retrying", "superseded")

    def test_terminal_states_have_no_outgoing(self):
        for st in TERMINAL_STATES:
            assert TRANSITIONS[st] == frozenset(), f"{st} must be terminal"

    def test_delivered_keeps_reviewed_redelivery_edge(self):
        # reviewed 档替换流: delivered → indexed（重走索引交付），故 delivered 不在终态集
        assert validate_transition("delivered", "indexed")
        assert "delivered" not in TERMINAL_STATES

    def test_unknown_states_rejected(self):
        assert not validate_transition("pending", "bogus")
        assert not validate_transition("bogus", "pending")

    def test_stored_state_edges(self):
        # 资产库：上传=stored（不入队）；「翻译」动作=stored→pending
        assert validate_transition("stored", "pending")
        assert validate_transition("stored", "cancelled")
        assert not validate_transition("stored", "running")  # 未入队不能被 worker 领取
        assert not validate_transition("pending", "stored")

    def test_new_task_schema_defaults(self):
        # 列级 default 契约（INSERT 时生效），断言 schema 而非构造期属性
        cols = TranslationTask.__table__.c
        assert cols.state.default.arg == "pending"
        assert cols.quality_tier.default.arg == "draft"
        assert cols.retry_count.default.arg == 0
        assert cols.task_version.default.arg == 1
