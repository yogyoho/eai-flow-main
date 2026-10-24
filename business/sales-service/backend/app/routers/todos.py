from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import Identity, require_opportunity_access, require_sales_permission
from app.database import get_db
from app.domain import add_audit, todo_dict, utc_now
from app.errors import conflict, forbidden, not_found
from app.models import ApprovalAction, ApprovalRequest, ApprovalStep, Opportunity, Todo, TodoEvent
from app.schemas import TodoBatchIn, TodoUpdate

router = APIRouter(prefix="/todos", tags=["todos"])


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


async def _todo(db: AsyncSession, todo_id: uuid.UUID, *, lock: bool = False) -> Todo:
    stmt = select(Todo).where(Todo.id == todo_id)
    if lock:
        stmt = stmt.with_for_update()
    todo = (await db.execute(stmt)).scalar_one_or_none()
    if todo is None:
        raise not_found("待办不存在", "SALES-404-TODO")
    return todo


async def _opportunity_for_todo(db: AsyncSession, todo: Todo) -> Opportunity | None:
    if todo.object_type == "opportunity":
        return await db.get(Opportunity, todo.object_id)
    if todo.object_type == "approval":
        request = await db.get(ApprovalRequest, todo.object_id)
        if request:
            return await db.get(Opportunity, request.opportunity_id)
    return None


def _ensure_todo_access(identity: Identity, todo: Todo, opportunity: Opportunity | None) -> None:
    if identity.is_admin or identity.data_scope == "all":
        return
    if todo.assignee_id == identity.user_id or todo.assignee_role in {identity.sales_role, None}:
        if opportunity is not None:
            require_opportunity_access(identity, opportunity)
        return
    if identity.data_scope == "region" and todo.assignee_role in {"regional_manager", "data_steward"}:
        if opportunity is not None:
            require_opportunity_access(identity, opportunity)
        return
    raise forbidden("无权处理该待办", "SALES-403-TODO_SCOPE")


