"""User-Department routers for extensions module."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser
from app.extensions.user_department.service import UserDepartmentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/users/{user_id}/departments", tags=["User Departments"])


@router.get("")
async def get_user_departments(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("user:read")),
) -> dict:
    """Get all departments for a user."""
    dept_ids, primary_dept_id = await UserDepartmentService.get_user_all_dept_ids(db, user_id)
    return {"dept_ids": dept_ids, "primary_dept_id": primary_dept_id}


@router.put("")
async def update_user_departments(
    user_id: UUID,
    dept_ids: list[UUID],
    primary_dept_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("user:update")),
) -> dict:
    """Update user's department associations."""
    if not dept_ids:
        await UserDepartmentService.update_user_departments(db, user_id, [])
    else:
        await UserDepartmentService.update_user_departments(db, user_id, dept_ids, primary_dept_id)

    dept_ids, primary_dept_id = await UserDepartmentService.get_user_all_dept_ids(db, user_id)
    return {"dept_ids": dept_ids, "primary_dept_id": primary_dept_id}


@router.post("/{dept_id}")
async def add_user_to_department(
    user_id: UUID,
    dept_id: UUID,
    is_primary: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("user:update")),
) -> dict:
    """Add user to a department."""
    await UserDepartmentService.add_user_to_dept(db, user_id, dept_id, is_primary)
    dept_ids, primary_dept_id = await UserDepartmentService.get_user_all_dept_ids(db, user_id)
    return {"dept_ids": dept_ids, "primary_dept_id": primary_dept_id}


@router.delete("/{dept_id}")
async def remove_user_from_department(
    user_id: UUID,
    dept_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("user:update")),
) -> dict:
    """Remove user from a department."""
    removed = await UserDepartmentService.remove_user_from_dept(db, user_id, dept_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Association not found")
    dept_ids, primary_dept_id = await UserDepartmentService.get_user_all_dept_ids(db, user_id)
    return {"dept_ids": dept_ids, "primary_dept_id": primary_dept_id}


@router.put("/primary/{dept_id}")
async def set_primary_department(
    user_id: UUID,
    dept_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("user:update")),
) -> dict:
    """Set a department as the primary department for a user."""
    association = await UserDepartmentService.get_association(db, user_id, dept_id)
    if not association:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not in this department")

    await UserDepartmentService.set_primary_dept(db, user_id, dept_id)
    dept_ids, primary_dept_id = await UserDepartmentService.get_user_all_dept_ids(db, user_id)
    return {"dept_ids": dept_ids, "primary_dept_id": primary_dept_id}
