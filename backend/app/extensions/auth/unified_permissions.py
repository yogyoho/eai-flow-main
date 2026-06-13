"""Unified permission checking — single entry point for all project RBAC.

Replaces the dual-system (permissions.py + project_permissions.py) with
one function that queries the role_permissions table.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.database import get_db
from app.extensions.models import ProjectMember, Role
from app.extensions.models.role_permission import ProjectRole
from app.extensions.schemas import CurrentUser


async def resolve_user_project_role(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    phase_node: str | None = None,
) -> ProjectRole | None:
    """Resolve a user's effective ProjectRole within a project.

    Priority:
    1. phase_duties override for the given phase_node
    2. ProjectMember.role
    3. None (not a member)
    """
    member_result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        return None

    # Phase-scoped role override
    if phase_node and member.phase_duties:
        phase_duty = member.phase_duties.get(phase_node, {})
        duty_role = phase_duty.get("role")
        if duty_role:
            _LEGACY_MAP = {
                "lead": ProjectRole.PHASE_LEAD.value,
                "leader": ProjectRole.PHASE_LEAD.value,
                "reviewer": ProjectRole.REVIEWER.value,
                "dept_reviewer": ProjectRole.REVIEWER.value,
                "approver": ProjectRole.APPROVER.value,
                "company_reviewer": ProjectRole.APPROVER.value,
                "write": ProjectRole.WRITER.value,
                "writer": ProjectRole.WRITER.value,
            }
            normalised = _LEGACY_MAP.get(duty_role, duty_role)
            try:
                return ProjectRole(normalised)
            except ValueError:
                pass

    # Project-level role
    try:
        return ProjectRole(member.role)
    except ValueError:
        return None


async def get_user_permissions(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    phase_node: str | None = None,
) -> set[str]:
    """Return the effective permission set for a user in a project."""
    from app.extensions.models.role_permission import RolePermission

    # Admin bypass — look up user's system role
    from app.extensions.models import User
    user = await db.get(User, user_id)
    user_role = None
    if user and user.role_id:
        user_role = await db.get(Role, user.role_id)
    if user_role and (user_role.is_system or "*" in (user_role.permissions or [])):
        result = await db.execute(select(RolePermission.permission))
        return {row[0] for row in result.all()}

    project_role = await resolve_user_project_role(db, user_id, project_id, phase_node)
    if not project_role:
        return set()

    result = await db.execute(
        select(RolePermission.permission).where(
            RolePermission.role == project_role.value
        )
    )
    return {row[0] for row in result.all()}


async def require_project_permission(
    action: str,
    project_id: UUID,
    user: CurrentUser,
    db: AsyncSession,
    phase_node: str | None = None,
):
    """FastAPI dependency: raise 403 if user lacks action in project."""
    perms = await get_user_permissions(db, user.id, project_id, phase_node)
    if action not in perms:
        raise HTTPException(
            status_code=403,
            detail=f"Permission '{action}' required",
        )
    return user


def RequireProjectPerm(action: str):
    """Factory: create a FastAPI dependency for a specific project permission."""
    async def _dep(
        project_id: UUID,
        user: CurrentUser,
        db: AsyncSession = Depends(get_db),
    ):
        return await require_project_permission(action, project_id, user, db)
    return Depends(_dep)
