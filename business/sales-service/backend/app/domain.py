"""Domain logic: stage machine, rules, probability, todos and audit."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    SEVERITY_SLA_HOURS,
    STAGE_BASE_PROBABILITY,
    STAGE_LABELS,
    STAGE_REQUIRED_FIELDS,
    STAGE_SLA_DAYS,
    STAGES,
)
from app.errors import bad_request, conflict, unprocessable
from app.models import (
    ApprovalRequest,
    AuditEvent,
    Customer,
    CustomerGroup,
    LostReasonCode,
    Opportunity,
    OpportunityDuplicate,
    OpportunityGateCheck,
    OpportunityProbabilityHistory,
    OpportunityStageHistory,
    PilotProject,
    QuoteConflict,
    RuleConfig,
    Todo,
    TodoEvent,
    UserProfile,
    Workface,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


async def next_number(db: AsyncSession, prefix: str, period: str) -> str:
    statement = text(
        """
        INSERT INTO number_sequences(prefix, period, next_value)
        VALUES (:prefix, :period, 2)
        ON CONFLICT (prefix, period)
        DO UPDATE SET next_value = number_sequences.next_value + 1
        RETURNING next_value - 1 AS value
        """
    )
    value = (await db.execute(statement, {"prefix": prefix, "period": period})).scalar_one()
    return f"{prefix}{period}{int(value):05d}"


async def get_rule(db: AsyncSession, code: str) -> dict[str, Any]:
    row = (await db.execute(select(RuleConfig).where(RuleConfig.rule_code == code, RuleConfig.enabled.is_(True), RuleConfig.effective_to.is_(None)).order_by(RuleConfig.version.desc()).limit(1))).scalar_one_or_none()
    return row.config_json if row else {}


async def probability_config(db: AsyncSession) -> dict[str, Any]:
    cfg = await get_rule(db, "PROBABILITY_MODEL")
    return {
        "base": {**STAGE_BASE_PROBABILITY, **(cfg.get("base") or {})},
        "overdue_penalty_pp": int(cfg.get("overdue_penalty_pp", 15)),
        "max_penalty_pp": int(cfg.get("max_penalty_pp", 20)),
        "floor": int(cfg.get("floor", 5)),
        "manual_override_threshold_pp": int(cfg.get("manual_override_threshold_pp", 15)),
    }


def compute_rule_probability(stage: str, stage_due_at: datetime | None, cfg: dict[str, Any], now: datetime | None = None) -> Decimal:
    now = now or utc_now()
    base = int(cfg["base"].get(stage, 0))
    penalty = 0
    if stage_due_at is not None:
        due = stage_due_at if stage_due_at.tzinfo else stage_due_at.replace(tzinfo=UTC)
        if due < now:
            penalty = min(int(cfg["max_penalty_pp"]), int(cfg["overdue_penalty_pp"]))
    return Decimal(str(max(int(cfg["floor"]), base - penalty)))


def stage_requirements(stage: str, cfg: dict[str, Any] | None = None) -> tuple[str, ...]:
    if cfg and cfg.get("required") and stage in cfg["required"]:
        return tuple(cfg["required"][stage])
    return STAGE_REQUIRED_FIELDS.get(stage, ())


def _missing_fields(opportunity: Opportunity, stage: str, cfg: dict[str, Any] | None = None) -> list[str]:
    missing: list[str] = []
    for field_name in stage_requirements(stage, cfg):
        value = getattr(opportunity, field_name, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field_name)
    return missing


async def approved_gate(db: AsyncSession, opportunity_id: uuid.UUID, gate_code: str) -> ApprovalRequest | None:
    return (
        await db.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.opportunity_id == opportunity_id,
                ApprovalRequest.gate_code == gate_code,
                ApprovalRequest.status == "approved",
            )
            .order_by(ApprovalRequest.completed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def evaluate_gates(
    db: AsyncSession,
    opportunity: Opportunity,
    to_stage: str,
    *,
    result: str | None = None,
    lost_reason_code: str | None = None,
    lost_reason_note: str | None = None,
) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    stage_cfg = await get_rule(db, "STAGE_FIELDS")
    missing = _missing_fields(opportunity, to_stage, stage_cfg)
    if missing:
        gates.append(
            {
                "gate_code": "STAGE_FIELDS",
                "status": "block",
                "message": f"推进到 {STAGE_LABELS.get(to_stage, to_stage)} 缺少字段",
                "evidence": {"missing": missing},
                "action": "complete_fields",
            }
        )
    else:
        gates.append(
            {
                "gate_code": "STAGE_FIELDS",
                "status": "pass",
                "message": "阶段必填字段完整",
                "evidence": {"required": list(stage_requirements(to_stage, stage_cfg))},
                "action": None,
            }
        )

    from_stage = opportunity.stage
    if from_stage == "S4" and to_stage == "S5":
        customer = await db.get(Customer, opportunity.customer_id)
        group = await db.get(CustomerGroup, customer.group_id) if customer and customer.group_id else None
        pilot_count = 0
        if group:
            pilot_count = int((await db.execute(select(func.count(PilotProject.id)).where(PilotProject.customer_group_id == group.id))).scalar_one())
        if group and group.is_new_customer and pilot_count == 0:
            approval = await approved_gate(db, opportunity.id, "R4")
            if approval:
                gates.append(
                    {
                        "gate_code": "R4",
                        "status": "pass",
                        "message": "新客户无示范面，已取得 R4 例外审批",
                        "evidence": {"approval_request_id": str(approval.id), "template": "R4_EXCEPTION", "pilot_count": 0},
                        "action": None,
                    }
                )
            else:
                gates.append(
                    {
                        "gate_code": "R4",
                        "status": "block",
                        "message": "新客户推进到投标立项前，需关联示范面或完成 R4 例外审批",
                        "evidence": {"template": "R4_EXCEPTION", "pilot_count": 0, "customer_group_id": str(group.id)},
                        "action": "link_pilot_project_or_request_exception",
                    }
                )
        else:
            gates.append(
                {
                    "gate_code": "R4",
                    "status": "pass",
                    "message": "示范面要求满足",
                    "evidence": {"pilot_count": pilot_count, "is_new_customer": bool(group and group.is_new_customer)},
                    "action": None,
                }
            )

    if from_stage == "S5" and to_stage == "S6":
        pending = int(
            (
                await db.execute(
                    select(func.count(QuoteConflict.id)).where(
                        QuoteConflict.opportunity_id == opportunity.id,
                        QuoteConflict.status == "pending",
                    )
                )
            ).scalar_one()
        )
        if pending:
            gates.append(
                {
                    "gate_code": "R2",
                    "status": "block",
                    "message": "存在未解决的报价冲突，不能进入报价审批",
                    "evidence": {"pending_conflicts": pending},
                    "action": "resolve_quote_conflict",
                }
            )
        else:
            gates.append(
                {
                    "gate_code": "R2",
                    "status": "pass",
                    "message": "无未解决报价冲突",
                    "evidence": {"pending_conflicts": 0},
                    "action": None,
                }
            )

    if from_stage == "S6" and to_stage == "S7":
        customer = await db.get(Customer, opportunity.customer_id)
        related = customer.related_party_status if customer else "unknown"
        if related == "unknown":
            gates.append(
                {
                    "gate_code": "R6",
                    "status": "block",
                    "message": "客户关联方状态未知，需先补全客户主数据",
                    "evidence": {"related_party_status": related},
                    "action": "fix_customer_related_party",
                }
            )
        elif related == "yes":
            approval = await approved_gate(db, opportunity.id, "R6")
            if approval:
                gates.append(
                    {
                        "gate_code": "R6",
                        "status": "pass",
                        "message": "关联方交易已完成 R6 审批",
                        "evidence": {"approval_request_id": str(approval.id), "template": "R6_RELATED_PARTY"},
                        "action": None,
                    }
                )
            else:
                gates.append(
                    {
                        "gate_code": "R6",
                        "status": "block",
                        "message": "关联方交易进入投标前需完成 R6 合规审批",
                        "evidence": {"template": "R6_RELATED_PARTY", "related_party_status": related},
                        "action": "request_related_party_approval",
                    }
                )
        else:
            gates.append(
                {
                    "gate_code": "R6",
                    "status": "pass",
                    "message": "客户非关联方",
                    "evidence": {"related_party_status": related},
                    "action": None,
                }
            )

    if to_stage == "S8":
        if result not in {"won", "lost"}:
            gates.append(
                {
                    "gate_code": "R9",
                    "status": "block",
                    "message": "进入中标/失标阶段必须填写结果",
                    "evidence": {},
                    "action": "set_result",
                }
            )
        elif result == "lost":
            if not lost_reason_code:
                gates.append(
                    {
                        "gate_code": "R9",
                        "status": "block",
                        "message": "失标必须填写失标原因",
                        "evidence": {"lost_reason_code": None},
                        "action": "set_lost_reason",
                    }
                )
            else:
                reason = await db.get(LostReasonCode, lost_reason_code)
                if reason is None or not reason.is_active:
                    gates.append(
                        {
                            "gate_code": "R9",
                            "status": "block",
                            "message": "无效的失标原因",
                            "evidence": {"lost_reason_code": lost_reason_code},
                            "action": "set_lost_reason",
                        }
                    )
                elif reason.requires_note and not (lost_reason_note or "").strip():
                    gates.append(
                        {
                            "gate_code": "R9",
                            "status": "block",
                            "message": "该失标原因需要填写说明",
                            "evidence": {"lost_reason_code": lost_reason_code},
                            "action": "set_lost_reason",
                        }
                    )
                else:
                    gates.append(
                        {
                            "gate_code": "R9",
                            "status": "pass",
                            "message": "失标原因完整",
                            "evidence": {"lost_reason_code": lost_reason_code},
                            "action": None,
                        }
                    )
        else:
            gates.append(
                {
                    "gate_code": "R9",
                    "status": "pass",
                    "message": "中标结果已记录",
                    "evidence": {"result": result},
                    "action": None,
                }
            )

    if to_stage == "S9" and opportunity.result != "won":
        gates.append(
            {
                "gate_code": "S9_CONTRACT",
                "status": "block",
                "message": "只有中标商机才能进入合同生效",
                "evidence": {"result": opportunity.result},
                "action": "set_result",
            }
        )

    return gates


def gates_blocked(gates: list[dict[str, Any]]) -> bool:
    return any(g["status"] == "block" for g in gates)


async def record_gate_checks(
    db: AsyncSession,
    opportunity_id: uuid.UUID,
    gates: list[dict[str, Any]],
    actor_id: str,
    rule_version: int | None = None,
) -> None:
    for gate in gates:
        db.add(
            OpportunityGateCheck(
                opportunity_id=opportunity_id,
                gate_code=gate["gate_code"],
                status=gate["status"],
                message=gate["message"],
                evidence_json=gate.get("evidence") or {},
                rule_version=rule_version,
                checked_by=actor_id,
            )
        )


def apply_probability(opportunity: Opportunity, rule_probability: Decimal, manual: Decimal | None, reason: str | None) -> None:
    opportunity.rule_probability = rule_probability
    opportunity.manual_probability = manual
    if manual is not None:
        opportunity.manual_reason = reason
        opportunity.probability_source = "manual"
        opportunity.effective_probability = manual
    else:
        opportunity.manual_reason = None
        opportunity.probability_source = "rule"
        opportunity.effective_probability = rule_probability


async def refresh_probability(
    db: AsyncSession,
    opportunity: Opportunity,
    *,
    actor_id: str | None = None,
    manual: Decimal | None = None,
    reason: str | None = None,
) -> None:
    cfg = await probability_config(db)
    rule = compute_rule_probability(opportunity.stage, opportunity.stage_due_at, cfg)
    if manual is not None:
        deviation = abs(float(manual) - float(rule))
        if deviation > float(cfg["manual_override_threshold_pp"]) and not (reason or "").strip():
            raise unprocessable(
                "人工概率偏离规则概率超过阈值，必须填写原因",
                "SALES-422-PROBABILITY_REASON_REQUIRED",
                {"rule_probability": float(rule), "manual_probability": float(manual), "threshold_pp": cfg["manual_override_threshold_pp"]},
            )
    apply_probability(opportunity, rule, manual, reason)
    db.add(
        OpportunityProbabilityHistory(
            opportunity_id=opportunity.id,
            rule_probability=rule,
            manual_probability=manual,
            manual_reason=reason,
            effective_probability=opportunity.effective_probability,
            changed_by=actor_id,
        )
    )


def stage_due_for(stage: str, now: datetime | None = None) -> datetime | None:
    days = STAGE_SLA_DAYS.get(stage)
    if not days:
        return None
    return (now or utc_now()) + timedelta(days=days)


def can_advance(from_stage: str, to_stage: str) -> bool:
    """QW2 only permits adjacent stage advances; rollback is a separate action."""
    if from_stage not in STAGES or to_stage not in STAGES:
        return False
    return STAGES.index(to_stage) == STAGES.index(from_stage) + 1


async def transition_opportunity(
    db: AsyncSession,
    opportunity: Opportunity,
    *,
    to_stage: str,
    expected_version: int,
    actor_id: str,
    reason: str | None = None,
    result: str | None = None,
    lost_reason_code: str | None = None,
    lost_reason_note: str | None = None,
    contract_no: str | None = None,
    contract_amount: Decimal | None = None,
    contract_effective_date: date | None = None,
) -> tuple[Opportunity, list[dict[str, Any]]]:
    if opportunity.version != expected_version:
        raise conflict("商机已被其他用户更新，请刷新后重试", "SALES-409-VERSION_CONFLICT")
    if opportunity.status != "active":
        raise conflict("只有进行中的商机可以推进", "SALES-409-NOT_ACTIVE")
    if to_stage not in STAGES:
        raise bad_request("未知阶段", "SALES-400-STAGE")
    if not can_advance(opportunity.stage, to_stage):
        raise bad_request("只能推进到相邻阶段；跨阶段请先按阶段要求完成", "SALES-400-NON_ADJACENT")

    if to_stage == "S8":
        opportunity.result = result
        opportunity.lost_reason_code = lost_reason_code
        opportunity.lost_reason_note = lost_reason_note
    if to_stage == "S9":
        opportunity.contract_no = contract_no
        opportunity.contract_amount = contract_amount
        opportunity.contract_effective_date = contract_effective_date

    gates = await evaluate_gates(
        db,
        opportunity,
        to_stage,
        result=result,
        lost_reason_code=lost_reason_code,
        lost_reason_note=lost_reason_note,
    )
    await record_gate_checks(db, opportunity.id, gates, actor_id)
    if gates_blocked(gates):
        if to_stage == "S8":
            opportunity.result = None
            opportunity.lost_reason_code = None
            opportunity.lost_reason_note = None
        if to_stage == "S9":
            opportunity.contract_no = None
            opportunity.contract_amount = None
            opportunity.contract_effective_date = None
        await db.flush()
        return opportunity, gates

    from_stage = opportunity.stage
    now = utc_now()
    opportunity.stage = to_stage
    opportunity.stage_entered_at = now
    opportunity.stage_due_at = stage_due_for(to_stage, now)
    opportunity.version += 1
    opportunity.updated_by = actor_id
    if to_stage == "S9":
        opportunity.status = "won"
        opportunity.forecast_excluded = True
    elif to_stage == "S8" and result == "lost":
        opportunity.status = "lost"
        opportunity.forecast_excluded = True
    else:
        opportunity.status = "active"
        opportunity.forecast_excluded = False

    db.add(
        OpportunityStageHistory(
            opportunity_id=opportunity.id,
            from_stage=from_stage,
            to_stage=to_stage,
            action="advance",
            reason=reason,
            operator_id=actor_id,
        )
    )
    await refresh_probability(db, opportunity, actor_id=actor_id)
    add_audit(
        db,
        actor_id=actor_id,
        action="opportunity.transition",
        object_type="opportunity",
        object_id=str(opportunity.id),
        before={"stage": from_stage},
        after={"stage": to_stage, "result": result},
    )
    await db.flush()
    return opportunity, gates


async def rollback_opportunity(
    db: AsyncSession,
    opportunity: Opportunity,
    *,
    to_stage: str,
    expected_version: int,
    actor_id: str,
    reason: str,
    impact: str,
    remedy: str,
) -> Opportunity:
    if opportunity.version != expected_version:
        raise conflict("商机已被其他用户更新，请刷新后重试", "SALES-409-VERSION_CONFLICT")
    if to_stage not in STAGES or STAGES.index(to_stage) >= STAGES.index(opportunity.stage):
        raise bad_request("只能回退到更早阶段", "SALES-400-ROLLBACK_TARGET")
    from_stage = opportunity.stage
    opportunity.stage = to_stage
    opportunity.stage_entered_at = utc_now()
    opportunity.stage_due_at = stage_due_for(to_stage)
    opportunity.status = "active"
    opportunity.result = None
    opportunity.forecast_excluded = False
    if to_stage != "S9":
        opportunity.contract_no = None
        opportunity.contract_amount = None
        opportunity.contract_effective_date = None
    opportunity.version += 1
    opportunity.updated_by = actor_id
    db.add(
        OpportunityStageHistory(
            opportunity_id=opportunity.id,
            from_stage=from_stage,
            to_stage=to_stage,
            action="rollback",
            reason=reason,
            impact=impact,
            remedy=remedy,
            operator_id=actor_id,
        )
    )
    await refresh_probability(db, opportunity, actor_id=actor_id)
    add_audit(
        db,
        actor_id=actor_id,
        action="opportunity.rollback",
        object_type="opportunity",
        object_id=str(opportunity.id),
        before={"stage": from_stage},
        after={"stage": to_stage, "reason": reason, "impact": impact, "remedy": remedy},
    )
    await db.flush()
    return opportunity


async def detect_duplicate(db: AsyncSession, opportunity: Opportunity) -> Opportunity | None:
    if not opportunity.workface_id:
        return None
    stmt = select(Opportunity).where(
        Opportunity.id != opportunity.id,
        Opportunity.customer_id == opportunity.customer_id,
        Opportunity.workface_id == opportunity.workface_id,
        Opportunity.product_line == opportunity.product_line,
        Opportunity.status == "active",
    )
    return (await db.execute(stmt.order_by(Opportunity.created_at.asc()).limit(1))).scalar_one_or_none()


async def create_duplicate_case(
    db: AsyncSession,
    opportunity: Opportunity,
    duplicate: Opportunity,
    actor_id: str,
) -> OpportunityDuplicate:
    existing = (
        await db.execute(
            select(OpportunityDuplicate).where(
                OpportunityDuplicate.status == "pending",
                or_(
                    and_(OpportunityDuplicate.opportunity_id == opportunity.id, OpportunityDuplicate.duplicate_opportunity_id == duplicate.id),
                    and_(OpportunityDuplicate.opportunity_id == duplicate.id, OpportunityDuplicate.duplicate_opportunity_id == opportunity.id),
                ),
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    case = OpportunityDuplicate(
        opportunity_id=opportunity.id,
        duplicate_opportunity_id=duplicate.id,
        match_keys={
            "customer_id": str(opportunity.customer_id),
            "workface_id": str(opportunity.workface_id),
            "product_line": opportunity.product_line,
        },
        status="pending",
    )
    db.add(case)
    await db.flush()
    await create_todo(
        db,
        type="arbitration",
        severity="high",
        title=f"疑似撞单：{opportunity.name}",
        description=f"与商机 {duplicate.opportunity_no} 命中同一客户、工作面、产品线。",
        object_type="opportunity",
        object_id=opportunity.id,
        dedupe_key=f"duplicate:{case.id}",
        source_rule="R10",
        assignee_role="regional_manager",
        created_by=actor_id,
    )
    return case


async def resolve_duplicate_case(
    db: AsyncSession,
    case: OpportunityDuplicate,
    *,
    resolution: str,
    reason: str,
    actor_id: str,
    primary_opportunity_id: uuid.UUID | None = None,
) -> OpportunityDuplicate:
    if case.status != "pending":
        raise conflict("撞单案件已处理", "SALES-409-DUPLICATE_CLOSED")
    if resolution not in {"keep_both", "merge", "transfer", "not_duplicate"}:
        raise bad_request("未知撞单处理方式", "SALES-400-DUPLICATE_RESOLUTION")
    case.status = "resolved"
    case.resolution = resolution
    case.reason = reason
    case.resolved_by = actor_id
    case.resolved_at = utc_now()
    if resolution == "merge" and primary_opportunity_id:
        case.primary_opportunity_id = primary_opportunity_id
        loser_id = case.duplicate_opportunity_id if primary_opportunity_id == case.opportunity_id else case.opportunity_id
        loser = await db.get(Opportunity, loser_id)
        if loser:
            loser.duplicate_of_id = primary_opportunity_id
            loser.status = "merged"
            loser.forecast_excluded = True
    await close_todos_for_object(db, "opportunity", case.opportunity_id, actor_id=actor_id, only_types={"arbitration"}, note="撞单已处理")
    add_audit(
        db,
        actor_id=actor_id,
        action="opportunity.duplicate_resolve",
        object_type="opportunity_duplicate",
        object_id=str(case.id),
        after={"resolution": resolution, "reason": reason},
    )
    await db.flush()
    return case


async def create_todo(
    db: AsyncSession,
    *,
    type: str,
    severity: str,
    title: str,
    description: str | None,
    object_type: str,
    object_id: uuid.UUID,
    dedupe_key: str,
    source_rule: str | None = None,
    assignee_id: str | None = None,
    assignee_role: str | None = None,
    created_by: str | None = None,
    due_hours: int | None = None,
) -> Todo:
    existing = (await db.execute(select(Todo).where(Todo.dedupe_key == dedupe_key, Todo.status.in_(["open", "in_progress"])))).scalar_one_or_none()
    if existing:
        return existing
    severity_cfg = await get_rule(db, "TODO_SLA")
    hours = due_hours if due_hours is not None else int((severity_cfg.get("hours") or {}).get(severity, SEVERITY_SLA_HOURS[severity]))
    period = utc_now().strftime("%Y%m%d")
    todo = Todo(
        todo_no=await next_number(db, "TD", period),
        type=type,
        severity=severity,
        title=title,
        description=description,
        object_type=object_type,
        object_id=object_id,
        source_rule=source_rule,
        assignee_id=assignee_id,
        assignee_role=assignee_role,
        status="open",
        due_at=utc_now() + timedelta(hours=hours),
        sla_minutes=hours * 60,
        dedupe_key=dedupe_key,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(todo)
    await db.flush()
    db.add(TodoEvent(todo_id=todo.id, event_type="created", to_status="open", operator_id=created_by, note=title))
    return todo


async def close_todos_for_object(
    db: AsyncSession,
    object_type: str,
    object_id: uuid.UUID,
    *,
    actor_id: str | None,
    only_types: set[str] | None = None,
    note: str = "关联对象已推进",
) -> int:
    stmt = select(Todo).where(Todo.object_type == object_type, Todo.object_id == object_id, Todo.status.in_(["open", "in_progress"]))
    if only_types:
        stmt = stmt.where(Todo.type.in_(list(only_types)))
    rows = list((await db.execute(stmt)).scalars())
    for todo in rows:
        todo.status = "resolved"
        todo.resolution = note
        todo.resolved_at = utc_now()
        todo.updated_by = actor_id
        db.add(TodoEvent(todo_id=todo.id, event_type="resolved", from_status="open", to_status="resolved", operator_id=actor_id, note=note))
    return len(rows)


def add_audit(
    db: AsyncSession,
    *,
    actor_id: str | None,
    action: str,
    object_type: str,
    object_id: str | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    actor_type: str = "user",
) -> None:
    db.add(
        AuditEvent(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before_json=before,
            after_json=after,
        )
    )


def opportunity_dict(
    opportunity: Opportunity,
    *,
    customer: Customer | None = None,
    owner: UserProfile | None = None,
    customer_group_name: str | None = None,
    workface_name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(opportunity.id),
        "opportunity_no": opportunity.opportunity_no,
        "name": opportunity.name,
        "customer_id": str(opportunity.customer_id),
        "customer_name": customer.name if customer else None,
        "customer_group_name": customer_group_name,
        "mine_id": str(opportunity.mine_id) if opportunity.mine_id else None,
        "workface_id": str(opportunity.workface_id) if opportunity.workface_id else None,
        "workface_name": workface_name,
        "product_line": opportunity.product_line,
        "amount": float(opportunity.amount),
        "currency": opportunity.currency,
        "stage": opportunity.stage,
        "stage_label": STAGE_LABELS.get(opportunity.stage, opportunity.stage),
        "status": opportunity.status,
        "result": opportunity.result,
        "stage_entered_at": opportunity.stage_entered_at.isoformat() if opportunity.stage_entered_at else None,
        "stage_due_at": opportunity.stage_due_at.isoformat() if opportunity.stage_due_at else None,
        "expected_close_date": opportunity.expected_close_date.isoformat() if opportunity.expected_close_date else None,
        "owner_id": opportunity.owner_id,
        "owner_name": owner.display_name if owner else None,
        "owner_org_id": opportunity.owner_org_id,
        "region_code": opportunity.region_code,
        "source": opportunity.source,
        "source_id": opportunity.source_id,
        "rule_probability": float(opportunity.rule_probability),
        "manual_probability": float(opportunity.manual_probability) if opportunity.manual_probability is not None else None,
        "manual_reason": opportunity.manual_reason,
        "effective_probability": float(opportunity.effective_probability),
        "probability_source": opportunity.probability_source,
        "forecast_excluded": opportunity.forecast_excluded,
        "duplicate_of_id": str(opportunity.duplicate_of_id) if opportunity.duplicate_of_id else None,
        "lost_reason_code": opportunity.lost_reason_code,
        "lost_reason_note": opportunity.lost_reason_note,
        "contract_no": opportunity.contract_no,
        "contract_amount": float(opportunity.contract_amount) if opportunity.contract_amount is not None else None,
        "contract_effective_date": opportunity.contract_effective_date.isoformat() if opportunity.contract_effective_date else None,
        "version": opportunity.version,
        "created_at": opportunity.created_at.isoformat() if opportunity.created_at else None,
        "updated_at": opportunity.updated_at.isoformat() if opportunity.updated_at else None,
        "is_overdue": bool(opportunity.stage_due_at and opportunity.stage_due_at < utc_now() and opportunity.status == "active"),
        "weighted_amount": float(Decimal(str(opportunity.amount)) * Decimal(str(opportunity.effective_probability)) / Decimal("100")),
    }


def todo_dict(todo: Todo, opportunity: Opportunity | None = None) -> dict[str, Any]:
    return {
        "id": str(todo.id),
        "todo_no": todo.todo_no,
        "type": todo.type,
        "severity": todo.severity,
        "title": todo.title,
        "description": todo.description,
        "object_type": todo.object_type,
        "object_id": str(todo.object_id),
        "opportunity_name": opportunity.name if opportunity else None,
        "source_rule": todo.source_rule,
        "assignee_id": todo.assignee_id,
        "assignee_role": todo.assignee_role,
        "status": todo.status,
        "due_at": todo.due_at.isoformat() if todo.due_at else None,
        "sla_minutes": todo.sla_minutes,
        "escalation_level": todo.escalation_level,
        "is_overdue": bool(todo.due_at and todo.due_at < utc_now() and todo.status in {"open", "in_progress"}),
        "resolution": todo.resolution,
        "resolved_at": todo.resolved_at.isoformat() if todo.resolved_at else None,
        "created_at": todo.created_at.isoformat() if todo.created_at else None,
        "updated_at": todo.updated_at.isoformat() if todo.updated_at else None,
    }


def approval_dict(request: ApprovalRequest, opportunity: Opportunity | None = None) -> dict[str, Any]:
    return {
        "id": str(request.id),
        "request_no": request.request_no,
        "definition_code": request.definition_code,
        "definition_version": request.definition_version,
        "opportunity_id": str(request.opportunity_id),
        "opportunity_name": opportunity.name if opportunity else None,
        "gate_code": request.gate_code,
        "status": request.status,
        "current_step": request.current_step,
        "reason": request.reason,
        "evidence": request.evidence_json,
        "payload": request.payload_json,
        "requested_by": request.requested_by,
        "requested_at": request.requested_at.isoformat() if request.requested_at else None,
        "started_at": request.started_at.isoformat() if request.started_at else None,
        "completed_at": request.completed_at.isoformat() if request.completed_at else None,
        "expires_at": request.expires_at.isoformat() if request.expires_at else None,
        "failure_reason": request.failure_reason,
        "engine": request.engine,
        "platform_instance_id": request.platform_instance_id,
        "version": request.version,
        "steps": [
            {
                "step_no": step.step_no,
                "mode": step.mode,
                "approver_role": step.approver_role,
                "approver_id": step.approver_id,
                "status": step.status,
                "decision": step.decision,
                "comment": step.comment,
                "sla_due_at": step.sla_due_at.isoformat() if step.sla_due_at else None,
                "decided_at": step.decided_at.isoformat() if step.decided_at else None,
                "escalation_level": step.escalation_level,
                "assignments": [
                    {
                        "assignment_key": assignment.assignment_key,
                        "approver_role": assignment.approver_role,
                        "approver_id": assignment.approver_id,
                        "status": assignment.status,
                        "decision": assignment.decision,
                        "comment": assignment.comment,
                        "decided_at": assignment.decided_at.isoformat() if assignment.decided_at else None,
                        "delegated_from": assignment.delegated_from,
                    }
                    for assignment in step.assignments
                ],
            }
            for step in request.steps
        ],
    }


def funnel_stage_rows(opportunities: list[Opportunity]) -> list[dict[str, Any]]:
    now = utc_now()
    rows = []
    for stage in STAGES:
        subset = [o for o in opportunities if o.stage == stage]
        amount = sum((float(o.amount) for o in subset), 0.0)
        weighted = sum((float(o.amount) * float(o.effective_probability) / 100 for o in subset), 0.0)
        overdue = sum(1 for o in subset if o.stage_due_at and o.stage_due_at < now and o.status == "active")
        rows.append(
            {
                "stage": stage,
                "label": STAGE_LABELS[stage],
                "count": len(subset),
                "amount": round(amount, 2),
                "weighted_amount": round(weighted, 2),
                "overdue": overdue,
            }
        )
    return rows


def format_date(value: datetime | None) -> str:
    return value.strftime("%m-%d %H:%M") if value else "-"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


async def serialize_opportunities(db: AsyncSession, opportunities: list[Opportunity]) -> list[dict[str, Any]]:
    if not opportunities:
        return []
    customer_ids = {o.customer_id for o in opportunities}
    workface_ids = {o.workface_id for o in opportunities if o.workface_id}
    owner_ids = {o.owner_id for o in opportunities if o.owner_id}
    customers = {c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars()}
    workfaces = {w.id: w for w in (await db.execute(select(Workface).where(Workface.id.in_(workface_ids)))).scalars()}
    profiles = {p.id: p for p in (await db.execute(select(UserProfile).where(UserProfile.id.in_(owner_ids)))).scalars()}
    group_ids = {c.group_id for c in customers.values() if c.group_id}
    groups = {g.id: g for g in (await db.execute(select(CustomerGroup).where(CustomerGroup.id.in_(group_ids)))).scalars()} if group_ids else {}
    return [
        opportunity_dict(
            o,
            customer=customers.get(o.customer_id),
            owner=profiles.get(o.owner_id),
            customer_group_name=groups.get(customers[o.customer_id].group_id).name if o.customer_id in customers and customers[o.customer_id].group_id in groups else None,
            workface_name=workfaces[o.workface_id].name if o.workface_id in workfaces else None,
        )
        for o in opportunities
    ]
