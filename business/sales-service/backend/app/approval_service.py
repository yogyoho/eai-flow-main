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
from app.workflows.contracts import ApprovalWorkflowInput, CancellationSignal, DecisionSignal, WorkflowStep

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
    steps: list[dict[str, Any]] = [dict(s) for s in definition["steps"]]
    if template_key == "DUPLICATE":
        duplicate = await db.get(OpportunityDuplicate, uuid.UUID(gate_evidence["duplicate_case_id"]))
        other = await db.get(Opportunity, duplicate.duplicate_opportunity_id) if duplicate else None
        if other and other.region_code != opportunity.region_code:
            if not any(s["approver_role"] == "sales_director" for s in steps):
                steps.append({"step_no": len(steps) + 1, "approver_role": "sales_director", "sla_hours": 24})

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


def workflow_input_for(request: ApprovalRequest) -> ApprovalWorkflowInput:
    expires_at = request.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
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
            )
            for step in request.steps
        ],
        expires_at_epoch=expires_at.timestamp() if expires_at else None,
    )


async def _load_request(db: AsyncSession, request_id: uuid.UUID) -> ApprovalRequest:
    request = (await db.execute(select(ApprovalRequest).where(ApprovalRequest.id == request_id).options(selectinload(ApprovalRequest.steps)))).scalar_one_or_none()
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
