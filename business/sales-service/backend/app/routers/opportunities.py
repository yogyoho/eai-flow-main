from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import (
    Identity,
    require_opportunity_access,
    require_sales_permission,
    scope_condition,
)
from app.database import get_db
from app.domain import (
    add_audit,
    create_duplicate_case,
    detect_duplicate,
    funnel_stage_rows,
    next_number,
    opportunity_dict,
    refresh_probability,
    resolve_duplicate_case,
    rollback_opportunity,
    serialize_opportunities,
    stage_due_for,
    transition_opportunity,
    utc_now,
)
from app.enums import STAGE_BASE_PROBABILITY, STAGE_LABELS, STAGES
from app.errors import conflict, forbidden, not_found, unprocessable
from app.models import (
    ApprovalRequest,
    ApprovalStep,
    Contact,
    Customer,
    CustomerGroup,
    Mine,
    Opportunity,
    OpportunityContact,
    OpportunityDuplicate,
    OpportunityGateCheck,
    OpportunityProbabilityHistory,
    OpportunityStageHistory,
    Todo,
    Workface,
)
from app.schemas import OpportunityCreate, OpportunityUpdate, ProbabilityIn, RollbackIn, TransitionIn

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


async def _load(db: AsyncSession, opportunity_id: uuid.UUID, *, lock: bool = False) -> Opportunity:
    stmt = select(Opportunity).where(Opportunity.id == opportunity_id)
    if lock:
        stmt = stmt.with_for_update()
    opp = (await db.execute(stmt)).scalar_one_or_none()
    if opp is None:
        raise not_found("商机不存在", "SALES-404-OPPORTUNITY")
    return opp


