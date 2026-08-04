"""Authentication middleware for extensions module.

Delegates authentication to Gateway Auth (Cookie-based JWT) and bridges
to the Extensions PostgreSQL user table via email matching.  On first
access a corresponding Extensions User row is auto-created; admin users
(Gateway ``system_role == "admin"``) are auto-assigned the ``superadmin``
role when it exists.
"""

import logging
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.database import get_db
from app.extensions.models import Department, Role, User
from app.extensions.schemas import CurrentUser

logger = logging.getLogger(__name__)

ACCESS_TOKEN_COOKIE = "access_token"

async def _ensure_role(db: AsyncSession, code: str) -> Role | None:
    """Look up a role by code, creating it on-the-fly from registry defaults if missing.

    No drift-reset: registry (permissions.yaml + roles_custom.yaml overlay) is the
    source of truth, and admin-assigned extra permissions must persist (S3 fix).
    """
    from app.extensions.auth.registry import get_permission_registry

    result = await db.execute(select(Role).where(Role.code == code))
    role = result.scalar_one_or_none()
    if role is not None:
        return role

    registry = get_permission_registry()
    defaults = registry.get_role_defaults(code)
    if defaults is None:
        return None

    role = Role(
        id=uuid.uuid4(),
        code=code,
        name=defaults.get("display_name", code),
        permissions=sorted(registry.resolve_role_permissions(code)),
        is_system=defaults.get("is_system", False),
        level=defaults.get("level", 10),
    )
    db.add(role)
    await db.flush()
    logger.info("Auto-created role '%s' (code=%s)", defaults.get("display_name", code), code)
    return role


async def _bridge_user(gw_user, db: AsyncSession) -> User:
    """Look up or auto-create an Extensions User for the given Gateway user."""
    stmt = select(User).where(User.email == gw_user.email)
    result = await db.execute(stmt)
    ext_user = result.scalar_one_or_none()

    if ext_user is not None:
        # Always validate the user's role to detect permission drift.
        role_code = "superadmin" if gw_user.system_role == "admin" else "user"
        await _ensure_role(db, role_code)

        if ext_user.role_id is None:
            role_code = "superadmin" if gw_user.system_role == "admin" else "user"
            role = await _ensure_role(db, role_code)
            if role is not None:
                ext_user.role_id = role.id
                await db.commit()
                await db.refresh(ext_user)
        return ext_user

    ext_user = User(
        username=gw_user.email.split("@")[0],
        email=gw_user.email,
        password_hash="",  # auth is handled by Gateway, not Extensions
        full_name=gw_user.email.split("@")[0],
        status="active",
    )
    db.add(ext_user)
    await db.flush()

    role_code = "superadmin" if gw_user.system_role == "admin" else "user"
    role = await _ensure_role(db, role_code)
    if role is not None:
        ext_user.role_id = role.id

    await db.commit()
    await db.refresh(ext_user)
    logger.info("Auto-created Extensions user %s for Gateway user %s", ext_user.id, gw_user.id)
    return ext_user


