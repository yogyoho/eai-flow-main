from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.approval_service import approve_decision, cancel_approval, create_approval, reset_for_retry
from app.auth import Identity, require_opportunity_access, require_sales_permission
from app.database import get_db
from app.domain import add_audit, approval_dict, utc_now
from app.errors import forbidden, not_found
from app.models import ApprovalAction, ApprovalRequest, ApprovalStep, Opportunity, OutboxEvent
from app.schemas import ApprovalCreate, ApprovalDecisionIn

router = APIRouter(tags=["approvals"])


def approval_scope(identity: Identity):
    if identity.is_admin or identity.data_scope == "all":
        return true()
    return or_(
        ApprovalRequest.requested_by == identity.user_id,
        ApprovalRequest.steps.any(
            and_(
                ApprovalStep.status == "active",
                or_(ApprovalStep.approver_role == identity.sales_role, ApprovalStep.approver_id == identity.user_id),
            )
        ),
    )


async def _load_request(db: AsyncSession, request_id: uuid.UUID, *, lock: bool = False) -> ApprovalRequest:
    stmt = select(ApprovalRequest).where(ApprovalRequest.id == request_id).options(selectinload(ApprovalRequest.steps))
    if lock:
        stmt = stmt.with_for_update()
    request = (await db.execute(stmt)).scalar_one_or_none()
    if request is None:
        raise not_found("审批单不存在", "SALES-404-APPROVAL")
    return request


def _can_view(identity: Identity, request: ApprovalRequest) -> bool:
    if identity.is_admin or identity.data_scope == "all":
        return True
    if request.requested_by == identity.user_id:
        return True
    return any(step.approver_role == identity.sales_role or step.approver_id == identity.user_id for step in request.steps)


async def _detail(db: AsyncSession, request: ApprovalRequest) -> dict[str, Any]:
    opportunity = await db.get(Opportunity, request.opportunity_id)
    data = approval_dict(request, opportunity)
    actions = list((await db.execute(select(ApprovalAction).where(ApprovalAction.request_id == request.id).order_by(ApprovalAction.created_at.asc()))).scalars())
    data["actions"] = [
        {
            "step_no": a.step_no,
            "action": a.action,
            "actor_id": a.actor_id,
            "actor_role": a.actor_role,
            "comment": a.comment,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in actions
    ]
    data["opportunity"] = (
        {
            "id": str(opportunity.id),
            "opportunity_no": opportunity.opportunity_no,
            "name": opportunity.name,
            "stage": opportunity.stage,
            "status": opportunity.status,
            "amount": float(opportunity.amount),
        }
        if opportunity
        else None
    )
    return data


@router.get("/approvals")
async def list_approvals(
    status: str | None = None,
    gate_code: str | None = None,
    opportunity_id: uuid.UUID | None = None,
    mine: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=200),
    identity: Identity = Depends(require_sales_permission("sales.approval.read")),
    db: AsyncSession = Depends(get_db),
):
    conditions = [approval_scope(identity)]
    if status:
        conditions.append(ApprovalRequest.status == status)
    if gate_code:
        conditions.append(ApprovalRequest.gate_code == gate_code)
    if opportunity_id:
        conditions.append(ApprovalRequest.opportunity_id == opportunity_id)
    base = select(ApprovalRequest).where(*conditions).options(selectinload(ApprovalRequest.steps))
    total = int((await db.execute(select(func.count(ApprovalRequest.id)).where(*conditions))).scalar_one())
    rows = list((await db.execute(base.order_by(ApprovalRequest.requested_at.desc()).offset(skip).limit(limit))).scalars())
    if mine:
        rows = [
            r
            for r in rows
            if r.status == "running" and r.requested_by != identity.user_id and any(s.status == "active" and (identity.is_admin or s.approver_role == identity.sales_role or s.approver_id == identity.user_id) for s in r.steps)
        ]
    opp_ids = {r.opportunity_id for r in rows}
    opps = {o.id: o for o in (await db.execute(select(Opportunity).where(Opportunity.id.in_(opp_ids)))).scalars()} if opp_ids else {}
    pending_my_action = sum(
        1 for r in rows if r.status == "running" and r.requested_by != identity.user_id and any(s.status == "active" and (identity.is_admin or s.approver_role == identity.sales_role or s.approver_id == identity.user_id) for s in r.steps)
    )
    return {
        "items": [approval_dict(r, opps.get(r.opportunity_id)) for r in rows],
        "total": total,
        "skip": skip,
        "limit": limit,
        "pending_my_action": pending_my_action,
    }


