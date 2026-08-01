"""Shared superadmin / admin-bypass helper (registry-backed, yaml authority).

# EAI-CUSTOM: yaml-driven role/permission system — the single source of truth
for "is this user an admin" is the PermissionRegistry (permissions.yaml +
roles_custom.yaml overlay), not the DB `roles` row. The DB role row is only a
calibrated mirror (code → id for users.role_id FK) and may lag the registry;
reading it for authorization makes the bypass depend on a stale mirror.
Use :func:`is_superadmin` instead of `db.get(Role, user.role_id)` +
`is_system or "*" in permissions` for every admin bypass.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth import identity as identity_mod
from app.extensions.auth.registry import get_permission_registry


async def is_superadmin(db: AsyncSession, user_id: UUID) -> bool:
    """True if the user's global role is is_system or has the wildcard (registry-resolved).

    Mirrors the middleware bypass expression (`is_system OR "*" in
    resolve_role_permissions(role_code)`) so every "is the user an admin"
    gate stays in lockstep with `require_super_admin`/`require_permission`.
    Returns False when the user row is missing or has no role.

    `get_identity_provider` is resolved through the module at call time so
    tests can monkeypatch `app.extensions.auth.identity.get_identity_provider`.
    """
    try:
        identity = await identity_mod.get_identity_provider().resolve(str(user_id), db)
    except ValueError:
        return False
    role_code = identity.role_code or ""
    defaults = get_permission_registry().get_role_defaults(role_code)
    if defaults and defaults.get("is_system"):
        return True
    resolved = get_permission_registry().resolve_role_permissions(role_code)
    return "*" in resolved