async def _build_current_user(ext_user: User, db: AsyncSession) -> CurrentUser:
    """Hydrate role and department display names for a CurrentUser response."""
    role_name = None
    if ext_user.role_id:
        role = await db.get(Role, ext_user.role_id)
        if role is not None:
            role_name = role.name

    dept_name = None
    if ext_user.dept_id:
        dept = await db.get(Department, ext_user.dept_id)
        if dept is not None:
            dept_name = dept.name

    return CurrentUser(
        id=ext_user.id,
        username=ext_user.username,
        email=ext_user.email,
        full_name=ext_user.full_name,
        role_id=ext_user.role_id,
        role_name=role_name,
        dept_id=ext_user.dept_id,
        dept_name=dept_name,
        status=ext_user.status,
    )


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Authenticate via Gateway Auth cookie and return the bridged Extensions user.

    Raises HTTPException(401) when the request carries no valid Gateway session.
    On first access for a given user an Extensions ``User`` row is auto-created.
    """
    from app.gateway.deps import get_current_user_from_request

    gw_user = await get_current_user_from_request(request)
    ext_user = await _bridge_user(gw_user, db)
    current_user = await _build_current_user(ext_user, db)
    logger.debug(
        "Bridged user: gw_id=%s email=%s system_role=%s → ext_id=%s role_id=%s role_name=%s",
        gw_user.id, gw_user.email, gw_user.system_role,
        current_user.id, current_user.role_id, current_user.role_name,
    )
    return current_user


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CurrentUser | None:
    """Return the bridged Extensions user, or ``None`` when unauthenticated."""
    from app.gateway.deps import get_optional_user_from_request

    gw_user = await get_optional_user_from_request(request)
    if gw_user is None:
        return None

    stmt = select(User).where(User.email == gw_user.email)
    result = await db.execute(stmt)
    ext_user = result.scalar_one_or_none()
    if ext_user is None:
        return None

    return await _build_current_user(ext_user, db)


def require_permission(permission: str):
    """Dependency factory for requiring a specific permission."""

    async def check_permission(
        current_user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> CurrentUser:
        if current_user.role_id is None:
            logger.warning(
                "Permission check failed: user=%s (%s) has no role assigned",
                current_user.id, current_user.username,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No role assigned. Please contact administrator.",
            )

        # EAI-CUSTOM: Delegate permission check to UnifiedPermissionEngine (ABAC-lite)
        from app.extensions.auth.cache import (
            get_cached_engine,
            get_cached_identity,
            set_cached_engine,
            set_cached_identity,
        )
        from app.extensions.auth.engine import UnifiedPermissionEngine
        from app.extensions.auth.identity import get_identity_provider
        from app.extensions.auth.registry import get_permission_registry

        # EAI-CUSTOM: Roles come from PermissionRegistry (permissions.yaml + roles_custom.yaml overlay),
        # with #inherit expansion — DB roles table is a calibrated mirror, not the source.
        registry = get_permission_registry()
        role_permissions = {
            code: registry.resolve_role_permissions(code)
            for code in registry.list_role_codes()
        }
        all_ids = {p.id for p in registry.list_all_permissions()}

        # Engine: cached per request
        engine = get_cached_engine()
        if engine is None:
            # Load ABAC policies from DB (global, dynamic — kept as data)
            from app.extensions.auth.engine import Policy as EnginePolicy
            from app.extensions.auth.models import Policy as PolicyModel

            policy_result = await db.execute(
                select(PolicyModel)
                .where(PolicyModel.enabled == True)  # noqa: E712
                .order_by(PolicyModel.priority)
            )
            policies = [
                EnginePolicy(
                    name=p.name,
                    priority=p.priority,
                    conditions=p.conditions,
                    grants=p.grants,
                )
                for p in policy_result.scalars().all()
            ]

            engine = UnifiedPermissionEngine(
                role_permissions=role_permissions,
                all_permission_ids=all_ids,
                policies=policies,
            )
            set_cached_engine(engine)

        # Identity: cached per request
        identity = get_cached_identity()
        if identity is None:
            provider = get_identity_provider()
            identity = await provider.resolve(current_user.id, db)
            set_cached_identity(identity)

        # EAI-CUSTOM: System-role wildcard bypass comes from registry defaults, not DB
        defaults = registry.get_role_defaults(identity.role_code)
        is_system = bool(defaults and defaults.get("is_system"))
        resolved = role_permissions.get(identity.role_code or "", set())
        if is_system or "*" in resolved:
            return current_user

        if current_user.role_id is not None and identity.role_code is None:
            logger.warning(
                "Permission check failed: user=%s role_id=%s not found in DB",
                current_user.id, current_user.role_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role not found",
            )

        if not engine.check(identity, permission):
            logger.warning(
                "Permission check failed: user=%s role=%s lacks '%s'",
                current_user.id, identity.role_code, permission,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )

        return current_user

    return check_permission


def require_role(*roles: str):
    """Dependency factory for requiring specific roles."""

    async def check_role(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.role_name in roles:
            return current_user

        if "超级管理员" in roles or "admin" in roles:
            if current_user.role_name in ("超级管理员", "admin"):
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role not authorized. Required: {roles}",
        )

    return check_role


def require_super_admin():
    """Dependency that only allows system admin users (is_system or wildcard permissions).

    Used for operations that should be locked to super admins only,
    e.g. editing/deleting workflow definitions after creation.
    """

    # EAI-CUSTOM: Reads super-admin status from PermissionRegistry, not the DB Role row,
    # so a tampered DB row (non-system role with "*") cannot grant super-admin access.
    async def check_super_admin(
        current_user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> CurrentUser:
        from app.extensions.auth.identity import get_identity_provider
        from app.extensions.auth.registry import get_permission_registry

        if current_user.role_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super admin access required.",
            )

        registry = get_permission_registry()
        provider = get_identity_provider()
        identity = await provider.resolve(current_user.id, db)

        defaults = registry.get_role_defaults(identity.role_code)
        is_system = bool(defaults and defaults.get("is_system"))
        resolved = registry.resolve_role_permissions(identity.role_code or "")
        if is_system or "*" in resolved:
            return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required. Only system administrators can perform this action.",
        )

    return check_super_admin


# ── Data scope dependency ────────────────────────────────────────────

from app.extensions.auth.datascope import DataScopeEngine
from app.extensions.auth.engine import FilterRule


def with_data_scope(resource_type: str):
    """FastAPI dependency: inject a FilterRule for data-level access control.

    Superadmin (is_system or '*' perms) gets allow_all (built-in bypass).
    Otherwise: allow scopes from registry, MINUS deny_data_scopes from active
    ABAC policies whose conditions match the identity.

    Usage:
        @router.get("/knowledge-bases")
        async def list_kbs(
            db: AsyncSession = Depends(get_db),
            scope: FilterRule = Depends(with_data_scope("knowledge")),
        ):
            query = select(KnowledgeBase).where(scope.to_sqlalchemy(KnowledgeBase))
            ...
    """
    async def _scope(
        current_user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> FilterRule:
        from app.extensions.auth.engine import evaluate_policy_conditions
        from app.extensions.auth.identity import get_identity_provider
        from app.extensions.auth.policy_loader import load_active_policies
        from app.extensions.auth.registry import get_permission_registry

        identity = await get_identity_provider().resolve(current_user.id, db)
        reg = get_permission_registry()
        defaults = reg.get_role_defaults(identity.role_code)
        resolved = reg.resolve_role_permissions(identity.role_code or "")
        if (defaults and defaults.get("is_system")) or "*" in resolved:
            return FilterRule(operator="allow_all")  # superadmin double-exemption, built-in
        deny_ids = set()
        for p in await load_active_policies(db):
            if evaluate_policy_conditions(p.conditions, identity):
                deny_ids.update(p.grants.get("deny_data_scopes") or [])
        return DataScopeEngine.from_registry().get_data_scope(identity, resource_type, deny_ids)

    return _scope