async def _detail(db: AsyncSession, opp: Opportunity) -> dict[str, Any]:
    customer = await db.get(Customer, opp.customer_id)
    group = await db.get(CustomerGroup, customer.group_id) if customer and customer.group_id else None
    workface = await db.get(Workface, opp.workface_id) if opp.workface_id else None
    history = list((await db.execute(select(OpportunityStageHistory).where(OpportunityStageHistory.opportunity_id == opp.id).order_by(OpportunityStageHistory.created_at.desc()).limit(30))).scalars())
    probabilities = list((await db.execute(select(OpportunityProbabilityHistory).where(OpportunityProbabilityHistory.opportunity_id == opp.id).order_by(OpportunityProbabilityHistory.created_at.desc()).limit(30))).scalars())
    gates = list((await db.execute(select(OpportunityGateCheck).where(OpportunityGateCheck.opportunity_id == opp.id).order_by(OpportunityGateCheck.checked_at.desc()).limit(40))).scalars())
    duplicates = list((await db.execute(select(OpportunityDuplicate).where(or_(OpportunityDuplicate.opportunity_id == opp.id, OpportunityDuplicate.duplicate_opportunity_id == opp.id)))).scalars())
    approvals = list(
        (await db.execute(select(ApprovalRequest).where(ApprovalRequest.opportunity_id == opp.id).options(selectinload(ApprovalRequest.steps).selectinload(ApprovalStep.assignments)).order_by(ApprovalRequest.requested_at.desc()))).scalars()
    )
    todos = list((await db.execute(select(Todo).where(Todo.object_type == "opportunity", Todo.object_id == opp.id).order_by(Todo.created_at.desc()).limit(20))).scalars())
    contacts = list((await db.execute(select(Contact, OpportunityContact).join(OpportunityContact, OpportunityContact.contact_id == Contact.id).where(OpportunityContact.opportunity_id == opp.id))).all())
    gate_rows = [
        {
            "gate_code": g.gate_code,
            "status": g.status,
            "message": g.message,
            "evidence": g.evidence_json,
            "checked_at": g.checked_at.isoformat() if g.checked_at else None,
        }
        for g in gates
    ]
    pending_gate_codes = {g["gate_code"] for g in gate_rows if g["status"] == "block"}
    base = opportunity_dict(
        opp,
        customer=customer,
        customer_group_name=group.name if group else None,
        workface_name=workface.name if workface else None,
    )
    base.update(
        {
            "customer": {
                "id": str(customer.id),
                "name": customer.name,
                "group_id": str(customer.group_id) if customer.group_id else None,
                "group_name": group.name if group else None,
                "related_party_status": customer.related_party_status,
                "region_code": customer.region_code,
                "completeness": customer.completeness,
                "data_as_of": customer.data_as_of.isoformat() if customer.data_as_of else None,
            }
            if customer
            else None,
            "mine": {"id": str(opp.mine_id), "name": None} if opp.mine_id else None,
            "workface": {"id": str(workface.id), "name": workface.name} if workface else None,
            "history": [
                {
                    "id": str(h.id),
                    "from_stage": h.from_stage,
                    "to_stage": h.to_stage,
                    "action": h.action,
                    "reason": h.reason,
                    "impact": h.impact,
                    "remedy": h.remedy,
                    "operator_id": h.operator_id,
                    "created_at": h.created_at.isoformat() if h.created_at else None,
                }
                for h in history
            ],
            "probability_history": [
                {
                    "rule_probability": float(p.rule_probability),
                    "manual_probability": float(p.manual_probability) if p.manual_probability is not None else None,
                    "effective_probability": float(p.effective_probability),
                    "manual_reason": p.manual_reason,
                    "changed_by": p.changed_by,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in probabilities
            ],
            "gates": gate_rows,
            "pending_gate_codes": sorted(pending_gate_codes),
            "duplicates": [
                {
                    "id": str(d.id),
                    "opportunity_id": str(d.opportunity_id),
                    "duplicate_opportunity_id": str(d.duplicate_opportunity_id),
                    "status": d.status,
                    "match_keys": d.match_keys,
                    "resolution": d.resolution,
                    "reason": d.reason,
                    "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None,
                }
                for d in duplicates
            ],
            "approvals": [
                {
                    "id": str(a.id),
                    "request_no": a.request_no,
                    "gate_code": a.gate_code,
                    "status": a.status,
                    "current_step": a.current_step,
                    "requested_at": a.requested_at.isoformat() if a.requested_at else None,
                    "completed_at": a.completed_at.isoformat() if a.completed_at else None,
                    "steps": [
                        {
                            "step_no": s.step_no,
                            "mode": s.mode,
                            "approver_role": s.approver_role,
                            "status": s.status,
                            "sla_due_at": s.sla_due_at.isoformat() if s.sla_due_at else None,
                            "assignments": [
                                {
                                    "assignment_key": item.assignment_key,
                                    "approver_role": item.approver_role,
                                    "approver_id": item.approver_id,
                                    "status": item.status,
                                }
                                for item in s.assignments
                            ],
                        }
                        for s in a.steps
                    ],
                }
                for a in approvals
            ],
            "todos": [
                {
                    "id": str(t.id),
                    "todo_no": t.todo_no,
                    "type": t.type,
                    "severity": t.severity,
                    "title": t.title,
                    "status": t.status,
                    "due_at": t.due_at.isoformat() if t.due_at else None,
                }
                for t in todos
            ],
            "contacts": [
                {
                    "id": str(contact.id),
                    "name": contact.name,
                    "title": contact.title,
                    "role": link.role or contact.role,
                    "influence": contact.influence,
                    "stance": contact.stance,
                    "is_primary": link.is_primary,
                    "phone": contact.phone,
                }
                for contact, link in contacts
            ],
            "next_stage": STAGES[STAGES.index(opp.stage) + 1] if opp.stage != "S9" else None,
            "next_stage_label": STAGE_LABELS[STAGES[STAGES.index(opp.stage) + 1]] if opp.stage != "S9" else None,
        }
    )
    return base


@router.get("")
async def list_opportunities(
    keyword: str | None = None,
    stage: str | None = None,
    status: str | None = None,
    owner_id: str | None = None,
    region_code: str | None = None,
    product_line: str | None = None,
    overdue: bool | None = None,
    duplicates_only: bool = False,
    sort: str = "updated_desc",
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    identity: Identity = Depends(require_sales_permission("sales.opportunity.read")),
    db: AsyncSession = Depends(get_db),
):
    conditions = [scope_condition(identity, Opportunity)]
    if stage:
        conditions.append(Opportunity.stage == stage)
    if status:
        conditions.append(Opportunity.status == status)
    if owner_id:
        conditions.append(Opportunity.owner_id == owner_id)
    if region_code:
        conditions.append(Opportunity.region_code == region_code)
    if product_line:
        conditions.append(Opportunity.product_line == product_line)
    if overdue:
        conditions.append(and_(Opportunity.stage_due_at < utc_now(), Opportunity.status == "active"))
    if keyword:
        pattern = f"%{keyword.strip()}%"
        conditions.append(or_(Opportunity.name.ilike(pattern), Opportunity.opportunity_no.ilike(pattern)))
    if duplicates_only:
        sub = select(OpportunityDuplicate.opportunity_id).where(OpportunityDuplicate.status == "pending")
        conditions.append(Opportunity.id.in_(sub))

    total = int((await db.execute(select(func.count(Opportunity.id)).where(*conditions))).scalar_one())
    order = {
        "amount_desc": Opportunity.amount.desc(),
        "amount_asc": Opportunity.amount.asc(),
        "close_asc": Opportunity.expected_close_date.asc(),
        "stage_asc": Opportunity.stage.asc(),
        "updated_desc": Opportunity.updated_at.desc(),
        "created_desc": Opportunity.created_at.desc(),
    }.get(sort, Opportunity.updated_at.desc())
    rows = list((await db.execute(select(Opportunity).where(*conditions).order_by(order).offset(skip).limit(limit))).scalars())
    items = await serialize_opportunities(db, rows)

    stage_counts = {}
    for s in STAGES:
        stage_counts[s] = int((await db.execute(select(func.count(Opportunity.id)).where(*conditions, Opportunity.stage == s))).scalar_one())

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "stage_counts": stage_counts,
        "stages": [{"stage": s, "label": STAGE_LABELS[s], "count": stage_counts[s]} for s in STAGES],
    }


