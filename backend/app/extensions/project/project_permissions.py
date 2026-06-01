"""Project-level permission system.

Extends the existing simple owner/member model with configurable
permissions derived from the Role.permissions ARRAY field.

The existing permissions.py remains for backward compatibility — it handles
the legacy owner/member matrix and require_resource_permission dependency.
This module provides the NEW logic for deriving project permissions from
system roles + phase duties, used by the tab registry and dashboard.

Design principle: double-layer config — system role provides defaults,
project-level phase_duties can grant additional permissions.
"""
from __future__ import annotations

from typing import Optional

# All project-level permission actions
PROJECT_PERMISSIONS = [
    "project:create",
    "project:edit",
    "project:delete",
    "member:add",
    "member:remove",
    "approval:submit",
    "approval:review",
    "approval:approve",
    "approval:view",
    "outline:edit",
    "chapter:write_any",
    "chapter:write_own",
    "chapter:review",
    "ai:start_writing",
    "source:view",
    "version:rollback",
    "export:generate",
    "settings:edit",
]

# Owner always gets all permissions regardless of system role
OWNER_PERMISSIONS = set(PROJECT_PERMISSIONS)

# Duty → extra permissions granted for that duty
_DUTY_BONUS: dict[str, set[str]] = {
    "lead": {"member:add", "outline:edit", "ai:start_writing"},
    "writer": {"chapter:write_own"},
    "reviewer": {"chapter:review", "approval:review"},
}


def get_effective_permissions(
    *,
    is_admin: bool = False,
    role: Optional[object] = None,
) -> list[str]:
    """Get effective project permissions for a user based on their system role.

    Args:
        is_admin: Whether the user is a system admin (gets all permissions).
        role: The user's Role ORM object (must have .permissions attribute).

    Returns:
        List of permission action strings.
    """
    if is_admin:
        return list(PROJECT_PERMISSIONS)
    if role is not None:
        role_perms = getattr(role, "permissions", []) or []
        return [p for p in role_perms if p in PROJECT_PERMISSIONS]
    return []


def get_project_role_permissions(
    *,
    project_role: str = "member",
    system_role: Optional[object] = None,
    phase_duties: Optional[dict] = None,
) -> list[str]:
    """Get permissions for a user within a specific project.

    Combines system role permissions with project-level role overrides
    and phase duty bonuses.

    Args:
        project_role: The user's role in this project ("owner" or "member").
        system_role: The user's system Role ORM object.
        phase_duties: The user's phase_duties JSONB from project_members.

    Returns:
        List of permission action strings for this project context.
    """
    if project_role == "owner":
        return list(OWNER_PERMISSIONS)

    # Member: derive from system role permissions
    base_perms = set(get_effective_permissions(role=system_role))

    # If user has phase_duties, grant additional permissions based on duties
    if phase_duties:
        for _phase_key, duty_info in phase_duties.items():
            duty = duty_info.get("duty", "")
            if duty in _DUTY_BONUS:
                base_perms |= _DUTY_BONUS[duty]

    return list(base_perms)


def has_permission(permissions: list[str], action: str) -> bool:
    """Check if a permission list contains a specific action."""
    return action in permissions
