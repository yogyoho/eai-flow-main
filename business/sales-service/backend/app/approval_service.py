"""Approval request orchestration. Temporal executes; this module owns facts."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import Identity
from app.config import get_settings
from app.domain import add_audit, next_number, utc_now
from app.enums import STAGE_LABELS
from app.errors import bad_request, conflict, forbidden, not_found, unavailable
from app.models import (
    ApprovalAction,
    ApprovalDefinition,
    ApprovalRequest,
    ApprovalStep,
    Customer,
    CustomerGroup,
    Opportunity,
    OpportunityDuplicate,
    OutboxEvent,
    PilotProject,
)
from app.workflows.client import signal_cancel, signal_decision
from app.workflows.contracts import ApprovalWorkflowInput, CancellationSignal, DecisionSignal, WorkflowApprover, WorkflowStep
from app.workflows.parallel import PARALLEL_MODES, STEP_MODES, assignment_key_for

logger = logging.getLogger(__name__)
settings = get_settings()

TEMPLATES: dict[str, dict[str, Any]] = {
    "R4": {
        "code": "R4_EXCEPTION",
        "name": "R4 新客户无示范面例外",
        "steps": [
            {"step_no": 1, "approver_role": "regional_manager", "sla_hours": 24},
            {"step_no": 2, "approver_role": "sales_director", "sla_hours": 24},
        ],
    },
    "R6": {
        "code": "R6_RELATED_PARTY",
        "name": "R6 关联方交易合规审批",
        "steps": [
            {"step_no": 1, "approver_role": "regional_manager", "sla_hours": 24},
            {"step_no": 2, "approver_role": "sales_director", "sla_hours": 24},
            {"step_no": 3, "approver_role": "compliance_officer", "sla_hours": 48},
        ],
    },
    "DUPLICATE": {
        "code": "DUPLICATE_MERGE",
        "name": "R10 撞单合并审批",
        "steps": [
            {"step_no": 1, "approver_role": "regional_manager", "sla_hours": 24},
        ],
    },
}

GATE_TO_TEMPLATE = {"R4": "R4", "R6": "R6", "DUPLICATE": "DUPLICATE", "R10": "DUPLICATE"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _step_has_role(step: dict[str, Any], role: str) -> bool:
    if _text(step.get("approver_role")) == role:
        return True
    return any(_text(item.get("role") or item.get("approver_role")) == role for item in step.get("approvers") or [] if isinstance(item, dict))


def _positive_int(value: Any, default: int, *, field: str) -> int:
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError) as exc:
        raise bad_request(f"审批步骤 {field} 必须为整数", "SALES-400-APPROVAL_STEP") from exc
    if parsed < 1:
        raise bad_request(f"审批步骤 {field} 必须大于 0", "SALES-400-APPROVAL_STEP")
    return parsed


def normalize_template_steps(raw_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize a template snapshot.

    Sequential steps keep the existing single ``approver_role`` shape. Parallel
    steps receive a stable ``approvers`` list whose keys are used by Signals,
    idempotency checks and per-participant todos.
    """
    normalized: list[dict[str, Any]] = []
    seen_steps: set[int] = set()
    for index, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict):
            raise bad_request("审批步骤配置必须为对象", "SALES-400-APPROVAL_STEP")
        step_no = _positive_int(raw.get("step_no"), index, field="step_no")
        if step_no in seen_steps:
            raise bad_request(f"审批步骤 {step_no} 重复", "SALES-400-APPROVAL_STEP")
        seen_steps.add(step_no)
        mode = _text(raw.get("mode")) or "sequential"
        if mode not in STEP_MODES:
            raise bad_request(f"未知审批步骤模式：{mode}", "SALES-400-APPROVAL_STEP_MODE")
        sla_hours = _positive_int(raw.get("sla_hours"), 24, field="sla_hours")
        if mode == "sequential":
            role = _text(raw.get("approver_role"))
            if not role:
                raise bad_request(f"第 {step_no} 步缺少审批角色", "SALES-400-APPROVAL_STEP")
            normalized.append({"step_no": step_no, "mode": mode, "approver_role": role, "approver_id": raw.get("approver_id"), "sla_hours": sla_hours, "approvers": []})
            continue

        raw_approvers = raw.get("approvers") or []
        if not isinstance(raw_approvers, list) or not raw_approvers:
            raise bad_request(f"第 {step_no} 步的 {mode} 模式必须配置 approvers", "SALES-400-APPROVAL_STEP")
        approvers: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for item in raw_approvers:
            if not isinstance(item, dict):
                raise bad_request(f"第 {step_no} 步的审批席位必须为对象", "SALES-400-APPROVAL_STEP")
            role = _text(item.get("role") or item.get("approver_role")) or None
            user_id = _text(item.get("user_id") or item.get("approver_id")) or None
            if not role and not user_id:
                raise bad_request(f"第 {step_no} 步存在空审批席位", "SALES-400-APPROVAL_STEP")
            explicit = _text(item.get("key"))
            key = explicit or assignment_key_for(role=role, user_id=user_id)
            if len(key) > 128:
                raise bad_request("审批席位 key 过长", "SALES-400-APPROVAL_STEP")
            if key in seen_keys:
                raise bad_request(f"第 {step_no} 步审批席位重复：{key}", "SALES-400-APPROVAL_STEP")
            seen_keys.add(key)
            approvers.append({"key": key, "role": role, "user_id": user_id})
        # ``approver_role`` is the display/escalation fallback. User-only slots
        # need a real role here so SLA escalation cannot create an unreachable
        # pseudo-role such as "parallel".
        primary_role = _text(raw.get("approver_role")) or next((item["role"] for item in approvers if item["role"]), "sales_director")
        normalized.append({"step_no": step_no, "mode": mode, "approver_role": primary_role, "approver_id": None, "sla_hours": sla_hours, "approvers": approvers})
    if not normalized:
        raise bad_request("审批模板没有步骤", "SALES-400-APPROVAL_STEP")
    return normalized