@router.post("", status_code=201)
async def create_opportunity(
    body: OpportunityCreate,
    identity: Identity = Depends(require_sales_permission("sales.opportunity.create")),
    db: AsyncSession = Depends(get_db),
):
    customer = await db.get(Customer, body.customer_id)
    if customer is None:
        raise not_found("客户不存在", "SALES-404-CUSTOMER")
    if identity.data_scope == "region" and customer.region_code != identity.region_code:
        raise forbidden("不能跨区域创建商机", "SALES-403-REGION")
    if identity.data_scope == "self" and body.region_code and body.region_code != identity.region_code:
        raise forbidden("不能为其他区域创建商机", "SALES-403-REGION")

    if body.mine_id and await db.get(Mine, body.mine_id) is None:
        raise not_found("矿井不存在", "SALES-404-MINE")
    if body.workface_id and await db.get(Workface, body.workface_id) is None:
        raise not_found("工作面不存在", "SALES-404-WORKFACE")

    region = body.region_code or customer.region_code or identity.region_code
    if identity.data_scope != "all":
        region = identity.region_code
    owner = body.owner_id or identity.user_id
    if identity.data_scope == "self" and owner != identity.user_id:
        raise forbidden("客户经理只能创建自己的商机", "SALES-403-OWNER")

    period = utc_now().strftime("%Y%m")
    opp = Opportunity(
        opportunity_no=await next_number(db, "OPP", period),
        name=body.name,
        customer_id=body.customer_id,
        mine_id=body.mine_id,
        workface_id=body.workface_id,
        product_line=body.product_line,
        amount=body.amount,
        currency=body.currency,
        stage="S1",
        status="active",
        stage_entered_at=utc_now(),
        stage_due_at=stage_due_for("S1"),
        expected_close_date=body.expected_close_date,
        owner_id=owner,
        owner_org_id=body.owner_org_id or identity.dept_id,
        region_code=region,
        source=body.source,
        source_id=body.source_id,
        rule_probability=Decimal(str(STAGE_BASE_PROBABILITY["S1"])),
        effective_probability=Decimal(str(STAGE_BASE_PROBABILITY["S1"])),
        probability_source="rule",
        created_by=identity.user_id,
        updated_by=identity.user_id,
    )
    db.add(opp)
    await db.flush()
    for contact_id in body.contact_ids:
        contact = await db.get(Contact, contact_id)
        if contact and contact.customer_id == body.customer_id:
            db.add(OpportunityContact(opportunity_id=opp.id, contact_id=contact_id))
    db.add(
        OpportunityStageHistory(
            opportunity_id=opp.id,
            from_stage=None,
            to_stage="S1",
            action="create",
            reason="新建商机",
            operator_id=identity.user_id,
        )
    )
    await refresh_probability(db, opp, actor_id=identity.user_id)
    duplicate = await detect_duplicate(db, opp)
    duplicate_case = await create_duplicate_case(db, opp, duplicate, identity.user_id) if duplicate else None
    add_audit(
        db,
        actor_id=identity.user_id,
        action="opportunity.create",
        object_type="opportunity",
        object_id=str(opp.id),
        after={"opportunity_no": opp.opportunity_no, "name": opp.name, "duplicate": bool(duplicate)},
    )
    await db.flush()
    result = await _detail(db, opp)
    if duplicate_case:
        result["duplicate_case"] = {"id": str(duplicate_case.id), "status": duplicate_case.status}
    return result


