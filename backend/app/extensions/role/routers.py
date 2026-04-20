"""Role routers for extensions module."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.models import User
from app.extensions.role.service import RoleService
from app.extensions.schemas import (
    CurrentUser,
    MessageResponse,
    RoleAssignmentInfo,
    RoleCopy,
    RoleCreate,
    RoleListResponse,
    RoleResponse,
    RoleUpdate,
)
from app.extensions.user.service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/roles", tags=["Roles"])


@router.get("", response_model=RoleListResponse)
async def list_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:read")),
):
    """List all roles."""
    roles, total = await RoleService.list_roles(db, skip=skip, limit=limit)
    return RoleListResponse(roles=[await RoleService.to_response(db, r) for r in roles], total=total)


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    data: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:create")),
):
    """Create a new role."""
    existing = await RoleService.get_role_by_code(db, data.code)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role code already exists")
    role = await RoleService.create_role(db, data)
    return await RoleService.to_response(db, role)


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:read")),
):
    """Get a specific role."""
    role = await RoleService.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return await RoleService.to_response(db, role)


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: UUID,
    data: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:update")),
):
    """Update a role."""
    role = await RoleService.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify system role")
    role = await RoleService.update_role(db, role, data)
    return await RoleService.to_response(db, role)


@router.delete("/{role_id}", response_model=MessageResponse)
async def delete_role(
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:delete")),
):
    """Delete a role."""
    role = await RoleService.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete system role")

    user_count = await RoleService.get_role_user_count(db, role_id)
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete role with {user_count} assigned users. Please reassign users first.",
        )

    await RoleService.delete_role(db, role)
    return MessageResponse(message="Role deleted successfully")


@router.post("/{role_id}/copy", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def copy_role(
    role_id: UUID,
    data: RoleCopy,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:create")),
):
    """Copy a role with new name and code."""
    role = await RoleService.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    existing = await RoleService.get_role_by_code(db, data.new_code)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role code already exists")

    new_role = await RoleService.copy_role(db, role, data)
    return await RoleService.to_response(db, new_role)


@router.get("/{role_id}/users", response_model=dict)
async def get_role_users(
    role_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:read")),
):
    """Get users assigned to a specific role."""
    role = await RoleService.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    query = select(User).where(User.role_id == role_id).offset(skip).limit(limit).order_by(User.created_at.desc())
    result = await db.execute(query)
    users = result.scalars().all()

    count_query = select(func.count(User.id)).where(User.role_id == role_id)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return {
        "role": await RoleService.to_response(db, role),
        "users": [await UserService.to_response(db, u) for u in users],
        "total": total,
    }


@router.get("/assignments", response_model=list[RoleAssignmentInfo])
async def get_role_assignments(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("role:read")),
):
    """Get all roles with their user counts."""
    return await RoleService.get_all_role_assignments(db)