async def _definition_for(db: AsyncSession, code: str) -> dict[str, Any]:
    row = (await db.execute(select(ApprovalDefinition).where(ApprovalDefinition.code == code, ApprovalDefinition.is_active.is_(True)).order_by(ApprovalDefinition.version.desc()).limit(1))).scalar_one_or_none()
    if row:
        return {"definition": row, "steps": row.steps_json, "version": row.version}
    for template in TEMPLATES.values():
        if template["code"] == code:
            return {"definition": None, "steps": template["steps"], "version": 1}
    raise not_found("未配置审批模板", "SALES-404-APPROVAL_TEMPLATE")


async def _validate_gate(db: AsyncSession, opportunity: Opportunity, gate_code: str) -> dict[str, Any]:
    if gate_code == "R4":
        customer = await db.get(Customer, opportunity.customer_id)
        group = await db.get(CustomerGroup, customer.group_id) if customer and customer.group_id else None
        if not group or not group.is_new_customer:
            raise conflict("当前客户不是新客户，无需 R4 例外审批", "SALES-409-GATE_NOT_APPLICABLE")
        pilot_count = int((await db.execute(select(func.count(PilotProject.id)).where(PilotProject.customer_group_id == group.id))).scalar_one())
        if pilot_count:
            raise conflict("已有示范面，无需 R4 例外审批", "SALES-409-GATE_NOT_APPLICABLE")
        return {"customer_group_id": str(group.id), "pilot_count": 0}
    if gate_code == "R6":
        customer = await db.get(Customer, opportunity.customer_id)
        if not customer or customer.related_party_status != "yes":
            raise conflict("当前客户不是关联方，无需 R6 审批", "SALES-409-GATE_NOT_APPLICABLE")
        return {"related_party_status": customer.related_party_status}
    if gate_code in {"DUPLICATE", "R10"}:
        case = (await db.execute(select(OpportunityDuplicate).where(OpportunityDuplicate.opportunity_id == opportunity.id, OpportunityDuplicate.status == "pending").limit(1))).scalar_one_or_none()
        if case is None:
            raise conflict("当前商机没有待处理撞单", "SALES-409-GATE_NOT_APPLICABLE")
        return {"duplicate_case_id": str(case.id)}
    raise bad_request("未知审批闸门", "SALES-400-GATE")