@router.get("/funnel")
async def opportunity_funnel(
    identity: Identity = Depends(require_sales_permission("sales.opportunity.read")),
    db: AsyncSession = Depends(get_db),
):
    rows = list((await db.execute(select(Opportunity).where(scope_condition(identity, Opportunity)))).scalars())
    return {"stages": funnel_stage_rows(rows)}


@router.get("/forecast")
async def opportunity_forecast(
    identity: Identity = Depends(require_sales_permission("sales.opportunity.read")),
    db: AsyncSession = Depends(get_db),
):
    rows = list(
        (
            await db.execute(
                select(Opportunity).where(
                    scope_condition(identity, Opportunity),
                    Opportunity.status == "active",
                    Opportunity.forecast_excluded.is_(False),
                )
            )
        ).scalars()
    )
    by_stage = {}
    by_region = {}
    by_product = {}
    for o in rows:
        weighted = float(o.amount) * float(o.effective_probability) / 100
        by_stage[o.stage] = by_stage.get(o.stage, 0) + weighted
        by_region[o.region_code] = by_region.get(o.region_code, 0) + weighted
        by_product[o.product_line] = by_product.get(o.product_line, 0) + weighted
    return {
        "total_weighted": round(sum(by_stage.values()), 2),
        "total_amount": round(sum(float(o.amount) for o in rows), 2),
        "by_stage": [{"stage": s, "label": STAGE_LABELS[s], "weighted": round(by_stage.get(s, 0), 2)} for s in STAGES if by_stage.get(s)],
        "by_region": [{"region_code": k, "weighted": round(v, 2)} for k, v in sorted(by_region.items(), key=lambda x: -x[1])],
        "by_product": [{"product_line": k, "weighted": round(v, 2)} for k, v in sorted(by_product.items(), key=lambda x: -x[1])],
    }


@router.get("/export")
async def export_opportunities(
    identity: Identity = Depends(require_sales_permission("sales.opportunity.export")),
    db: AsyncSession = Depends(get_db),
):
    rows = list((await db.execute(select(Opportunity).where(scope_condition(identity, Opportunity)).order_by(Opportunity.updated_at.desc()))).scalars())
    items = await serialize_opportunities(db, rows)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["商机编号", "商机名称", "客户", "产品线", "金额", "阶段", "状态", "负责人", "区域", "规则概率", "有效概率", "预计成交", "阶段到期"])
    for item in items:
        writer.writerow(
            [
                item["opportunity_no"],
                item["name"],
                item["customer_name"] or "",
                item["product_line"],
                item["amount"],
                item["stage_label"],
                item["status"],
                item["owner_name"] or item["owner_id"],
                item["region_code"],
                item["rule_probability"],
                item["effective_probability"],
                item["expected_close_date"] or "",
                item["stage_due_at"] or "",
            ]
        )
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=opportunities.csv"},
    )


