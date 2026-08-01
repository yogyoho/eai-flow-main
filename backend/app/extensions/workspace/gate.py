"""Collab Workspace — 闸门原语。

EAI-CUSTOM: 复用 review/gate.py::evaluate_gate（纯函数）；本模块包装：
- agent 参与者语义（agent 完成任务自动批准；quorum = 人类参与者数）
- deadline 惰性执行（GET gates / POST judge / 桥触发时检查）
- 零人类参与者防退化（不自动通过）
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.review.gate import GateMode, GateResult, evaluate_gate

from .models import CollabGate


def _now() -> datetime:
    # EAI-CUSTOM: DB 列是 TIMESTAMP WITHOUT TIME ZONE，须返回 naive UTC
    return datetime.now(timezone.utc).replace(tzinfo=None)


def resolve_judgments(gate: CollabGate, human_judgments: list[dict]) -> list[dict]:
    """合并 agent 自动批准 + 人类判定。

    - agent 参与者：任务完成时视为 approved（由桥在触发时写入 audit + 这里作为已判）。
    - human 参与者：从 human_judgments（judge 端点提交）取。
    """
    judgments: list[dict] = []
    humans: list[str] = []
    for p in (gate.participants or []):
        key = str(p.get("user_id") or p.get("agent_name") or "")
        if p.get("type") == "agent":
            # agent 已完成任务 = 自动批准（由桥写入 resolved/audit 标记）
            judgments.append({"reviewer_id": key, "status": "approved", "auto": True})
        else:
            humans.append(key)
    for j in human_judgments:
        judgments.append({"reviewer_id": str(j.get("reviewer_id")), "status": j.get("status", "approved")})
    return judgments, humans


async def apply_deadline(gate: CollabGate) -> CollabGate:
    """惰性检查 deadline_at + escalation_rule。修改 gate 状态但不 flush。"""
    now = _now()
    if gate.state != "pending" or not gate.deadline_at:
        return gate
    if now < gate.deadline_at:
        return gate
    rule = gate.escalation_rule or {}
    action = rule.get("action", "auto_approve")
    if action == "auto_approve":
        gate.state = "approved"
        gate.resolved_at = now
        gate.audit = list(gate.audit or []) + [{"at": now.isoformat(), "by": "system", "action": "deadline_auto_approve"}]
    elif action == "escalate_admin":
        # 提升给 owner：state 保持 pending，但记 escalate 标记（前端展示）
        gate.audit = list(gate.audit or []) + [{"at": now.isoformat(), "by": "system", "action": "deadline_escalate_admin"}]
    return gate


def evaluate(
    gate: CollabGate,
    human_judgments: list[dict],
    weights: dict[str, float] | None = None,
) -> GateResult:
    """评估闸门。agent 参与者自动批准；quorum = 人类参与者数。零人类防退化。"""
    judgments, humans = resolve_judgments(gate, human_judgments)

    # 零人类参与者：不自动通过（escalate 或保持 pending）
    if not humans:
        return GateResult.WAITING

    total_humans = len(humans)
    mode = GateMode(gate.mode) if gate.mode in [m.value for m in GateMode] else GateMode.ALL_MUST_APPROVE
    return evaluate_gate(mode, total_humans, judgments, weights)
