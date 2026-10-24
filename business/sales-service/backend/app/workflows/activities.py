"""Idempotent Temporal activities that project workflow progress into the DB."""

from __future__ import annotations

import hashlib
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
    ApprovalAssignment,
    ApprovalRequest,
    ApprovalStep,
    Notification,
    Opportunity,
    Todo,
)
from app.workflows.contracts import ApprovalWorkflowInput, DecisionSignal, WorkflowApprover, WorkflowStep
from app.workflows.parallel import PARALLEL_MODES, assignment_key_for, parallel_step_outcome

logger = logging.getLogger(__name__)


def _sid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


async def _load_request(db, request_id: str) -> ApprovalRequest | None:
    """Load an approval with its steps eagerly.

    Activities run outside the request's greenlet context; touching a lazy
    ``request.steps`` relationship there raises MissingGreenlet. Every activity
    that reads or mutates steps must go through this loader.
    """
    return (await db.execute(select(ApprovalRequest).where(ApprovalRequest.id == _sid(request_id)).options(selectinload(ApprovalRequest.steps).selectinload(ApprovalStep.assignments)))).scalar_one_or_none()


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


def _step_todo_base(request_id: uuid.UUID, step_no: int) -> str:
    return f"approval:{request_id}:step:{step_no}"


def _short_token(value: str) -> str:
    """Keep generated todo dedupe keys inside the 200-char column limit."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _bounded_key(value: str) -> str:
    """Return ``value`` when it fits ``Todo.dedupe_key``, otherwise a stable hash."""
    if len(value) <= 200:
        return value
    return f"approval:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


async def _close_step_todos(db, request_id: uuid.UUID, step_no: int, note: str) -> None:
    """Close every todo for one step without touching sibling steps."""
    base = _step_todo_base(request_id, step_no)
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
        if todo.dedupe_key == base or todo.dedupe_key.startswith(f"{base}:"):
            todo.status = "resolved"
            todo.resolution = note
            todo.resolved_at = utc_now()
    await db.flush()


async def _close_assignment_todos(db, request_id: uuid.UUID, step_no: int, assignment_key: str, note: str) -> None:
    prefix = f"{_step_todo_base(request_id, step_no)}:assignee:{assignment_key}"
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
        if todo.dedupe_key == prefix or todo.dedupe_key.startswith(f"{prefix}:"):
            todo.status = "resolved"
            todo.resolution = note
            todo.resolved_at = utc_now()
    await db.flush()


async def _retime_step_todos(db, request_id: uuid.UUID, step_no: int, due_at, note: str) -> None:
    base = _step_todo_base(request_id, step_no)
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
        if todo.dedupe_key == base or todo.dedupe_key.startswith(f"{base}:"):
            todo.due_at = due_at
            todo.sla_minutes = max(1, int((due_at - utc_now()).total_seconds() // 60))
            todo.updated_by = "temporal"


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
        if step.mode in PARALLEL_MODES:
            raise ApplicationError("并行审批步骤不能走顺序激活", non_retryable=True)
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


@activity.defn(name="activate_parallel_step")
async def activate_parallel_step(request_id: str, step: WorkflowStep) -> None:
    """Create one assignment/todo per participant and activate the step."""
    async with get_session_maker()() as db:
        request = await _load_request(db, request_id)
        if request is None or request.status != "running":
            return
        row = next((s for s in request.steps if s.step_no == step.step_no), None)
        if row is None:
            return
        if row.mode not in PARALLEL_MODES:
            raise ApplicationError("非并行审批步骤不能走并行激活", non_retryable=True)
        if row.status != "pending":
            return
        # A retry reset may leave old slots behind. They must be removed before
        # reusing the same unique assignment keys.
        await _close_step_todos(db, request.id, row.step_no, "审批重试，原待办已关闭")
        row.assignments.clear()
        await db.flush()

        approvers = list(step.approvers)
        if not approvers:
            approvers = [
                WorkflowApprover(
                    key=assignment_key_for(role=step.approver_role or None, user_id=step.approver_id),
                    role=step.approver_role or None,
                    user_id=step.approver_id,
                )
            ]
        now = utc_now()
        due_at = now + timedelta(hours=max(1, step.sla_hours))
        row.status = "active"
        row.sla_due_at = due_at
        request.current_step = row.step_no
        opportunity = await db.get(Opportunity, request.opportunity_id)
        for approver in approvers:
            role = approver.role or row.approver_role
            db.add(
                ApprovalAssignment(
                    step_id=row.id,
                    request_id=request.id,
                    step_no=row.step_no,
                    assignment_key=approver.key,
                    approver_role=role,
                    approver_id=approver.user_id,
                    status="active",
                )
            )
            await create_todo(
                db,
                type="approval",
                severity="high",
                title=f"审批：{request.gate_code} · {opportunity.opportunity_no if opportunity else request.request_no}",
                description=f"{request.reason or '请在审批中心处理'}（第 {row.step_no} 步/{row.mode}：{role}）",
                object_type="approval",
                object_id=request.id,
                dedupe_key=_bounded_key(f"{_step_todo_base(request.id, row.step_no)}:assignee:{approver.key}"),
                assignee_role=None if approver.user_id else role,
                assignee_id=approver.user_id,
                created_by="temporal",
                due_hours=max(1, step.sla_hours),
            )
        await _notify(
            db,
            request.requested_by,
            f"审批已流转：{request.request_no}",
            f"{request.gate_code} 审批进入第 {row.step_no} 步（{row.mode}），共 {len(approvers)} 个审批席位",
            f"/sales/approvals?focus={request.id}",
            f"approval-active:{request.id}:{row.step_no}",
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
        if step.mode in PARALLEL_MODES:
            raise ApplicationError("并行审批步骤不能走顺序升级", non_retryable=True)
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


@activity.defn(name="escalate_parallel_step")
async def escalate_parallel_step(request_id: str, step_no: int, reason: str, expected_level: int = 1) -> str:
    """Escalate only the still-active slots of a parallel step."""
    async with get_session_maker()() as db:
        request = await _load_request(db, request_id)
        if request is None:
            return "missing"
        if request.status != "running":
            return request.status
        step = next((s for s in request.steps if s.step_no == step_no), None)
        if step is None:
            return "missing-step"
        if step.mode not in PARALLEL_MODES:
            raise ApplicationError("非并行审批步骤不能走并行升级", non_retryable=True)
        if step.status != "active":
            return step.status
        if step.escalation_level >= expected_level:
            return step.status
        active = [assignment for assignment in step.assignments if assignment.status == "active"]
        if not active:
            return step.status
        await _close_step_todos(db, request.id, step_no, "审批超时升级，原待办已关闭")
        step.escalation_level = expected_level
        step.escalated_at = utc_now()
        step.sla_due_at = utc_now() + timedelta(hours=4)
        if step.approver_role == "regional_manager":
            step.approver_role = "sales_director"
        opportunity = await db.get(Opportunity, request.opportunity_id)
        for assignment in active:
            role = assignment.approver_role or step.approver_role or "sales_director"
            if role == "regional_manager":
                role = "sales_director"
            assignment.approver_role = role
            # An escalated slot belongs to the new role, not to a previous
            # delegate.
            assignment.approver_id = None
            await create_todo(
                db,
                type="approval",
                severity="blocker",
                title=f"审批超时升级：{request.gate_code} · {opportunity.opportunity_no if opportunity else request.request_no}",
                description=f"{reason}（第 {step_no} 步/{assignment.assignment_key}）",
                object_type="approval",
                object_id=request.id,
                dedupe_key=_bounded_key(f"{_step_todo_base(request.id, step_no)}:assignee:{assignment.assignment_key}:esc:{expected_level}"),
                assignee_role=role,
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
            after={"step_no": step_no, "level": step.escalation_level, "mode": step.mode, "pending_slots": [item.assignment_key for item in active]},
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
        return "active"


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
        if step.mode in PARALLEL_MODES:
            raise ApplicationError("并行审批步骤不能走顺序决策", non_retryable=True)
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


@activity.defn(name="record_parallel_decision")
async def record_parallel_decision(request_id: str, decision: DecisionSignal) -> str:
    """Record one participant decision and return the aggregated step status.

    The return value is intentionally the current step status, including on an
    idempotent retry. The workflow uses it to decide whether the step has
    reached a terminal outcome without reading the database itself.
    """
    if not decision.assignment_key:
        raise ApplicationError("并行审批决策缺少审批席位", non_retryable=True)
    async with get_session_maker()() as db:
        existing = (await db.execute(select(ApprovalAction).where(ApprovalAction.idempotency_key == decision.idempotency_key))).scalar_one_or_none()
        if existing:
            if existing.request_id == _sid(request_id) and existing.step_no == decision.step_no and existing.assignment_key == decision.assignment_key and existing.action == decision.action and existing.actor_id == decision.actor_id:
                request = await _load_request(db, request_id)
                if request is None:
                    return "missing"
                step = next((s for s in request.steps if s.step_no == decision.step_no), None)
                return step.status if step else "missing-step"
            raise ApplicationError("审批幂等键冲突", non_retryable=True)

        request = await _load_request(db, request_id)
        if request is None:
            return "missing"
        if request.status != "running":
            return "not-running"
        step = next((s for s in request.steps if s.step_no == decision.step_no), None)
        if step is None:
            return "missing-step"
        if step.mode not in PARALLEL_MODES:
            raise ApplicationError("非并行审批步骤不能记录并行决策", non_retryable=True)
        if step.status != "active":
            return step.status
        assignment = next((item for item in step.assignments if item.assignment_key == decision.assignment_key), None)
        if assignment is None:
            raise ApplicationError("并行审批席位不存在", non_retryable=True)
        if assignment.status != "active":
            return step.status
        if decision.action not in {"approve", "reject", "return"}:
            raise ApplicationError("并行决策动作非法", non_retryable=True)
        if decision.action in {"reject", "return"} and not (decision.comment or "").strip():
            raise ApplicationError("驳回或退回必须填写意见", non_retryable=True)

        now = utc_now()
        status_by_action = {"approve": "approved", "reject": "rejected", "return": "returned"}
        assignment.status = status_by_action[decision.action]
        assignment.decision = decision.action
        assignment.comment = decision.comment
        assignment.decided_at = now
        assignment.idempotency_key = decision.idempotency_key
        db.add(
            ApprovalAction(
                request_id=request.id,
                step_no=decision.step_no,
                assignment_key=decision.assignment_key,
                action=decision.action,
                actor_id=decision.actor_id,
                actor_role=decision.actor_role,
                comment=decision.comment,
                idempotency_key=decision.idempotency_key,
            )
        )
        await _close_assignment_todos(db, request.id, step.step_no, assignment.assignment_key, "该审批席位已处理")
        add_audit(
            db,
            actor_id=decision.actor_id,
            action=f"approval.{decision.action}",
            object_type="approval_request",
            object_id=str(request.id),
            after={"step_no": decision.step_no, "assignment_key": decision.assignment_key, "comment": decision.comment},
        )

        outcome = parallel_step_outcome(step.mode, [item.status for item in step.assignments])
        if outcome == "active":
            await db.commit()
            return outcome

        step.status = outcome
        step.decision = {"approved": "approve", "rejected": "reject", "returned": "return"}[outcome]
        step.comment = decision.comment
        step.decided_at = now
        step.idempotency_key = decision.idempotency_key
        for other in step.assignments:
            if other is assignment:
                continue
            if other.status == "active":
                other.status = "skipped"
                other.comment = "步骤已结束，无需继续处理"
                other.decided_at = now
        await _close_step_todos(db, request.id, step.step_no, f"审批步骤已{ {'approved': '通过', 'rejected': '驳回', 'returned': '退回'}[outcome] }")
        add_audit(
            db,
            actor_id="temporal",
            actor_type="system",
            action=f"approval.step.{outcome}",
            object_type="approval_request",
            object_id=str(request.id),
            after={"step_no": step.step_no, "mode": step.mode, "assignments": {item.assignment_key: item.status for item in step.assignments}},
        )
        await _notify(
            db,
            request.requested_by,
            f"审批步骤已{ {'approved': '通过', 'rejected': '驳回', 'returned': '退回'}[outcome] }：{request.request_no}",
            f"{request.gate_code} 审批第 {step.step_no} 步（{step.mode}）已结束",
            f"/sales/approvals?focus={request.id}",
            f"approval-step:{request.id}:{step.step_no}:{outcome}",
        )
        await db.commit()
        return outcome


@activity.defn(name="delegate_parallel_assignment")
async def delegate_parallel_assignment(request_id: str, decision: DecisionSignal) -> str:
    """Delegate only one participant slot; other slots keep their state."""
    if not decision.assignment_key:
        raise ApplicationError("并行转办缺少审批席位", non_retryable=True)
    async with get_session_maker()() as db:
        existing = (await db.execute(select(ApprovalAction).where(ApprovalAction.idempotency_key == decision.idempotency_key))).scalar_one_or_none()
        if existing:
            if existing.request_id == _sid(request_id) and existing.step_no == decision.step_no and existing.assignment_key == decision.assignment_key and existing.action == "delegate" and existing.actor_id == decision.actor_id:
                request = await _load_request(db, request_id)
                if request is None:
                    return "missing"
                step = next((s for s in request.steps if s.step_no == decision.step_no), None)
                return step.status if step else "missing-step"
            raise ApplicationError("审批幂等键冲突", non_retryable=True)

        request = await _load_request(db, request_id)
        if request is None:
            return "missing"
        if request.status != "running":
            return "not-running"
        step = next((s for s in request.steps if s.step_no == decision.step_no), None)
        if step is None:
            return "missing-step"
        if step.mode not in PARALLEL_MODES:
            raise ApplicationError("非并行审批步骤不能走并行转办", non_retryable=True)
        if step.status != "active":
            return step.status
        assignment = next((item for item in step.assignments if item.assignment_key == decision.assignment_key), None)
        if assignment is None:
            raise ApplicationError("并行审批席位不存在", non_retryable=True)
        if assignment.status != "active":
            return step.status
        if not decision.delegate_to:
            raise ApplicationError("转办必须指定接收人", non_retryable=True)

        assignment.approver_id = decision.delegate_to
        if assignment.delegated_from is None:
            assignment.delegated_from = decision.actor_id
        assignment.status = "active"
        assignment.decision = None
        assignment.comment = None
        assignment.decided_at = None
        step.sla_due_at = utc_now() + timedelta(hours=24)
        await _close_assignment_todos(db, request.id, step.step_no, assignment.assignment_key, "审批席位已转办")
        await _retime_step_todos(db, request.id, step.step_no, step.sla_due_at, "审批转办，时限重置")
        db.add(
            ApprovalAction(
                request_id=request.id,
                step_no=decision.step_no,
                assignment_key=decision.assignment_key,
                action="delegate",
                actor_id=decision.actor_id,
                actor_role=decision.actor_role,
                comment=decision.comment,
                idempotency_key=decision.idempotency_key,
            )
        )
        opportunity = await db.get(Opportunity, request.opportunity_id)
        await create_todo(
            db,
            type="approval",
            severity="high",
            title=f"转办审批：{request.gate_code} · {opportunity.opportunity_no if opportunity else request.request_no}",
            description=f"{decision.actor_id} 将第 {decision.step_no} 步（{assignment.assignment_key}）转办给你。",
            object_type="approval",
            object_id=request.id,
            dedupe_key=_bounded_key(f"{_step_todo_base(request.id, step.step_no)}:assignee:{assignment.assignment_key}:delegate:{_short_token(decision.idempotency_key)}"),
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
            after={"step_no": decision.step_no, "assignment_key": decision.assignment_key, "delegate_to": decision.delegate_to},
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
        return "active"


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
        if step.mode in PARALLEL_MODES:
            raise ApplicationError("并行审批步骤不能走顺序转办", non_retryable=True)
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
            dedupe_key=_bounded_key(f"approval:{request.id}:step:{decision.step_no}:delegate:{decision.idempotency_key}"),
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
        final_now = utc_now()
        for step in request.steps:
            for assignment in step.assignments:
                if assignment.status == "active":
                    assignment.status = "skipped"
                    assignment.comment = assignment.comment or "审批流程已结束"
                    assignment.decided_at = final_now
            if status in {"rejected", "returned", "cancelled", "expired"}:
                if step.status == "active":
                    step.status = status
                    step.decided_at = final_now
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
        failed_at = utc_now()
        for step in request.steps:
            for assignment in step.assignments:
                if assignment.status == "active":
                    assignment.status = "skipped"
                    assignment.comment = assignment.comment or "审批执行失败"
                    assignment.decided_at = failed_at
            if step.status == "active":
                step.status = "cancelled"
                step.decided_at = failed_at
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
