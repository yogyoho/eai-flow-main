"""Tests for Collab Workspace — tier signals, gate evaluation, schemas, headings.

EAI-CUSTOM: 全新模块。纯单元测试（不依赖 DB），覆盖 tier 派生、闸门 evaluate（agent 参与者）、
promote-to-report 标题提取、schema 校验。
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.extensions.workspace.gate import evaluate, resolve_judgments
from app.extensions.workspace.models import CollabGate
from app.extensions.workspace.schemas import (
    CollabMemberCreate,
    CollabProjectCreate,
    CollabSectionCreate,
    CollabTaskCreate,
)
from app.extensions.workspace.tier import _count_headings

# ── Tier: heading counting (S4 quickdoc signal) ──


class TestCountHeadings:
    def test_counts_h2_only(self):
        md = "## 第一章\n正文\n### 小节\n## 第二章\n"
        assert _count_headings(md) == 2

    def test_zero_when_none(self):
        assert _count_headings("") == 0
        assert _count_headings("# 只有一级标题\n") == 0

    def test_ignores_code_blocks_naive(self):
        # 简化：只按行首 ## 计（与实现一致）
        md = "```\n## 伪标题\n```\n## 真标题\n"
        assert _count_headings(md) == 2


# ── Gate: agent participant semantics ──


def _gate(mode: str = "all_must_approve", participants=None) -> CollabGate:
    return CollabGate(
        id=uuid4(),
        project_id=uuid4(),
        scope="task",
        state="pending",
        mode=mode,
        participants=participants or [],
        audit=[],
    )


class TestGateEvaluate:
    def test_agent_auto_approve_human_approves(self):
        """agent 参与者自动批准；人类 approve 即 PASS。"""
        gate = _gate(
            participants=[
                {"type": "agent", "agent_name": "writer-a", "weight": 1.0},
                {"type": "human", "user_id": str(uuid4()), "weight": 1.0},
            ]
        )
        human_judgments = [{"reviewer_id": gate.participants[1]["user_id"], "status": "approved"}]
        from app.extensions.review.gate import GateResult

        assert evaluate(gate, human_judgments) == GateResult.PASS

    def test_zero_human_participants_waits(self):
        """零人类参与者不自动通过（防退化）。"""
        gate = _gate(
            participants=[
                {"type": "agent", "agent_name": "writer-a", "weight": 1.0},
            ]
        )
        from app.extensions.review.gate import GateResult

        assert evaluate(gate, []) == GateResult.WAITING

    def test_human_reject_fails(self):
        gate = _gate(
            participants=[
                {"type": "human", "user_id": str(uuid4()), "weight": 1.0},
            ]
        )
        human_judgments = [{"reviewer_id": gate.participants[0]["user_id"], "status": "rejected"}]
        from app.extensions.review.gate import GateResult

        assert evaluate(gate, human_judgments) == GateResult.REJECT

    def test_any_can_approve(self):
        gate = _gate(
            mode="any_can_approve",
            participants=[
                {"type": "human", "user_id": str(uuid4()), "weight": 1.0},
            ],
        )
        human_judgments = [{"reviewer_id": gate.participants[0]["user_id"], "status": "approved"}]
        from app.extensions.review.gate import GateResult

        assert evaluate(gate, human_judgments) == GateResult.PASS


class TestResolveJudgments:
    def test_agent_auto_approved(self):
        gate = _gate(
            participants=[
                {"type": "agent", "agent_name": "w", "weight": 1.0},
                {"type": "human", "user_id": str(uuid4()), "weight": 1.0},
            ]
        )
        judgments, humans = resolve_judgments(gate, [])
        assert len(judgments) == 1  # agent 自动批准
        assert judgments[0]["status"] == "approved"
        assert len(humans) == 1


# ── Schemas ──


class TestSchemas:
    def test_project_create_quickdoc(self):
        p = CollabProjectCreate(name="测试项目", kind="quickdoc")
        assert p.kind == "quickdoc"

    def test_project_create_invalid_kind(self):
        with pytest.raises(ValidationError):
            CollabProjectCreate(name="x", kind="bogus")

    def test_member_create_human(self):
        uid = uuid4()
        m = CollabMemberCreate(member_type="human", user_id=uid, role="reviewer")
        assert m.user_id == uid

    def test_task_create_defaults(self):
        t = CollabTaskCreate(title="写第一章", kind="section_write")
        assert t.kind == "section_write"
        assert t.context is None

    def test_section_create(self):
        s = CollabSectionCreate(title="第一章")
        assert s.word_count_target == 3000
