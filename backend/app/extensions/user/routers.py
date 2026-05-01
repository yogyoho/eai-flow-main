"""User routers for extensions module."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user, require_permission
from app.extensions.database import get_db
from app.extensions.schemas import (
    CurrentUser,
    MessageResponse,
    UserBatchOperation,
    UserBatchResponse,
    UserCreate,
    UserListResponse,
    UserPasswordChange,
    UserPasswordReset,
    UserResponse,
    UserStatistics,
    UserUpdate,
)
from app.extensions.user.service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/users", tags=["Users"])


@router.get("", response_model=UserListResponse)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    dept_id: UUID | None = None,
    role_id: UUID | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all users with pagination and filters."""
    is_admin = current_user.role_name in ["超级管理员", "管理员", "admin"] or await _is_admin_role(db, current_user)

    if not is_admin:
        if current_user.dept_id:
            if dept_id and str(dept_id) != str(current_user.dept_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot view users from other departments",
                )
            dept_id = current_user.dept_id
        else:
            dept_id = None

    users, total = await UserService.list_users(db, skip=skip, limit=limit, dept_id=dept_id, role_id=role_id, status=status)
    return UserListResponse(
        users=[await UserService.to_response(db, u) for u in users],
        total=total,
    )


async def _is_admin_role(db: AsyncSession, current_user: CurrentUser) -> bool:
    """Check if current user has admin role."""
    if not current_user.role_id:
        return False

    from sqlalchemy import select

    from app.extensions.models import Role

    stmt = select(Role).where(Role.id == current_user.role_id)
    result = await db.execute(stmt)
    role = result.scalar_one_or_none()

    if not role:
        return False

    permissions = role.permissions or []
    return "user:read" in permissions or any(p.endswith(":read") for p in permissions) or "*" in permissions


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("user:create")),
):
    """Create a new user."""
    existing = await UserService.get_user_by_username(db, data.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    existing = await UserService.get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists",
        )

    user = await UserService.create_user(db, data)
    return await UserService.to_response(db, user)


@router.get("/me", response_model=UserResponse)
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get current authenticated user info (bridged from Gateway Auth)."""
    user = await UserService.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return await UserService.to_response(db, user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("user:read")),
):
    """Get a specific user by ID."""
    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return await UserService.to_response(db, user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("user:update")),
):
    """Update a user."""
    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if data.email and data.email != user.email:
        existing = await UserService.get_user_by_email(db, data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists",
            )

    user = await UserService.update_user(db, user, data)
    return await UserService.to_response(db, user)


@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("user:delete")),
):
    """Delete a user."""
    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    await UserService.delete_user(db, user)
    return MessageResponse(message="User deleted successfully")


@router.post("/{user_id}/reset-password", response_model=MessageResponse)
async def reset_password(
    user_id: UUID,
    body: UserPasswordReset,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("user:update")),
):
    """Reset user password (admin only)."""
    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await UserService.reset_password(db, user, body.new_password)
    return MessageResponse(message="Password reset successfully")


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(
    body: UserPasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Change own password."""
    user = await UserService.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    success = await UserService.change_password(db, user, body.old_password, body.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect",
        )

    return MessageResponse(message="Password changed successfully")


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get current user information."""
    user = await UserService.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return await UserService.to_response(db, user)


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update current user information (limited fields)."""
    user = await UserService.get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if body.role_id is not None or body.dept_id is not None or body.status is not None:
        if not await _is_admin_role(db, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your email and full name",
            )

    user = await UserService.update_user(db, user, body)
    return await UserService.to_response(db, user)


@router.get("/search", response_model=UserListResponse)
async def search_users(
    keyword: str | None = Query(None, description="Search keyword for username, email, full_name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    dept_id: UUID | None = None,
    role_id: UUID | None = None,
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Search users by keyword."""
    users, total = await UserService.search_users(
        db,
        keyword=keyword,
        skip=skip,
        limit=limit,
        dept_id=dept_id,
        role_id=role_id,
        status=status_filter,
    )
    return UserListResponse(
        users=[await UserService.to_response(db, u) for u in users],
        total=total,
    )


@router.post("/batch", response_model=UserBatchResponse)
async def batch_operation(
    body: UserBatchOperation,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("user:update")),
):
    """Batch operation on users (enable, disable, delete)."""
    success, failed = await UserService.batch_operation(
        db,
        user_ids=body.user_ids,
        operation=body.operation,
    )
    return UserBatchResponse(success=success, failed=failed)


@router.get("/statistics", response_model=UserStatistics)
async def get_user_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("user:read")),
):
    """Get user statistics."""
    return await UserService.get_statistics(db)
