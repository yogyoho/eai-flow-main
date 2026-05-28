"""项目立项路由"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Project
from app.schemas import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["项目立项"])


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    keyword: Optional[str] = Query(None),
    project_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    dept_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    stmt = select(Project)
    count_stmt = select(func.count(Project.id))

    if keyword:
        stmt = stmt.where(Project.name.ilike(f"%{keyword}%") | Project.project_no.ilike(f"%{keyword}%"))
        count_stmt = count_stmt.where(Project.name.ilike(f"%{keyword}%") | Project.project_no.ilike(f"%{keyword}%"))
    if project_type:
        stmt = stmt.where(Project.project_type == project_type)
        count_stmt = count_stmt.where(Project.project_type == project_type)
    if status:
        stmt = stmt.where(Project.status == status)
        count_stmt = count_stmt.where(Project.status == status)
    if dept_id:
        stmt = stmt.where(Project.dept_id == dept_id)
        count_stmt = count_stmt.where(Project.dept_id == dept_id)

    result = await db.execute(stmt.offset(skip).limit(limit).order_by(Project.created_at.desc()))
    projects = result.scalars().all()

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return ProjectListResponse(projects=[ProjectResponse.model_validate(p) for p in projects], total=total)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    project = Project(**data.model_dump(), created_by=current_user.username)
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectResponse.model_validate(project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)
    await db.flush()
    await db.refresh(project)
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await db.delete(project)
