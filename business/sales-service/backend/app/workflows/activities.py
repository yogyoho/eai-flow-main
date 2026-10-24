"""Idempotent Temporal activities that project workflow progress into the DB."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.database import get_session_maker
from app.domain import add_audit, create_todo, utc_now
from app.models import (
    ApprovalAction,
    ApprovalRequest,
    Notification,
    Opportunity,
    Todo,
)
from app.workflows.contracts import ApprovalWorkflowInput, DecisionSignal

logger = logging.getLogger(__name__)


def _sid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


async def _load_request(db, request_id: str) -> ApprovalRequest | None:
    """Load an approval with its steps eagerly.

    Activities run outside the request's greenlet context; touching a lazy
    ``request.steps`` relationship there raises MissingGreenlet. Every activity
    that reads or mutates steps must go through this loader.
    """
    return (await db.execute(select(ApprovalRequest).where(ApprovalRequest.id == _sid(request_id)).options(selectinload(ApprovalRequest.steps)))).scalar_one_or_none()


async def _close_approval_todos(db, request_id: uuid.UUID, note: str) -> None:
    rows = list(
        (
            await db.execute(
                select(Todo).where(
                    Todo.object_type == "approval",
                    Todo.object_id == request_id,
                    Todo.status.in_(["open", "in_progress"]),
                )
            )
        ).scalars()
    )
    for todo in rows:
        todo.status = "resolved"
        todo.resolution = note
        todo.resolved_at = utc_now()
    await db.flush()


async def _notify(db, user_id: str | None, title: str, body: str, link: str, dedupe: str) -> None:
    if not user_id:
        return
    existing = (await db.execute(select(Notification).where(Notification.dedupe_key == dedupe))).scalar_one_or_none()
    if existing:
        return
    db.add(Notification(user_id=user_id, type="approval", title=title, body=body, link=link, dedupe_key=dedupe))


@activity.defn(name="mark_running")
async def mark_running(payload: ApprovalWorkflowInput, workflow_id: str, run_id: str) -> None:
    async with get_session_maker()() as db:
        request = await _load_request(db, payload.request_id)
        if request is None:
            return
        if request.status in {"approved", "rejected", "returned", "cancelled", "expired"}:
            return
        if request.status in {"pending_start", "failed"}:
            request.status = "running"
            request.started_at = utc_now()
        request.workflow_id = workflow_id
        request.workflow_run_id = run_id
        request.failure_reason = None
        await db.commit()


@activity.defn(name="activate_step")
async def activate_step(request_id: str, step_no: int) -> None:
    async with get_session_maker()() as db:
        request = await _load_request(db, request_id)
        if request is None:
            return
        step = next((s for s in request.steps if s.step_no == step_no), None)
        if step is None:
            return
        # Activation is a one-way transition. An activity retry after the
        # transaction committed must not recreate a todo for an already active
        # (or terminal) step.
        if step.status != "pending":
            return
        step.status = "active"
        if step.sla_due_at is None:
            step.sla_due_at = utc_now() + timedelta(hours=24)
        request.current_step = step_no
        due_at = step.sla_due_at
        if due_at is not None and due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=UTC)
        opportunity = await db.get(Opportunity, request.opportunity_id)
        await create_todo(
            db,
            type="approval",
            severity="high",
            title=f"审批：{request.gate_code} · {opportunity.opportunity_no if opportunity else request.request_no}",
            description=f"{request.reason or '请在审批中心处理'}（第 {step_no} 步：{step.approver_role}）",
            object_type="approval",
            object_id=request.id,
            dedupe_key=f"approval:{request.id}:step:{step_no}",
            assignee_role=step.approver_role,
            assignee_id=step.approver_id,
            created_by="temporal",
            due_hours=max(1, int((due_at - utc_now()).total_seconds() // 3600) if due_at else 24),
        )
        await _notify(
            db,
            request.requested_by,
            f"审批已流转：{request.request_no}",
            f"{request.gate_code} 审批进入第 {step_no} 步（{step.approver_role}）",
            f"/sales/approvals?focus={request.id}",
            f"approval-active:{request.id}:{step_no}",
        )
        await db.commit()


@activity.defn(name="escalate_step")
async def escalate_step(request_id: str, step_no: int, reason: str, expected_level: int = 1) -> None:
    async with get_session_maker()() as db:
        request = await _load_request(db, request_id)
        if request is None:
            return
        step = next((s for s in request.steps if s.step_no == step_no), None)
        if step is None or step.status != "active":
            return
        # The activity may be retried after its transaction committed. The
        # workflow passes the level it expects, so an old retry is a no-op.
        if step.escalation_level >= expected_level:
            return
        await _close_approval_todos(db, request.id, "审批超时升级，原待办已关闭")
        step.escalation_level = expected_level
        step.escalated_at = utc_now()
        if step.approver_role == "regional_manager":
            step.approver_role = "sales_director"
        # An escalated step belongs to the new role, not to the previous
        # delegate. Without this the old assignee could still act.
        step.approver_id = None
        step.decision = None
        step.sla_due_at = utc_now() + timedelta(hours=4)
        opportunity = await db.get(Opportunity, request.opportunity_id)
        await create_todo(
            db,
            type="approval",
            severity="blocker",
            title=f"审批超时升级：{request.gate_code} · {opportunity.opportunity_no if opportunity else request.request_no}",
            description=reason,
            object_type="approval",
            object_id=request.id,
            dedupe_key=f"approval:{request.id}:step:{step_no}:esc:{step.escalation_level}",
            assignee_role=step.approver_role,
            created_by="temporal",
            due_hours=4,
        )
        add_audit(
            db,
            actor_id="temporal",
            actor_type="system",
            action="approval.escalate",
            object_type="approval_request",
            object_id=str(request.id),
            after={"step_no": step_no, "level": step.escalation_level, "role": step.approver_role},
        )
        await _notify(
            db,
            request.requested_by,
            f"审批超时升级：{request.request_no}",
            reason,
            f"/sales/approvals?focus={request.id}",
            f"approval-escalate:{request.id}:{step_no}:{step.escalation_level}",
        )
        await db.commit()


@activity.defn(name="record_decision")
async def record_decision(request_id: str, decision: DecisionSignal) -> str:
    async with get_session_maker()() as db:
        existing = (await db.execute(select(ApprovalAction).where(ApprovalAction.idempotency_key == decision.idempotency_key))).scalar_one_or_none()
        if existing:
            if existing.request_id == _sid(request_id) and existing.step_no == decision.step_no and existing.action == decision.action and existing.actor_id == decision.actor_id:
                return "duplicate"
            raise ApplicationError("审批幂等键冲突", non_retryable=True)
        request = await _load_request(db, request_id)
        if request is None:
            return "missing"
        if request.status != "running":
            return "not-running"
        step = next((s for s in request.steps if s.step_no == decision.step_no), None)
        if step is None:
            return "missing-step"
        if step.status != "active":
            return "not-active"
        status_by_action = {"approve": "approved", "reject": "rejected", "return": "returned"}
        step.status = status_by_action.get(decision.action, "approved")
        step.decision = decision.action
        step.comment = decision.comment
        step.decided_at = utc_now()
        step.idempotency_key = decision.idempotency_key
        db.add(
            ApprovalAction(
                request_id=request.id,
                step_no=decision.step_no,
                action=decision.action,
                actor_id=decision.actor_id,
                actor_role=decision.actor_role,
                comment=decision.comment,
                idempotency_key=decision.idempotency_key,
            )
        )
        await _close_approval_todos(db, request.id, f"审批已{ {'approve': '通过', 'reject': '驳回', 'return': '退回'}.get(decision.action, decision.action) }")
        add_audit(
            db,
            actor_id=decision.actor_id,
            action=f"approval.{decision.action}",
            object_type="approval_request",
            object_id=str(request.id),
            after={"step_no": decision.step_no, "comment": decision.comment},
        )
        await db.commit()
        return "recorded"


@activity.defn(name="delegate_step")
async def delegate_step(request_id: str, decision: DecisionSignal) -> str:
    async with get_session_maker()() as db:
        existing = (await db.execute(select(ApprovalAction).where(ApprovalAction.idempotency_key == decision.idempotency_key))).scalar_one_or_none()
        if existing:
            if existing.request_id == _sid(request_id) and existing.step_no == decision.step_no and existing.action == "delegate" and existing.actor_id == decision.actor_id:
                return "duplicate"
            raise ApplicationError("审批幂等键冲突", non_retryable=True)
        request = await _load_request(db, request_id)
        if request is None:
            return "missing"
        if request.status != "running":
            return "not-running"
        step = next((s for s in request.steps if s.step_no == decision.step_no), None)
        if step is None or step.status != "active":
            return "not-active"
        if not decision.delegate_to:
            return "missing-target"
        step.approver_id = decision.delegate_to
        step.status = "active"
        step.decision = "delegate"
        step.comment = decision.comment
        step.sla_due_at = utc_now() + timedelta(hours=24)
        db.add(
            ApprovalAction(
                request_id=request.id,
                step_no=decision.step_no,
                action="delegate",
                actor_id=decision.actor_id,
                actor_role=decision.actor_role,
                comment=decision.comment,
                idempotency_key=decision.idempotency_key,
            )
        )
        await _close_approval_todos(db, request.id, "审批已转办")
        opportunity = await db.get(Opportunity, request.opportunity_id)
        await create_todo(
            db,
            type="approval",
            severity="high",
            title=f"转办审批：{request.gate_code} · {opportunity.opportunity_no if opportunity else request.request_no}",
            description=f"{decision.actor_id} 将第 {decision.step_no} 步转办给你。",
            object_type="approval",
            object_id=request.id,
            dedupe_key=f"approval:{request.id}:step:{decision.step_no}:delegate:{decision.idempotency_key}",
            assignee_id=decision.delegate_to,
            created_by=decision.actor_id,
            due_hours=24,
        )
        add_audit(
            db,
            actor_id=decision.actor_id,
            action="approval.delegate",
            object_type="approval_request",
            object_id=str(request.id),
            after={"step_no": decision.step_no, "delegate_to": decision.delegate_to},
        )
        await _notify(
            db,
            decision.delegate_to,
            f"审批转办：{request.request_no}",
            f"{decision.actor_id} 将第 {decision.step_no} 步审批转办给你",
            f"/sales/approvals?focus={request.id}",
            f"approval-delegate:{request.id}:{decision.step_no}:{decision.idempotency_key}",
        )
        await db.commit()
        return "delegated"


@activity.defn(name="finalize_request")
async def finalize_request(request_id: str, status: str, reason: str | None = None) -> None:
    if status not in {"approved", "rejected", "returned", "cancelled", "expired"}:
        return
    async with get_session_maker()() as db:
        request = await _load_request(db, request_id)
        if request is None:
            return
        if request.status in {"approved", "rejected", "returned", "cancelled", "expired", "failed"}:
            return
        request.status = status
        request.completed_at = utc_now()
        request.failure_reason = reason
        if status in {"rejected", "returned", "cancelled", "expired"}:
            for step in request.steps:
                if step.status == "active":
                    step.status = status
                    step.decided_at = utc_now()
                elif step.status == "pending":
                    # A terminal decision ends the flow; future steps must not
                    # keep advertising a live SLA in the UI.
                    step.status = "skipped"
        await _close_approval_todos(db, request.id, f"审批结束：{status}")
        labels = {"approved": "通过", "rejected": "驳回", "returned": "退回", "cancelled": "取消", "expired": "过期"}
        add_audit(
            db,
            actor_id="temporal",
            actor_type="system",
            action=f"approval.{status}",
            object_type="approval_request",
            object_id=str(request.id),
            after={"reason": reason},
        )
        await _notify(
            db,
            request.requested_by,
            f"审批{labels.get(status, status)}：{request.request_no}",
            reason or f"{request.gate_code} 审批已{labels.get(status, status)}",
            f"/sales/approvals?focus={request.id}",
            f"approval-final:{request.id}:{status}",
        )
        await db.commit()


@activity.defn(name="mark_failed")
async def mark_failed(request_id: str, error: str) -> None:
    async with get_session_maker()() as db:
        request = await _load_request(db, request_id)
        if request is None:
            return
        if request.status in {"approved", "rejected", "returned", "cancelled", "expired", "failed"}:
            return
        request.status = "failed"
        request.completed_at = utc_now()
        request.failure_reason = error[:2000]
        for step in request.steps:
            if step.status == "active":
                step.status = "cancelled"
                step.decided_at = utc_now()
            elif step.status == "pending":
                step.status = "skipped"
        await _close_approval_todos(db, request.id, "审批执行失败")
        add_audit(
            db,
            actor_id="temporal",
            actor_type="system",
            action="approval.failed",
            object_type="approval_request",
            object_id=str(request.id),
            after={"error": error[:1000]},
        )
        await _notify(
            db,
            request.requested_by,
            f"审批执行失败：{request.request_no}",
            error[:500],
            f"/sales/approvals?focus={request.id}",
            f"approval-final:{request.id}:failed",
        )
        await db.commit()
