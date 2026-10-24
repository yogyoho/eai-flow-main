from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import Identity, require_sales_permission, scope_condition
from app.database import get_db
from app.domain import funnel_stage_rows, serialize_opportunities, todo_dict, utc_now
from app.enums import STAGE_LABELS
from app.models import ApprovalRequest, ApprovalStep, Opportunity, Todo, WorkbenchCardConfig

router = APIRouter(prefix="/workbench", tags=["workbench"])

DEFAULT_CARDS = [
    "today_todos",
    "pending_approvals",
    "blockers",
    "overdue_opportunities",
    "weighted_forecast",
    "funnel_health",
]


def todo_scope(identity: Identity):
    if identity.is_admin or identity.data_scope == "all":
        return true()
    clauses = [
        Todo.assignee_id == identity.user_id,
        Todo.assignee_role == identity.sales_role,
        Todo.assignee_role.is_(None),
    ]
    if identity.data_scope == "region":
        clauses.append(Todo.assignee_role.in_(["regional_manager", "data_steward"]))
    return or_(*clauses)


async def _weighted(opportunities: list[Opportunity]) -> tuple[float, float]:
    active = [o for o in opportunities if o.status == "active" and not o.forecast_excluded]
    amount = sum(float(o.amount) for o in active)
    weighted = sum(float(o.amount) * float(o.effective_probability) / 100 for o in active)
    return amount, weighted


