"""Authentication middleware for extensions module."""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.jwt import verify_token
from app.extensions.database import get_db
from app.extensions.models import Department, Role, User
from app.extensions.schemas import CurrentUser

security = HTTPBearer(auto_error=False)

ACCESS_TOKEN_COOKIE = "access_token"


def extract_token_from_request(request: Request) -> Optional[str]:
    """Extract token from Authorization header or cookie."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.cookies.get(ACCESS_TOKEN_COOKIE)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Get current authenticated user from JWT token."""
    token = extract_token_from_request(request)

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(token, "access")

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from sqlalchemy import select

    stmt = select(User).where(User.id == payload.sub)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active",
        )

    role_name = None
    dept_name = None

    if user.role_id:
        stmt_role = select(Role).where(Role.id == user.role_id)
        result_role = await db.execute(stmt_role)
        role = result_role.scalar_one_or_none()
        if role:
            role_name = role.name

    if user.dept_id:
        stmt_dept = select(Department).where(Department.id == user.dept_id)
        result_dept = await db.execute(stmt_dept)
        dept = result_dept.scalar_one_or_none()
        if dept:
            dept_name = dept.name

    return CurrentUser(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role_id=user.role_id,
        role_name=role_name,
        dept_id=user.dept_id,
        dept_name=dept_name,
        status=user.status,
    )


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[CurrentUser]:
    """Get current user if authenticated, otherwise return None."""
    try:
        return await get_current_user(request, credentials, db)
    except HTTPException:
        return None


def require_permission(permission: str):
    """Dependency factory for requiring a specific permission."""

    async def check_permission(
        current_user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> CurrentUser:
        if current_user.role_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No role assigned. Please contact administrator.",
            )

        from sqlalchemy import select

        stmt = select(Role).where(Role.id == current_user.role_id)
        result = await db.execute(stmt)
        role = result.scalar_one_or_none()

        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role not found",
            )

        permissions = role.permissions or []

        if "*" in permissions or role.is_system:
            return current_user

        if permission not in permissions and f"{permission.split(':')[0]}:*" not in permissions:
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
            if current_user.role_name == "超级管理员" or current_user.role_name == "admin":
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role not authorized. Required: {roles}",
        )

    return check_role
