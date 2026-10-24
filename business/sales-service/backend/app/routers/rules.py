from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Identity, require_sales_permission
from app.database import get_db
from app.domain import add_audit, utc_now
from app.enums import APPROVAL_STATUSES, ROLE_LABELS, SALES_ROLES, SEVERITIES, STAGE_LABELS, STAGES, TODO_TYPES
from app.errors import not_found
from app.models import AuditEvent, LostReasonCode, Notification, RuleConfig
from app.schemas import RuleUpdate

router = APIRouter(tags=["rules"])


@router.get("/meta")
async def meta(identity: Identity = Depends(require_sales_permission("sales.rule.read"))):
    return {
        "stages": [{"code": s, "label": STAGE_LABELS[s]} for s in STAGES],
        "roles": [{"code": r, "label": ROLE_LABELS.get(r, r)} for r in sorted(SALES_ROLES)],
        "severities": sorted(SEVERITIES),
        "todo_types": sorted(TODO_TYPES),
        "approval_statuses": sorted(APPROVAL_STATUSES),
        "identity": identity.to_public(),
    }


@router.get("/rules")
async def list_rules(
    identity: Identity = Depends(require_sales_permission("sales.rule.read")),
    db: AsyncSession = Depends(get_db),
):
    rows = list((await db.execute(select(RuleConfig).order_by(RuleConfig.rule_code, RuleConfig.version.desc()))).scalars())
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row.rule_code, []).append(
            {
                "id": str(row.id),
                "version": row.version,
                "enabled": row.enabled,
                "config": row.config_json,
                "effective_from": row.effective_from.isoformat() if row.effective_from else None,
                "effective_to": row.effective_to.isoformat() if row.effective_to else None,
            }
        )
    return {"items": [{"rule_code": code, "versions": versions, "active": next((v for v in versions if v["effective_to"] is None), None)} for code, versions in grouped.items()]}


@router.put("/rules/{rule_code}")
async def update_rule(
    rule_code: str,
    body: RuleUpdate,
    identity: Identity = Depends(require_sales_permission("sales.rule.manage")),
    db: AsyncSession = Depends(get_db),
):
    active = (await db.execute(select(RuleConfig).where(RuleConfig.rule_code == rule_code, RuleConfig.effective_to.is_(None)).order_by(RuleConfig.version.desc()).limit(1))).scalar_one_or_none()
    if active is None:
        raise not_found("规则不存在", "SALES-404-RULE")
    next_version = int((await db.execute(select(RuleConfig.version).where(RuleConfig.rule_code == rule_code).order_by(RuleConfig.version.desc()).limit(1))).scalar_one()) + 1
    active.effective_to = utc_now()
    new = RuleConfig(
        rule_code=rule_code,
        version=next_version,
        enabled=body.enabled if body.enabled is not None else active.enabled,
        config_json=body.config_json if body.config_json is not None else active.config_json,
        effective_from=utc_now(),
        created_by=identity.user_id,
    )
    db.add(new)
    add_audit(
        db,
        actor_id=identity.user_id,
        action="rule.update",
        object_type="rule_config",
        object_id=str(new.id),
        before={"rule_code": rule_code, "version": active.version, "config": active.config_json},
        after={"rule_code": rule_code, "version": next_version, "config": new.config_json, "reason": body.reason},
    )
    await db.flush()
    return {"rule_code": rule_code, "version": next_version, "enabled": new.enabled, "config": new.config_json}


@router.get("/lost-reason-codes")
async def lost_reasons(
    identity: Identity = Depends(require_sales_permission("sales.rule.read")),
    db: AsyncSession = Depends(get_db),
):
    rows = list((await db.execute(select(LostReasonCode).where(LostReasonCode.is_active.is_(True)).order_by(LostReasonCode.sort_order))).scalars())
    return {"items": [{"code": r.code, "label": r.label, "requires_note": r.requires_note} for r in rows]}


@router.get("/notifications")
async def notifications(
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    identity: Identity = Depends(require_sales_permission("sales.workbench.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Notification).where(Notification.user_id == identity.user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = list((await db.execute(stmt.order_by(Notification.created_at.desc()).limit(limit))).scalars())
    return {
        "items": [
            {
                "id": str(n.id),
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "link": n.link,
                "read_at": n.read_at.isoformat() if n.read_at else None,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in rows
        ],
        "unread": len([n for n in rows if n.read_at is None]),
    }


@router.post("/notifications/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    identity: Identity = Depends(require_sales_permission("sales.workbench.read")),
    db: AsyncSession = Depends(get_db),
):
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.user_id != identity.user_id:
        raise not_found("通知不存在", "SALES-404-NOTIFICATION")
    notification.read_at = utc_now()
    await db.flush()
    return {"id": str(notification.id), "read_at": notification.read_at.isoformat()}


@router.get("/audit")
async def audit_events(
    action: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    identity: Identity = Depends(require_sales_permission("sales.audit.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditEvent)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if object_type:
        stmt = stmt.where(AuditEvent.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditEvent.object_id == object_id)
    rows = list((await db.execute(stmt.order_by(AuditEvent.created_at.desc()).limit(limit))).scalars())
    return {
        "items": [
            {
                "id": str(e.id),
                "actor_id": e.actor_id,
                "action": e.action,
                "object_type": e.object_type,
                "object_id": e.object_id,
                "before": e.before_json,
                "after": e.after_json,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in rows
        ]
    }