async def _todo_detail(db: AsyncSession, todo: Todo, identity: Identity) -> dict[str, Any]:
    opp = await _opportunity_for_todo(db, todo)
    data = todo_dict(todo, opp)
    data["assignee_name"] = None
    if todo.assignee_id:
        from app.models import UserProfile

        profile = await db.get(UserProfile, todo.assignee_id)
        data["assignee_name"] = profile.display_name if profile else todo.assignee_id
    if todo.type == "approval":
        request = (await db.execute(select(ApprovalRequest).where(ApprovalRequest.id == todo.object_id).options(selectinload(ApprovalRequest.steps).selectinload(ApprovalStep.assignments)))).scalar_one_or_none()
        if request:
            actions = list((await db.execute(select(ApprovalAction).where(ApprovalAction.request_id == request.id).order_by(ApprovalAction.created_at.asc()))).scalars())
            data["approval"] = {
                "id": str(request.id),
                "request_no": request.request_no,
                "gate_code": request.gate_code,
                "status": request.status,
                "current_step": request.current_step,
                "requested_by": request.requested_by,
                "reason": request.reason,
                "steps": [
                    {
                        "step_no": s.step_no,
                        "mode": s.mode,
                        "approver_role": s.approver_role,
                        "status": s.status,
                        "decision": s.decision,
                        "comment": s.comment,
                        "sla_due_at": s.sla_due_at.isoformat() if s.sla_due_at else None,
                        "assignments": [
                            {
                                "assignment_key": item.assignment_key,
                                "approver_role": item.approver_role,
                                "approver_id": item.approver_id,
                                "status": item.status,
                                "decision": item.decision,
                            }
                            for item in s.assignments
                        ],
                    }
                    for s in request.steps
                ],
                "actions": [
                    {
                        "step_no": a.step_no,
                        "assignment_key": a.assignment_key,
                        "action": a.action,
                        "actor_id": a.actor_id,
                        "comment": a.comment,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in actions
                ],
            }
    return data


@router.get("")
async def list_todos(
    type: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    assignee_id: str | None = None,
    assignee_role: str | None = None,
    object_type: str | None = None,
    object_id: uuid.UUID | None = None,
    overdue: bool | None = None,
    keyword: str | None = None,
    sort: str = "due_asc",
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    identity: Identity = Depends(require_sales_permission("sales.todo.read")),
    db: AsyncSession = Depends(get_db),
):
    from app.routers.workbench import todo_scope as workbench_todo_scope

    conditions = [workbench_todo_scope(identity)]
    if type:
        conditions.append(Todo.type == type)
    if status:
        conditions.append(Todo.status == status)
    if severity:
        conditions.append(Todo.severity == severity)
    if assignee_id:
        conditions.append(Todo.assignee_id == assignee_id)
    if assignee_role:
        conditions.append(Todo.assignee_role == assignee_role)
    if object_type:
        conditions.append(Todo.object_type == object_type)
    if object_id:
        conditions.append(Todo.object_id == object_id)
    if overdue:
        conditions.append(and_(Todo.due_at < utc_now(), Todo.status.in_(["open", "in_progress"])))
    if keyword:
        pattern = f"%{keyword.strip()}%"
        conditions.append(or_(Todo.title.ilike(pattern), Todo.todo_no.ilike(pattern), Todo.description.ilike(pattern)))

    total = int((await db.execute(select(func.count(Todo.id)).where(*conditions))).scalar_one())
    order = {
        "due_asc": Todo.due_at.asc(),
        "due_desc": Todo.due_at.desc(),
        "created_desc": Todo.created_at.desc(),
        "severity_asc": Todo.severity.asc(),
    }.get(sort, Todo.due_at.asc())
    rows = list((await db.execute(select(Todo).where(*conditions).order_by(order).offset(skip).limit(limit))).scalars())
    items = [await _todo_detail(db, t, identity) for t in rows]
    stats = await _stats(db, identity)
    return {"items": items, "total": total, "skip": skip, "limit": limit, "stats": stats}


async def _stats(db: AsyncSession, identity: Identity) -> dict[str, Any]:
    from app.routers.workbench import todo_scope as workbench_todo_scope

    scope = workbench_todo_scope(identity)
    open_rows = list((await db.execute(select(Todo).where(scope, Todo.status.in_(["open", "in_progress"])))).scalars())
    now = utc_now()
    return {
        "open": len(open_rows),
        "overdue": len([t for t in open_rows if t.due_at and t.due_at < now]),
        "blocker": len([t for t in open_rows if t.severity == "blocker"]),
        "high": len([t for t in open_rows if t.severity == "high"]),
        "approval": len([t for t in open_rows if t.type == "approval"]),
        "data_fix": len([t for t in open_rows if t.type == "data_fix"]),
        "arbitration": len([t for t in open_rows if t.type == "arbitration"]),
        "rule_event": len([t for t in open_rows if t.type == "rule_event"]),
    }


@router.get("/stats")
async def todo_stats(
    identity: Identity = Depends(require_sales_permission("sales.todo.read")),
    db: AsyncSession = Depends(get_db),
):
    return await _stats(db, identity)


@router.get("/{todo_id}")
async def get_todo(
    todo_id: uuid.UUID,
    identity: Identity = Depends(require_sales_permission("sales.todo.read")),
    db: AsyncSession = Depends(get_db),
):
    todo = await _todo(db, todo_id)
    opp = await _opportunity_for_todo(db, todo)
    _ensure_todo_access(identity, todo, opp)
    return await _todo_detail(db, todo, identity)


def _write_event(db: AsyncSession, todo: Todo, event_type: str, from_status: str, actor_id: str, note: str | None = None) -> None:
    db.add(
        TodoEvent(
            todo_id=todo.id,
            event_type=event_type,
            from_status=from_status,
            to_status=todo.status,
            operator_id=actor_id,
            note=note,
        )
    )


@router.patch("/{todo_id}")
async def update_todo(
    todo_id: uuid.UUID,
    body: TodoUpdate,
    identity: Identity = Depends(require_sales_permission("sales.todo.read")),
    db: AsyncSession = Depends(get_db),
):
    todo = await _todo(db, todo_id, lock=True)
    opp = await _opportunity_for_todo(db, todo)
    _ensure_todo_access(identity, todo, opp)
    if todo.type == "approval" and body.status in {"resolved", "cancelled"}:
        raise conflict("审批待办不能在此关闭，请通过审批中心作出决定", "SALES-409-APPROVAL_TODO")
    if any(v is not None for v in [body.assignee_id, body.assignee_role, body.severity, body.due_at]):
        if not identity.has("sales.todo.assign"):
            raise forbidden("缺少待办分派权限", "AUTH-403-PERMISSION_DENIED")
    if body.status in {"resolved", "cancelled"} and not identity.has("sales.todo.resolve"):
        raise forbidden("缺少待办处理权限", "AUTH-403-PERMISSION_DENIED")

    before_status = todo.status
    if body.assignee_id is not None:
        todo.assignee_id = body.assignee_id
        todo.assignee_role = None
    if body.assignee_role is not None:
        todo.assignee_role = body.assignee_role
        todo.assignee_id = None
    if body.severity is not None:
        todo.severity = body.severity
    if body.due_at is not None:
        todo.due_at = body.due_at
    if body.status is not None:
        todo.status = body.status
        if body.status in {"resolved", "cancelled"}:
            todo.resolved_at = utc_now()
            todo.resolution = body.resolution
    todo.updated_by = identity.user_id
    _write_event(db, todo, "updated", before_status, identity.user_id, body.resolution)
    add_audit(
        db,
        actor_id=identity.user_id,
        action="todo.update",
        object_type="todo",
        object_id=str(todo.id),
        before={"status": before_status},
        after={"status": todo.status, "assignee_id": todo.assignee_id, "assignee_role": todo.assignee_role},
    )
    await db.flush()
    return await _todo_detail(db, todo, identity)


@router.post("/{todo_id}/start")
async def start_todo(
    todo_id: uuid.UUID,
    identity: Identity = Depends(require_sales_permission("sales.todo.resolve")),
    db: AsyncSession = Depends(get_db),
):
    todo = await _todo(db, todo_id, lock=True)
    opp = await _opportunity_for_todo(db, todo)
    _ensure_todo_access(identity, todo, opp)
    if todo.type == "approval":
        raise conflict("审批待办无需开始，请直接处理审批", "SALES-409-APPROVAL_TODO")
    if todo.status not in {"open", "in_progress"}:
        raise conflict("待办已结束", "SALES-409-TODO_CLOSED")
    before = todo.status
    todo.status = "in_progress"
    todo.updated_by = identity.user_id
    _write_event(db, todo, "started", before, identity.user_id)
    await db.flush()
    return await _todo_detail(db, todo, identity)


@router.post("/{todo_id}/resolve")
async def resolve_todo(
    todo_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
    identity: Identity = Depends(require_sales_permission("sales.todo.resolve")),
    db: AsyncSession = Depends(get_db),
):
    todo = await _todo(db, todo_id, lock=True)
    opp = await _opportunity_for_todo(db, todo)
    _ensure_todo_access(identity, todo, opp)
    if todo.type == "approval":
        raise conflict("审批待办不能直接关闭，请到审批中心作出决定", "SALES-409-APPROVAL_TODO")
    if todo.status not in {"open", "in_progress"}:
        raise conflict("待办已结束", "SALES-409-TODO_CLOSED")
    before = todo.status
    todo.status = "resolved"
    todo.resolution = (payload or {}).get("resolution") or "已处理"
    todo.resolved_at = utc_now()
    todo.updated_by = identity.user_id
    _write_event(db, todo, "resolved", before, identity.user_id, todo.resolution)
    add_audit(
        db,
        actor_id=identity.user_id,
        action="todo.resolve",
        object_type="todo",
        object_id=str(todo.id),
        before={"status": before},
        after={"status": "resolved", "resolution": todo.resolution},
    )
    await db.flush()
    return await _todo_detail(db, todo, identity)


@router.post("/{todo_id}/cancel")
async def cancel_todo(
    todo_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
    identity: Identity = Depends(require_sales_permission("sales.todo.resolve")),
    db: AsyncSession = Depends(get_db),
):
    todo = await _todo(db, todo_id, lock=True)
    opp = await _opportunity_for_todo(db, todo)
    _ensure_todo_access(identity, todo, opp)
    if todo.type == "approval":
        raise conflict("审批待办不能直接取消，请取消审批单", "SALES-409-APPROVAL_TODO")
    before = todo.status
    todo.status = "cancelled"
    todo.resolution = (payload or {}).get("reason") or "已取消"
    todo.resolved_at = utc_now()
    todo.updated_by = identity.user_id
    _write_event(db, todo, "cancelled", before, identity.user_id, todo.resolution)
    await db.flush()
    return await _todo_detail(db, todo, identity)


@router.post("/batch")
async def batch_todos(
    body: TodoBatchIn,
    identity: Identity = Depends(require_sales_permission("sales.todo.batch")),
    db: AsyncSession = Depends(get_db),
):
    rows = list((await db.execute(select(Todo).where(Todo.id.in_(body.todo_ids), Todo.status.in_(["open", "in_progress"])).with_for_update())).scalars())
    if not rows:
        raise not_found("没有可处理的待办", "SALES-404-TODO")
    results = []
    for todo in rows:
        opp = await _opportunity_for_todo(db, todo)
        _ensure_todo_access(identity, todo, opp)
        if todo.type == "approval":
            results.append({"id": str(todo.id), "status": "skipped", "reason": "审批待办"})
            continue
        before = todo.status
        if body.action == "assign":
            todo.assignee_id = body.assignee_id
            todo.assignee_role = body.assignee_role
            todo.assignee_id = body.assignee_id
            event = "assigned"
        elif body.action == "resolve":
            todo.status = "resolved"
            todo.resolution = body.resolution or "批量处理"
            todo.resolved_at = utc_now()
            event = "resolved"
        else:
            todo.status = "cancelled"
            todo.resolution = body.resolution or "批量取消"
            todo.resolved_at = utc_now()
            event = "cancelled"
        todo.updated_by = identity.user_id
        _write_event(db, todo, event, before, identity.user_id, todo.resolution)
        results.append({"id": str(todo.id), "status": todo.status})
    add_audit(
        db,
        actor_id=identity.user_id,
        action=f"todo.batch_{body.action}",
        object_type="todo",
        object_id=None,
        after={"count": len(results), "todo_ids": [str(x) for x in body.todo_ids]},
    )
    await db.flush()
    return {"items": results, "processed": len(results)}
