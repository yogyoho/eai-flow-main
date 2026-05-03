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

# Role definitions for on-demand creation when seed_db hasn't run yet.
_ROLE_DEFAULTS = {
    "user": {"name": "普通用户", "permissions": ["kb:read", "kb:create", "kb:upload"], "level": 1},
    "superadmin": {"name": "Super Admin", "permissions": ["*"], "is_system": True, "level": 100},
}


async def _ensure_role(db: AsyncSession, code: str) -> Role | None:
    """Look up a role by code, creating it on-the-fly if missing."""
    result = await db.execute(select(Role).where(Role.code == code))
    role = result.scalar_one_or_none()
    if role is not None:
        return role

    defaults = _ROLE_DEFAULTS.get(code)
    if defaults is None:
        return None

    role = Role(
        id=uuid.uuid4(),
        code=code,
        name=defaults["name"],
        permissions=defaults["permissions"],
        is_system=defaults.get("is_system", False),
        level=defaults.get("level", 10),
    )
    db.add(role)
    await db.flush()
    logger.info("Auto-created role '%s' (code=%s)", defaults["name"], code)
    return role


async def _bridge_user(gw_user, db: AsyncSession) -> User:
    """Look up or auto-create an Extensions User for the given Gateway user."""
    stmt = select(User).where(User.email == gw_user.email)
    result = await db.execute(stmt)
    ext_user = result.scalar_one_or_none()

    if ext_user is not None:
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

        role = await db.get(Role, current_user.role_id)
        if role is None:
            logger.warning(
                "Permission check failed: user=%s role_id=%s not found in DB",
                current_user.id, current_user.role_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role not found",
            )

        permissions = role.permissions or []
        if "*" in permissions or role.is_system:
            return current_user

        if permission not in permissions and f"{permission.split(':')[0]}:*" not in permissions:
            logger.warning(
                "Permission check failed: user=%s role=%s permissions=%s lacks '%s'",
                current_user.id, role.code, permissions, permission,
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
