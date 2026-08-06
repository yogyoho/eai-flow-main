"""EAI-CUSTOM: 每-KB 显式授权的可见性/写权限辅助（knowledge_base_grants）。"""

from __future__ import annotations

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import aliased

from app.extensions.auth.identity import AttributeSet
from app.extensions.models import KnowledgeBase, KnowledgeBaseGrant


def _grantee_match(g, identity: AttributeSet):
    """授权行命中身份的 OR 条件：user=用户id、dept=部门id、role=角色code。"""
    return or_(
        and_(g.grantee_type == "user", g.grantee_id == str(identity.user_id)),
        and_(g.grantee_type == "dept", g.grantee_id.in_(identity.dept_ids or [])),
        and_(g.grantee_type == "role", g.grantee_id == identity.role_code),
    )


def _grant_active(g):
    """未过期（expires_at 为空或未来）。"""
    return or_(g.expires_at.is_(None), g.expires_at > func.now())


def kb_grant_visible_clause(identity: AttributeSet):
    """SQL EXISTS：当前 KB 有一条命中身份的未过期授权行。拼进 KB 查询 WHERE 的 OR 分支。"""
    g = aliased(KnowledgeBaseGrant)
    return exists(select(1).where(and_(g.kb_id == KnowledgeBase.id, _grantee_match(g, identity), _grant_active(g))))


async def has_kb_grant(db, kb_id, identity: AttributeSet, permission: str | None = None) -> bool:
    """当前身份对某 KB 是否有显式授权（可选限定 permission=read|write）。"""
    g = KnowledgeBaseGrant
    clauses = [g.kb_id == kb_id, _grantee_match(g, identity), _grant_active(g)]
    if permission:
        clauses.append(g.permission == permission)
    stmt = select(g.id).where(and_(*clauses)).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none() is not None