@router.get("/{opportunity_id}")
async def get_opportunity(
    opportunity_id: uuid.UUID,
    identity: Identity = Depends(require_sales_permission("sales.opportunity.read")),
    db: AsyncSession = Depends(get_db),
):
    opp = await _load(db, opportunity_id)
    require_opportunity_access(identity, opp)
    return await _detail(db, opp)


@router.patch("/{opportunity_id}")
async def update_opportunity(
    opportunity_id: uuid.UUID,
    body: OpportunityUpdate,
    identity: Identity = Depends(require_sales_permission("sales.opportunity.update")),
    db: AsyncSession = Depends(get_db),
):
    opp = await _load(db, opportunity_id, lock=True)
    require_opportunity_access(identity, opp)
    if opp.version != body.version:
        raise conflict("商机已被其他用户更新，请刷新后重试", "SALES-409-VERSION_CONFLICT")
    before = {"name": opp.name, "amount": float(opp.amount), "stage": opp.stage}
    updates = body.model_dump(exclude_unset=True, exclude={"version", "contact_ids"})
    for key, value in updates.items():
        if value is not None:
            setattr(opp, key, value)
    if body.contact_ids is not None:
        existing = list((await db.execute(select(OpportunityContact).where(OpportunityContact.opportunity_id == opp.id))).scalars())
        for link in existing:
            await db.delete(link)
        for contact_id in body.contact_ids:
            contact = await db.get(Contact, contact_id)
            if contact and contact.customer_id == opp.customer_id:
                db.add(OpportunityContact(opportunity_id=opp.id, contact_id=contact_id))
    opp.version += 1
    opp.updated_by = identity.user_id
    duplicate = await detect_duplicate(db, opp)
    if duplicate:
        await create_duplicate_case(db, opp, duplicate, identity.user_id)
    add_audit(
        db,
        actor_id=identity.user_id,
        action="opportunity.update",
        object_type="opportunity",
        object_id=str(opp.id),
        before=before,
        after={"name": opp.name, "amount": float(opp.amount), "stage": opp.stage},
    )
    await db.flush()
    return await _detail(db, opp)


@router.post("/{opportunity_id}/transition")
async def transition(
    opportunity_id: uuid.UUID,
    body: TransitionIn,
    identity: Identity = Depends(require_sales_permission("sales.opportunity.transition")),
    db: AsyncSession = Depends(get_db),
):
    opp = await _load(db, opportunity_id, lock=True)
    require_opportunity_access(identity, opp)
    updated, gates = await transition_opportunity(
        db,
        opp,
        to_stage=body.to_stage,
        expected_version=body.expected_version,
        actor_id=identity.user_id,
        reason=body.reason,
        result=body.result,
        lost_reason_code=body.lost_reason_code,
        lost_reason_note=body.lost_reason_note,
        contract_no=body.contract_no,
        contract_amount=body.contract_amount,
        contract_effective_date=body.contract_effective_date,
    )
    blocked = [g for g in gates if g["status"] == "block"]
    if blocked:
        await db.commit()
        raise unprocessable(
            "阶段闸门未通过",
            "SALES-422-GATE_BLOCKED",
            {"gates": gates, "blocked": blocked, "stage": body.to_stage},
        )
    result = await _detail(db, updated)
    result["gates"] = gates
    return result


@router.post("/{opportunity_id}/rollback")
async def rollback(
    opportunity_id: uuid.UUID,
    body: RollbackIn,
    identity: Identity = Depends(require_sales_permission("sales.opportunity.rollback")),
    db: AsyncSession = Depends(get_db),
):
    opp = await _load(db, opportunity_id, lock=True)
    require_opportunity_access(identity, opp)
    updated = await rollback_opportunity(
        db,
        opp,
        to_stage=body.to_stage,
        expected_version=body.expected_version,
        actor_id=identity.user_id,
        reason=body.reason,
        impact=body.impact,
        remedy=body.remedy,
    )
    return await _detail(db, updated)