@router.get("/approvals/pending-count")
async def pending_count(
    identity: Identity = Depends(require_sales_permission("sales.approval.read")),
    db: AsyncSession = Depends(get_db),
):
    rows = list((await db.execute(select(ApprovalRequest).where(ApprovalRequest.status == "running", ApprovalRequest.requested_by != identity.user_id).options(selectinload(ApprovalRequest.steps)))).scalars())
    count = sum(1 for r in rows if any(s.status == "active" and (identity.is_admin or s.approver_role == identity.sales_role or s.approver_id == identity.user_id) for s in r.steps))
    return {"pending": count}


@router.post("/opportunities/{opportunity_id}/approvals", status_code=201)
async def request_approval(
    opportunity_id: uuid.UUID,
    body: ApprovalCreate,
    identity: Identity = Depends(require_sales_permission("sales.approval.request")),
    db: AsyncSession = Depends(get_db),
):
    opportunity = await db.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise not_found("商机不存在", "SALES-404-OPPORTUNITY")
    require_opportunity_access(identity, opportunity)
    request = await create_approval(
        db,
        opportunity,
        identity,
        gate_code=body.gate_code,
        reason=body.reason,
        evidence=body.evidence,
    )
    await db.commit()
    # The outbox worker owns workflow startup. Returning pending_start is
    # intentional: the page can poll and show "等待审批引擎" without lying.
    return {"id": str(request.id), "request_no": request.request_no, "status": request.status}


@router.get("/approvals/{request_id}")
async def get_approval(
    request_id: uuid.UUID,
    identity: Identity = Depends(require_sales_permission("sales.approval.read")),
    db: AsyncSession = Depends(get_db),
):
    request = await _load_request(db, request_id)
    if not _can_view(identity, request):
        raise forbidden("无权查看该审批", "SALES-403-APPROVAL_SCOPE")
    return await _detail(db, request)


@router.post("/approvals/{request_id}/decision", status_code=202)
async def decide(
    request_id: uuid.UUID,
    body: ApprovalDecisionIn,
    identity: Identity = Depends(require_sales_permission("sales.approval.decide")),
    db: AsyncSession = Depends(get_db),
):
    request = await approve_decision(
        db,
        request_id,
        identity,
        action=body.action,
        comment=body.comment,
        idempotency_key=body.idempotency_key,
        delegate_to=body.delegate_to,
    )
    return {"id": str(request.id), "status": request.status, "message": "决策已提交审批引擎"}


@router.post("/approvals/{request_id}/cancel", status_code=202)
async def cancel(
    request_id: uuid.UUID,
    payload: dict[str, Any] = Body(default={}),
    identity: Identity = Depends(require_sales_permission("sales.approval.cancel")),
    db: AsyncSession = Depends(get_db),
):
    request = await cancel_approval(
        db,
        request_id,
        identity,
        reason=str(payload.get("reason") or "发起人取消"),
    )
    return {"id": str(request.id), "status": request.status}


@router.post("/approvals/{request_id}/retry")
async def retry_start(
    request_id: uuid.UUID,
    identity: Identity = Depends(require_sales_permission("sales.approval.manage")),
    db: AsyncSession = Depends(get_db),
):
    request = await _load_request(db, request_id, lock=True)
    if request.status not in {"pending_start", "failed"}:
        return {"id": str(request.id), "status": request.status, "message": "无需重试"}
    event = (
        await db.execute(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == request.id,
                OutboxEvent.event_type == "approval.start",
            )
        )
    ).scalar_one_or_none()
    if event is None:
        event = OutboxEvent(
            aggregate_type="approval_request",
            aggregate_id=request.id,
            event_type="approval.start",
            payload_json={"request_id": str(request.id)},
            status="pending",
            next_retry_at=utc_now(),
        )
        db.add(event)
    else:
        event.status = "pending"
        event.next_retry_at = utc_now()
        event.attempts = 0
        event.last_error = None
        event.processed_at = None
    reset_for_retry(request)
    add_audit(
        db,
        actor_id=identity.user_id,
        action="approval.retry",
        object_type="approval_request",
        object_id=str(request.id),
    )
    await db.commit()
    return {"id": str(request.id), "status": "pending_start", "message": "已重置，等待审批 Worker 处理"}
