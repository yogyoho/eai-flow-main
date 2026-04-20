"""Department routers for extensions module."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user, require_permission
from app.extensions.database import get_db
from app.extensions.dept.service import DepartmentService
from app.extensions.models import Department
from app.extensions.schemas import (
    CurrentUser,
    DepartmentCreate,
    DepartmentListResponse,
    DepartmentResponse,
    DepartmentTreeResponse,
    DepartmentUpdate,
    MessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/departments", tags=["Departments"])


@router.get("", response_model=DepartmentListResponse)
async def list_departments(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all departments in tree format."""
    tree = await DepartmentService.get_department_tree(db)
    total = len(tree)

    # Count all departments
    _, total_count = await DepartmentService.list_departments(db, skip=0, limit=10000)

    return DepartmentListResponse(departments=tree, total=total_count)


@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("department:create")),
):
    """Create a new department."""
    existing = await DepartmentService.get_department_by_name(db, data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department name already exists",
        )

    if data.parent_id:
        parent = await DepartmentService.get_department_by_id(db, data.parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent department not found",
            )

    department = await DepartmentService.create_department(db, data)
    return await DepartmentService.to_response(db, department)


@router.get("/{dept_id}", response_model=DepartmentResponse)
async def get_department(
    dept_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a specific department by ID."""
    department = await DepartmentService.get_department_by_id(db, dept_id)
    if not department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )
    return await DepartmentService.to_response(db, department)


@router.put("/{dept_id}", response_model=DepartmentResponse)
async def update_department(
    dept_id: UUID,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("department:update")),
):
    """Update a department."""
    department = await DepartmentService.get_department_by_id(db, dept_id)
    if not department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    if data.name:
        existing = await DepartmentService.get_department_by_name(db, data.name)
        if existing and existing.id != dept_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department name already exists",
            )

    if data.parent_id:
        if data.parent_id == dept_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department cannot be its own parent",
            )
        parent = await DepartmentService.get_department_by_id(db, data.parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent department not found",
            )

    department = await DepartmentService.update_department(db, department, data)
    return await DepartmentService.to_response(db, department)


@router.delete("/{dept_id}", response_model=MessageResponse)
async def delete_department(
    dept_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("department:delete")),
):
    """Delete a department."""
    department = await DepartmentService.get_department_by_id(db, dept_id)
    if not department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    # Check if department has children
    children = await DepartmentService.get_children(db, dept_id)
    if children:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete department with child departments. Please delete or reassign children first.",
        )

    await DepartmentService.delete_department(db, department)
    return MessageResponse(message="Department deleted successfully")


@router.get("/{dept_id}/children", response_model=list[DepartmentResponse])
async def get_department_children(
    dept_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get child departments of a specific department."""
    department = await DepartmentService.get_department_by_id(db, dept_id)
    if not department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    children = await DepartmentService.get_children(db, dept_id)
    return [await DepartmentService.to_response(db, child) for child in children]