@router.post("/{opportunity_id}/probability")
async def update_probability(
    opportunity_id: uuid.UUID,
    body: ProbabilityIn,
    identity: Identity = Depends(require_sales_permission("sales.opportunity.probability_override")),
    db: AsyncSession = Depends(get_db),
):
    opp = await _load(db, opportunity_id, lock=True)
    require_opportunity_access(identity, opp)
    if opp.version != body.expected_version:
        raise conflict("商机已被其他用户更新，请刷新后重试", "SALES-409-VERSION_CONFLICT")
    before = {"effective_probability": float(opp.effective_probability), "source": opp.probability_source}
    await refresh_probability(db, opp, actor_id=identity.user_id, manual=body.manual_probability, reason=body.reason)
    opp.version += 1
    opp.updated_by = identity.user_id
    add_audit(
        db,
        actor_id=identity.user_id,
        action="opportunity.probability",
        object_type="opportunity",
        object_id=str(opp.id),
        before=before,
        after={"effective_probability": float(opp.effective_probability), "source": opp.probability_source, "reason": body.reason},
    )
    await db.flush()
    return await _detail(db, opp)


@router.get("/{opportunity_id}/timeline")
async def timeline(
    opportunity_id: uuid.UUID,
    identity: Identity = Depends(require_sales_permission("sales.opportunity.read")),
    db: AsyncSession = Depends(get_db),
):
    opp = await _load(db, opportunity_id)
    require_opportunity_access(identity, opp)
    history = list((await db.execute(select(OpportunityStageHistory).where(OpportunityStageHistory.opportunity_id == opp.id))).scalars())
    probabilities = list((await db.execute(select(OpportunityProbabilityHistory).where(OpportunityProbabilityHistory.opportunity_id == opp.id))).scalars())
    events = [
        {
            "kind": "stage",
            "at": h.created_at.isoformat() if h.created_at else None,
            "title": f"{h.from_stage or '新建'} → {h.to_stage}",
            "detail": h.reason,
            "actor": h.operator_id,
        }
        for h in history
    ]
    events += [
        {
            "kind": "probability",
            "at": p.created_at.isoformat() if p.created_at else None,
            "title": f"概率 {float(p.effective_probability):.0f}%",
            "detail": p.manual_reason,
            "actor": p.changed_by,
        }
        for p in probabilities
    ]
    return {"items": sorted(events, key=lambda x: x["at"] or "", reverse=True)}


@router.get("/{opportunity_id}/duplicates")
async def list_duplicates(
    opportunity_id: uuid.UUID,
    identity: Identity = Depends(require_sales_permission("sales.opportunity.read")),
    db: AsyncSession = Depends(get_db),
):
    opp = await _load(db, opportunity_id)
    require_opportunity_access(identity, opp)
    rows = list((await db.execute(select(OpportunityDuplicate).where(or_(OpportunityDuplicate.opportunity_id == opp.id, OpportunityDuplicate.duplicate_opportunity_id == opp.id)))).scalars())
    return {
        "items": [
            {
                "id": str(d.id),
                "opportunity_id": str(d.opportunity_id),
                "duplicate_opportunity_id": str(d.duplicate_opportunity_id),
                "status": d.status,
                "match_keys": d.match_keys,
                "resolution": d.resolution,
                "reason": d.reason,
            }
            for d in rows
        ]
    }


@router.post("/duplicates/{case_id}/resolve")
async def resolve_duplicate(
    case_id: uuid.UUID,
    payload: dict[str, Any] = Body(...),
    identity: Identity = Depends(require_sales_permission("sales.opportunity.duplicate_resolve")),
    db: AsyncSession = Depends(get_db),
):
    case = await db.get(OpportunityDuplicate, case_id)
    if case is None:
        raise not_found("撞单案件不存在", "SALES-404-DUPLICATE")
    primary = payload.get("primary_opportunity_id")
    updated = await resolve_duplicate_case(
        db,
        case,
        resolution=str(payload.get("resolution") or "not_duplicate"),
        reason=str(payload.get("reason") or ""),
        actor_id=identity.user_id,
        primary_opportunity_id=uuid.UUID(primary) if primary else None,
    )
    return {"id": str(updated.id), "status": updated.status, "resolution": updated.resolution}
