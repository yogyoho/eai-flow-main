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

# DEPRECATED (2026-06-13): This module is superseded by
# app.extensions.auth.unified_permissions.  It is kept for backward
# compatibility during migration and will be removed after all callers
# are migrated.
import warnings
warnings.warn(
    "project_permissions.py is deprecated; use unified_permissions instead",
    DeprecationWarning,
    stacklevel=2,
)

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
    "chapter:confirm",
    "ai:start_writing",
    "source:view",
    "version:rollback",
    "export:generate",
    "settings:edit",
    "workflow:start",
    "workflow:cancel",
    "workflow:edit",
    "template:manage",
    "template:publish",
    "report:submit",
    "report:final_approve",
]

# Owner always gets all permissions regardless of system role
OWNER_PERMISSIONS = set(PROJECT_PERMISSIONS)

# Slot type → permissions granted for that workflow slot
SLOT_PERMISSIONS: dict[str, set[str]] = {
    "leader": {
        "member:add", "outline:edit", "ai:start_writing",
        "project:edit", "chapter:write_any", "chapter:confirm",
        "report:submit",
    },
    "writer": {
        "ai:start_writing", "chapter:write_own", "chapter:confirm",
    },
    "dept_reviewer": {
        "chapter:review", "approval:review",
    },
    "company_reviewer": {
        "chapter:review", "approval:review", "report:final_approve",
    },
}

# Backward-compat aliases for old duty key → new slot_type
_LEGACY_DUTY_MAP: dict[str, str] = {
    "lead": "leader",
    "reviewer": "dept_reviewer",
    "approver": "company_reviewer",
    "data_reviewer": "dept_reviewer",
}

# Backward-compat alias
_DUTY_BONUS = SLOT_PERMISSIONS


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
    project_role: str = "writer",
    system_role: Optional[object] = None,
    phase_duties: Optional[dict] = None,
) -> list[str]:
    """Get permissions for a user within a specific project.

    Combines system role permissions with workflow slot-based permissions
    derived from phase_duties.

    Args:
        project_role: Legacy project role string (kept for backward compat).
        system_role: The user's system Role ORM object.
        phase_duties: The user's phase_duties JSONB from project_members.
            Each entry may have "slot_type" (new) or "duty" (legacy).

    Returns:
        List of permission action strings for this project context.
    """
    # Owner always gets all permissions
    if project_role == "owner":
        return list(OWNER_PERMISSIONS)

    base_perms: set[str] = set()

    # Merge in any system-role permissions that apply to project scope
    base_perms |= set(get_effective_permissions(role=system_role))

    # Grant permissions from workflow slot assignments
    if phase_duties:
        for _phase_key, duty_info in phase_duties.items():
            # Support both new "slot_type" and legacy "duty" keys
            slot_type = duty_info.get("slot_type") or duty_info.get("duty", "")
            # Map legacy duty names to new slot types
            slot_type = _LEGACY_DUTY_MAP.get(slot_type, slot_type)
            if slot_type in SLOT_PERMISSIONS:
                base_perms |= SLOT_PERMISSIONS[slot_type]

    return list(base_perms)


def has_permission(permissions: list[str], action: str) -> bool:
    """Check if a permission list contains a specific action."""
    return action in permissions