async def create_approval(
    db: AsyncSession,
    opportunity: Opportunity,
    identity: Identity,
    *,
    gate_code: str,
    reason: str,
    evidence: dict[str, Any] | None = None,
) -> ApprovalRequest:
    template_key = GATE_TO_TEMPLATE.get(gate_code)
    if not template_key:
        raise bad_request("QW2 仅支持 R4 / R6 / 撞单合并审批", "SALES-400-GATE")
    if not settings.temporal_enabled:
        raise unavailable()
    existing = (
        await db.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.opportunity_id == opportunity.id,
                ApprovalRequest.gate_code == gate_code,
                ApprovalRequest.status.in_(["pending_start", "running"]),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        raise conflict("该闸门已有进行中的审批", "SALES-409-APPROVAL_EXISTS")
    approved = (
        await db.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.opportunity_id == opportunity.id,
                ApprovalRequest.gate_code == gate_code,
                ApprovalRequest.status == "approved",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if approved:
        raise conflict("该闸门已审批通过", "SALES-409-GATE_ALREADY_APPROVED")

    gate_evidence = await _validate_gate(db, opportunity, gate_code)
    evidence = {**(evidence or {}), **gate_evidence}
    template = TEMPLATES[template_key]
    definition = await _definition_for(db, template["code"])
    raw_steps: list[dict[str, Any]] = [dict(s) for s in definition["steps"]]
    if template_key == "DUPLICATE":
        duplicate = await db.get(OpportunityDuplicate, uuid.UUID(gate_evidence["duplicate_case_id"]))
        other = await db.get(Opportunity, duplicate.duplicate_opportunity_id) if duplicate else None
        if other and other.region_code != opportunity.region_code:
            if not any(_step_has_role(s, "sales_director") for s in raw_steps):
                raw_steps.append({"step_no": len(raw_steps) + 1, "approver_role": "sales_director", "sla_hours": 24})
    steps = normalize_template_steps(raw_steps)

    period = utc_now().strftime("%Y%m")
    request = ApprovalRequest(
        request_no=await next_number(db, "AP", period),
        definition_code=template["code"],
        definition_version=definition["version"],
        opportunity_id=opportunity.id,
        gate_code=gate_code,
        status="pending_start",
        current_step=1,
        reason=reason,
        evidence_json=evidence,
        payload_json={
            "opportunity_no": opportunity.opportunity_no,
            "opportunity_name": opportunity.name,
            "stage": opportunity.stage,
            "stage_label": STAGE_LABELS.get(opportunity.stage, opportunity.stage),
            "amount": float(opportunity.amount),
            "region_code": opportunity.region_code,
            # Snapshot the original steps so an explicit retry can restore
            # roles/SLA without reading a mutable template version.
            "approval_steps": [dict(step) for step in steps],
        },
        requested_by=identity.user_id,
        expires_at=utc_now() + timedelta(days=7),
    )
    for step in steps:
        request.steps.append(
            ApprovalStep(
                step_no=int(step["step_no"]),
                mode=str(step.get("mode", "sequential")),
                approver_role=str(step["approver_role"]),
                approver_id=step.get("approver_id"),
                status="pending",
                sla_due_at=utc_now() + timedelta(hours=int(step["sla_hours"])),
                idempotency_key=None,
            )
        )
    db.add(request)
    await db.flush()
    db.add(
        OutboxEvent(
            aggregate_type="approval_request",
            aggregate_id=request.id,
            event_type="approval.start",
            payload_json={"request_id": str(request.id)},
            status="pending",
            next_retry_at=utc_now(),
        )
    )
    add_audit(
        db,
        actor_id=identity.user_id,
        action="approval.request",
        object_type="approval_request",
        object_id=str(request.id),
        after={"gate_code": gate_code, "template": template["code"], "steps": len(steps)},
    )
    await db.flush()
    return request


def reset_for_retry(request: ApprovalRequest, now: datetime | None = None) -> None:
    """Reset a failed request before an explicit admin retry.

    Temporal cannot safely resume a run whose projection was already partially
    applied, so a retry is a fresh attempt from step 1. The original step roles
    and SLA are restored from the creation snapshot in ``payload_json``.
    """
    current = now or utc_now()
    snapshot = (request.payload_json or {}).get("approval_steps") or []
    by_step = {int(item["step_no"]): item for item in snapshot if isinstance(item, dict) and "step_no" in item}
    request.status = "pending_start"
    request.current_step = 1
    request.workflow_id = None
    request.workflow_run_id = None
    request.started_at = None
    request.completed_at = None
    request.failure_reason = None
    request.expires_at = current + timedelta(days=7)
    for step in request.steps:
        source = by_step.get(step.step_no, {})
        step.approver_role = str(source.get("approver_role") or step.approver_role)
        step.mode = str(source.get("mode") or step.mode)
        # Restore the template assignee, dropping any runtime delegation.
        step.approver_id = source.get("approver_id")
        # A retry is a fresh attempt. Old parallel slots (and their decisions)
        # must not survive into the new workflow run.
        assignments = getattr(step, "assignments", None)
        if assignments is not None:
            assignments.clear()
        step.status = "pending"
        step.decision = None
        step.comment = None
        step.decided_at = None
        step.escalated_at = None
        step.escalation_level = 0
        step.idempotency_key = None
        step.sla_due_at = current + timedelta(hours=max(1, int(source.get("sla_hours") or 24)))


def _remaining_sla_hours(step: ApprovalStep) -> int:
    if step.sla_due_at is None:
        return 24
    due_at = step.sla_due_at if step.sla_due_at.tzinfo is not None else step.sla_due_at.replace(tzinfo=UTC)
    return max(1, int((due_at - utc_now()).total_seconds() // 3600))


def _workflow_approvers(step: ApprovalStep, source: dict[str, Any]) -> list[WorkflowApprover]:
    if step.mode not in PARALLEL_MODES:
        return []
    raw = source.get("approvers") or []
    approvers: list[WorkflowApprover] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = _text(item.get("role") or item.get("approver_role")) or None
        user_id = _text(item.get("user_id") or item.get("approver_id")) or None
        key = _text(item.get("key"))
        if not key:
            if not role and not user_id:
                continue
            key = assignment_key_for(role=role, user_id=user_id)
        approvers.append(WorkflowApprover(key=key, role=role, user_id=user_id))
    if not approvers:
        # Legacy/manual rows may lack a snapshot. Preserve a single-slot
        # fallback so the workflow still has an executable contract.
        key = assignment_key_for(role=step.approver_role or None, user_id=step.approver_id)
        approvers.append(WorkflowApprover(key=key, role=step.approver_role or None, user_id=step.approver_id))
    return approvers


def workflow_input_for(request: ApprovalRequest) -> ApprovalWorkflowInput:
    expires_at = request.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    snapshot = {int(item["step_no"]): item for item in (getattr(request, "payload_json", None) or {}).get("approval_steps") or [] if isinstance(item, dict) and item.get("step_no") is not None}
    return ApprovalWorkflowInput(
        request_id=str(request.id),
        request_no=request.request_no,
        opportunity_id=str(request.opportunity_id),
        gate_code=request.gate_code,
        requested_by=request.requested_by,
        steps=[
            WorkflowStep(
                step_no=step.step_no,
                approver_role=step.approver_role,
                approver_id=step.approver_id,
                sla_hours=_remaining_sla_hours(step),
                mode=step.mode,
                approvers=_workflow_approvers(step, snapshot.get(step.step_no, {})),
            )
            for step in request.steps
        ],
        expires_at_epoch=expires_at.timestamp() if expires_at else None,
    )


async def _load_request(db: AsyncSession, request_id: uuid.UUID) -> ApprovalRequest:
    request = (await db.execute(select(ApprovalRequest).where(ApprovalRequest.id == request_id).options(selectinload(ApprovalRequest.steps).selectinload(ApprovalStep.assignments)))).scalar_one_or_none()
    if request is None:
        raise not_found("审批单不存在", "SALES-404-APPROVAL")
    return request


async def approve_decision(
    db: AsyncSession,
    request_id: uuid.UUID,
    identity: Identity,
    *,
    action: str,
    comment: str | None,
    idempotency_key: str,
    delegate_to: str | None = None,
    assignment_key: str | None = None,
) -> ApprovalRequest:
    request = await _load_request(db, request_id)
    duplicate = (await db.execute(select(ApprovalAction).where(ApprovalAction.idempotency_key == idempotency_key))).scalar_one_or_none()
    if duplicate:
        if duplicate.request_id == request.id and duplicate.actor_id == identity.user_id:
            return request
        raise conflict("幂等键已被其他审批操作使用", "SALES-409-IDEMPOTENCY_KEY")
    if request.status == "pending_start":
        raise conflict("审批引擎尚未启动，请稍后重试", "SALES-409-APPROVAL_NOT_STARTED")
    if request.status != "running":
        raise conflict("审批单当前不可操作", "SALES-409-APPROVAL_CLOSED")
    step = next((s for s in request.steps if s.step_no == request.current_step), None)
    if step is None or step.status != "active":
        raise conflict("当前审批步骤未激活", "SALES-409-STEP_NOT_ACTIVE")
    if action in {"reject", "return"} and not (comment or "").strip():
        raise bad_request("驳回或退回必须填写意见", "SALES-400-COMMENT_REQUIRED")
    if action == "delegate" and not (delegate_to or "").strip():
        raise bad_request("转办必须指定接收人", "SALES-400-DELEGATE_TARGET")
    if action not in {"approve", "reject", "return", "delegate"}:
        raise bad_request("未知审批动作", "SALES-400-ACTION")

    if step.mode in PARALLEL_MODES:
        if not assignment_key:
            raise bad_request("会签/或签步骤必须指定审批席位", "SALES-400-ASSIGNMENT_KEY")
        assignment = next((item for item in step.assignments if item.assignment_key == assignment_key and item.status == "active"), None)
        if assignment is None:
            raise conflict("审批席位不存在或已处理", "SALES-409-ASSIGNMENT_NOT_ACTIVE")
        if assignment.approver_id:
            allowed = identity.is_admin or assignment.approver_id == identity.user_id
        else:
            allowed = identity.is_admin or identity.sales_role == assignment.approver_role or identity.role_code == assignment.approver_role
        if not allowed:
            raise forbidden(f"当前审批席位需要 {assignment.approver_id or assignment.approver_role} 审批", "AUTH-403-APPROVER_ROLE")
    else:
        if assignment_key:
            raise bad_request("顺序审批步骤不接受审批席位", "SALES-400-ASSIGNMENT_KEY")
        if step.approver_id:
            # An explicit assignee (template default or delegation) narrows the
            # step to that user; role membership alone is not enough.
            allowed = identity.is_admin or step.approver_id == identity.user_id
        else:
            allowed = identity.is_admin or identity.sales_role == step.approver_role or identity.role_code == step.approver_role
        if not allowed:
            raise forbidden(f"当前步骤需要 {step.approver_id or step.approver_role} 审批", "AUTH-403-APPROVER_ROLE")

    signal = DecisionSignal(
        step_no=step.step_no,
        action=action,
        actor_id=identity.user_id,
        actor_role=identity.sales_role,
        comment=comment,
        idempotency_key=idempotency_key,
        delegate_to=delegate_to,
        assignment_key=assignment_key,
    )
    try:
        await signal_decision(str(request.id), signal)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Temporal decision signal failed: %s", exc)
        raise unavailable("审批引擎暂不可用，决策未提交") from exc
    return request


async def cancel_approval(
    db: AsyncSession,
    request_id: uuid.UUID,
    identity: Identity,
    *,
    reason: str,
) -> ApprovalRequest:
    request = await _load_request(db, request_id)
    if request.status not in {"pending_start", "running"}:
        raise conflict("审批单已结束", "SALES-409-APPROVAL_CLOSED")
    if request.requested_by != identity.user_id and not identity.is_admin:
        raise forbidden("只有发起人或管理员可以取消", "SALES-403-CANCEL")
    if request.status == "pending_start":
        request.status = "cancelled"
        request.completed_at = utc_now()
        request.failure_reason = reason
        add_audit(
            db,
            actor_id=identity.user_id,
            action="approval.cancel",
            object_type="approval_request",
            object_id=str(request.id),
            after={"reason": reason},
        )
        await db.flush()
        return request
    try:
        await signal_cancel(str(request.id), CancellationSignal(actor_id=identity.user_id, reason=reason))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Temporal cancel signal failed: %s", exc)
        raise unavailable("审批引擎暂不可用，取消未提交") from exc
    return request
