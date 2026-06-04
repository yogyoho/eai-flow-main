"""Project RBAC permission matrix — owner/manager/editor/reviewer/approver/member model."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Order: most privileged → least privileged
ROLE_ORDER = ["owner", "manager", "editor", "reviewer", "approver", "member"]

# Permission matrix — each column maps to ROLE_ORDER index.
#                      owner  manager  editor  reviewer  approver  member
PERMISSION_MATRIX: dict[str, list[bool]] = {
    "project:edit":    [True,  True,    False,  False,    False,    False],
    "project:delete":  [True,  False,   False,  False,    False,    False],
    "member:add":      [True,  True,    False,  False,    False,    False],
    "member:remove":   [True,  True,    False,  False,    False,    False],
    "approval:submit": [True,  True,    False,  False,    False,    False],
    "approval:review": [True,  True,    False,  True,     False,    False],
    "approval:approve":[True,  True,    False,  False,    True,     False],
    "approval:view":   [True,  True,    True,   True,     True,     True],
    "outline:edit":    [True,  True,    True,   False,    False,    False],
    "chapter:write_any":[True, True,    True,   False,    False,    False],
    "chapter:write_own":[True, True,    True,   False,    False,    False],
    "chapter:review":  [True,  True,    False,  True,     False,    False],
    "settings:edit":   [True,  False,   False,  False,    False,    False],
}


def check_permission(role: str, action: str) -> bool:
    perms = PERMISSION_MATRIX.get(action)
    if perms is None:
        return False
    try:
        idx = ROLE_ORDER.index(role)
    except ValueError:
        return False
    return perms[idx]


def get_permissions_for_role(role: str) -> list[str]:
    try:
        idx = ROLE_ORDER.index(role)
    except ValueError:
        return []
    return [action for action, perms in PERMISSION_MATRIX.items() if perms[idx]]


async def get_project_role(db: AsyncSession, project_id: UUID, user_id: UUID) -> str | None:
    from app.extensions.models import ProjectMember

    stmt = (
        select(ProjectMember.role)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_project_permissions(
    db: AsyncSession, project_id: UUID, user_id: UUID, is_admin: bool,
) -> tuple[str | None, list[str]]:
    if is_admin:
        return "owner", list(PERMISSION_MATRIX.keys())
    role = await get_project_role(db, project_id, user_id)
    if role is None:
        return None, []
    return role, get_permissions_for_role(role)


def require_resource_permission(action: str):
    from app.extensions.database import get_db
    from app.extensions.auth.middleware import require_permission

    base_auth = require_permission("system:access")

    async def check(
        current_user: Annotated = Depends(base_auth),
        request: Request = ...,
        db: AsyncSession = Depends(get_db),
    ) -> str:
        is_admin = False
        if current_user.role_id is not None:
            from app.extensions.models import Role
            role_obj = await db.get(Role, current_user.role_id)
            if role_obj is not None:
                permissions = role_obj.permissions or []
                if "*" in permissions or role_obj.is_system:
                    is_admin = True

        if is_admin:
            return "owner"

        project_id = request.path_params.get("project_id")
        if not project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="project_id is required in path")

        from uuid import UUID as _UUID
        try:
            pid = _UUID(project_id)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project_id")

        role = await get_project_role(db, pid, current_user.id)
        if role is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this project")

        if not check_permission(role, action):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission denied: {action}")

        return role

    return check