@router.get("/summary")
async def workbench_summary(
    identity: Identity = Depends(require_sales_permission("sales.workbench.read")),
    db: AsyncSession = Depends(get_db),
):
    opps = list((await db.execute(select(Opportunity).where(scope_condition(identity, Opportunity)).order_by(Opportunity.amount.desc()))).scalars())
    active = [o for o in opps if o.status == "active"]
    now = utc_now()
    overdue = [o for o in active if o.stage_due_at and o.stage_due_at < now]

    todos = list((await db.execute(select(Todo).where(todo_scope(identity), Todo.status.in_(["open", "in_progress"])).order_by(Todo.severity.asc(), Todo.due_at.asc()).limit(200))).scalars())
    approval_stmt = select(ApprovalRequest).where(ApprovalRequest.status == "running").options(selectinload(ApprovalRequest.steps))
    if not (identity.is_admin or identity.data_scope == "all"):
        approval_stmt = approval_stmt.where(
            ApprovalRequest.requested_by != identity.user_id,
            ApprovalRequest.steps.any(
                and_(
                    ApprovalStep.status == "active",
                    or_(ApprovalStep.approver_role == identity.sales_role, ApprovalStep.approver_id == identity.user_id),
                )
            ),
        )
    approvals = list((await db.execute(approval_stmt.order_by(ApprovalRequest.requested_at.asc()).limit(100))).scalars())
    pending_approvals = [item for item in approvals if (identity.is_admin or identity.data_scope == "all") or any(s.status == "active" and (s.approver_role == identity.sales_role or s.approver_id == identity.user_id) for s in item.steps)]

    amount, weighted = await _weighted(opps)
    active_amount = sum(float(o.amount) for o in active)
    today_end = datetime.now(UTC).replace(hour=23, minute=59, second=59, microsecond=0)
    today_todos = [t for t in todos if t.due_at is None or t.due_at <= today_end]
    blockers = [t for t in todos if t.severity == "blocker"]

    top_opps = await serialize_opportunities(db, active[:5])
    top_todos = []
    for todo in todos[:6]:
        opp = next((o for o in opps if o.id == todo.object_id), None)
        top_todos.append(todo_dict(todo, opp))

    approved_count = int((await db.execute(select(func.count(ApprovalRequest.id)).where(ApprovalRequest.status == "approved"))).scalar_one())
    brief = [
        {
            "kind": "todo",
            "text": f"今天聚焦 {len(today_todos)} 项待办，其中 {len(blockers)} 项会阻断阶段推进。",
            "link": "/todos",
        },
        {
            "kind": "forecast",
            "text": f"加权预测 ¥{weighted / 10000:.0f} 万，在管金额 ¥{active_amount / 10000:.0f} 万。",
            "link": "/opportunities",
        },
        {
            "kind": "approval",
            "text": f"待我审批 {len(pending_approvals)} 单，已完成 {approved_count} 单（累计）。",
            "link": "/todos?type=approval",
        },
        {
            "kind": "data",
            "text": f"主数据为本地快照；{len(overdue)} 个商机阶段停留超期，建议先处理阻断项。",
            "link": "/master-data",
        },
    ]

    return {
        "identity": identity.to_public(),
        "data_as_of": now.isoformat(),
        "metrics": {
            "today_todos": len(today_todos),
            "open_todos": len(todos),
            "pending_approvals": len(pending_approvals),
            "blockers": len(blockers),
            "overdue_opportunities": len(overdue),
            "active_opportunities": len(active),
            "active_amount": round(active_amount, 2),
            "weighted_forecast": round(weighted, 2),
            "approved_approvals": approved_count,
            "win_rate": round(
                len([o for o in opps if o.status == "won"]) / max(1, len([o for o in opps if o.status in {"won", "lost"}])) * 100,
                1,
            ),
        },
        "funnel": funnel_stage_rows(opps),
        "brief": brief,
        "top_todos": top_todos,
        "top_opportunities": top_opps,
        "pending_approval_items": [
            {
                "id": str(a.id),
                "request_no": a.request_no,
                "gate_code": a.gate_code,
                "opportunity_id": str(a.opportunity_id),
                "status": a.status,
                "requested_at": a.requested_at.isoformat() if a.requested_at else None,
                "current_step": a.current_step,
                "steps": [
                    {
                        "step_no": s.step_no,
                        "approver_role": s.approver_role,
                        "status": s.status,
                        "sla_due_at": s.sla_due_at.isoformat() if s.sla_due_at else None,
                    }
                    for s in a.steps
                ],
            }
            for a in pending_approvals[:5]
        ],
        "placeholders": [
            {"code": "C2", "label": "招标雷达", "status": "not_connected", "hint": "QW1 接入公开招标文件后开放"},
            {"code": "D01", "label": "回款作战", "status": "not_connected", "hint": "依赖合同与财务实收接口"},
            {"code": "B01", "label": "集团全景", "status": "not_connected", "hint": "依赖 MDM / 售后 / 财务"},
            {"code": "E01", "label": "装机台账", "status": "not_connected", "hint": "依赖售后装机数据"},
            {"code": "F01", "label": "领导驾驶舱", "status": "not_connected", "hint": "QW1-QW3 数据稳定后开放"},
        ],
        "quick_entries": [
            {"label": "新建商机", "link": "/opportunities?new=1", "kind": "primary"},
            {"label": "处理待办", "link": "/todos", "kind": "default"},
            {"label": "导入主数据", "link": "/master-data?import=1", "kind": "default"},
        ],
    }


@router.get("/brief")
async def workbench_brief(
    identity: Identity = Depends(require_sales_permission("sales.workbench.read")),
    db: AsyncSession = Depends(get_db),
):
    summary = await workbench_summary(identity, db)
    return {"data_as_of": summary["data_as_of"], "brief": summary["brief"]}


@router.get("/cards")
async def workbench_cards(
    identity: Identity = Depends(require_sales_permission("sales.workbench.read")),
    db: AsyncSession = Depends(get_db),
):
    role = "sales_admin" if identity.is_admin else identity.sales_role
    rows = list((await db.execute(select(WorkbenchCardConfig).where(WorkbenchCardConfig.role_code == role, WorkbenchCardConfig.enabled.is_(True)).order_by(WorkbenchCardConfig.sort_order.asc()))).scalars())
    cards = [r.card_code for r in rows] if rows else DEFAULT_CARDS
    return {"role": role, "cards": cards}


@router.get("/funnel")
async def workbench_funnel(
    identity: Identity = Depends(require_sales_permission("sales.opportunity.read")),
    db: AsyncSession = Depends(get_db),
):
    opps = list((await db.execute(select(Opportunity).where(scope_condition(identity, Opportunity)))).scalars())
    return {"stages": funnel_stage_rows(opps), "stage_labels": STAGE_LABELS}
