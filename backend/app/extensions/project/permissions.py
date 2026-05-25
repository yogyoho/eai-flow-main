"""Project RBAC permission matrix and check functions.

Provides a role-based access control system for project management with
five roles: manager, editor, writer, reviewer, approver.

The PERMISSION_MATRIX maps each action to a list of 5 booleans, one per
role in ROLE_ORDER.  Helper functions expose permission checks, role-based
permission lists, default tabs, and FastAPI dependency factories.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Role definitions ──

ROLE_ORDER = ["manager", "editor", "writer", "reviewer", "approver"]

# ── Permission matrix ──
# Each value is a list of 5 booleans aligned with ROLE_ORDER.
# [manager, editor, writer, reviewer, approver]

PERMISSION_MATRIX: dict[str, list[bool]] = {
    # Project management
    "project:edit":       [True,   False,  False,  False,    False],
    "project:delete":     [True,   False,  False,  False,    False],
    "project:advance":    [True,   False,  False,  False,    False],
    # Member management
    "member:add":         [True,   False,  False,  False,    False],
    "member:remove":      [True,   False,  False,  False,    False],
    "member:list":        [True,   True,   True,   False,    False],
    "member:manage":      [True,   False,  False,  False,    False],
    # Outline
    "outline:edit":       [True,   True,   False,  False,    False],
    "outline:view":       [True,   True,   True,   True,     True],
    # Chapters
    "chapter:write_own":  [True,   True,   True,   False,    False],
    "chapter:write_any":  [True,   False,  False,  False,    False],
    "chapter:view_all":   [True,   True,   True,   True,     True],
    "chapter:assign":     [True,   False,  False,  False,    False],
    "chapter:status":     [True,   False,  False,  False,    False],
    # AI tools
    "ai:start_writing":   [True,   False,  False,  False,    False],
    "ai:start_editing":   [True,   True,   True,   False,    False],
    "ai:toolbox":         [True,   True,   True,   False,    False],
    # Approval workflow
    "approval:submit":    [True,   False,  False,  False,    False],
    "approval:review":    [True,   False,  False,  True,     False],
    "approval:approve":   [True,   False,  False,  False,    True],
    "approval:view":      [True,   True,   True,   True,     True],
    # Export
    "export:generate":    [True,   False,  False,  False,    False],
    "export:view":        [True,   True,   True,   True,     True],
}

# ── Default tab per role ──

DEFAULT_TAB_MAP: dict[str, str] = {
    "manager":  "dashboard",
    "editor":   "my-workspace",
    "writer":   "my-workspace",
    "reviewer": "kanban",
    "approver": "kanban",
}


# ── Pure permission helpers ──


def check_permission(role: str, action: str) -> bool:
    """Check if a project role has permission for the given action.

    Returns False for unknown roles or actions.
    """
    perms = PERMISSION_MATRIX.get(action)
    if perms is None:
        return False
    try:
        idx = ROLE_ORDER.index(role)
    except ValueError:
        return False
    return perms[idx]


def get_permissions_for_role(role: str) -> list[str]:
    """Return all actions that the given role is allowed to perform.

    Returns an empty list for unknown roles.
    """
    try:
        idx = ROLE_ORDER.index(role)
    except ValueError:
        return []
    return [action for action, perms in PERMISSION_MATRIX.items() if perms[idx]]


def get_default_tab(role: str) -> str:
    """Return the default workspace tab for a given role.

    Falls back to 'dashboard' for unknown roles.
    """
    return DEFAULT_TAB_MAP.get(role, "dashboard")


# ── Database-backed helpers ──


async def get_project_role(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
) -> str | None:
    """Query the ProjectMember table for the user's role in a project.

    Returns the role string (e.g. 'editor') or None if the user is not a member.
    """
    from app.extensions.models import ProjectMember

    stmt = (
        select(ProjectMember.role)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    return row


async def get_user_project_permissions(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    is_admin: bool,
) -> tuple[str | None, list[str]]:
    """Get the user's effective project role and permissions.

    Admin users always get manager-level permissions regardless of
    project membership.  Non-admins get their project role permissions,
    or (None, []) if they are not a project member.
    """
    if is_admin:
        return "manager", list(PERMISSION_MATRIX.keys())

    role = await get_project_role(db, project_id, user_id)
    if role is None:
        return None, []
    return role, get_permissions_for_role(role)


# ── FastAPI dependency factory ──



def require_resource_permission(action: str):
    """FastAPI dependency factory for project-level permission checks.

    Workflow:
    1. Require base auth via ``require_permission("system:access")``.
    2. Check if user is a system admin (Role.permissions contains '*'
       or Role.is_system is True).  Admins get manager-level access.
    3. Otherwise, look up the user's role in ProjectMember and check
       PERMISSION_MATRIX.

    Returns the effective project role string (e.g. 'manager', 'editor').
    Raises HTTPException(403) on insufficient permissions.

    Usage::

        @router.post("/projects/{project_id}/outline")
        async def edit_outline(
            project_id: UUID,
            role: str = Depends(require_resource_permission("outline:edit")),
        ):
            ...
    """

    from app.extensions.database import get_db

    from app.extensions.auth.middleware import require_permission

    base_auth = require_permission("system:access")

    async def check(
        current_user: Annotated = Depends(base_auth),
        request: Request = ...,
        db: AsyncSession = Depends(get_db),
    ) -> str:
        # Check if user is system admin
        is_admin = False
        if current_user.role_id is not None:
            from app.extensions.models import Role

            role_obj = await db.get(Role, current_user.role_id)
            if role_obj is not None:
                permissions = role_obj.permissions or []
                if "*" in permissions or role_obj.is_system:
                    is_admin = True

        if is_admin:
            return "manager"

        # Extract project_id from path
        project_id = request.path_params.get("project_id")
        if not project_id:
            logger.warning(
                "require_resource_permission: no project_id in path for action=%s",
                action,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="project_id is required in path",
            )

        from uuid import UUID as _UUID

        try:
            pid = _UUID(project_id)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid project_id",
            )

        # Look up project role
        role = await get_project_role(db, pid, current_user.id)
        if role is None:
            logger.warning(
                "Permission denied: user=%s is not a member of project=%s action=%s",
                current_user.id, project_id, action,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this project",
            )

        if not check_permission(role, action):
            logger.warning(
                "Permission denied: user=%s role=%s project=%s action=%s",
                current_user.id, role, project_id, action,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {action}",
            )

        return role

    return check
