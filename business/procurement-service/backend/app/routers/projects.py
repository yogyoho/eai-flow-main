"""招标项目 API 路由"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import TenderProject
from app.schemas import (
    MessageResponse,
    TenderProjectCreate,
    TenderProjectDetailResponse,
    TenderProjectListResponse,
    TenderProjectResponse,
    TenderProjectUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["招标项目管理"])


@router.get("", response_model=TenderProjectListResponse)
async def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    method: Optional[str] = None,
    procurement_type: Optional[str] = None,
    dept_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """查询招标项目列表"""
    stmt = select(TenderProject)
    if keyword:
        stmt = stmt.where(TenderProject.title.ilike(f"%{keyword}%"))
    if status:
        stmt = stmt.where(TenderProject.status == status)
    if method:
        stmt = stmt.where(TenderProject.procurement_method == method)
    if procurement_type:
        stmt = stmt.where(TenderProject.procurement_type == procurement_type)
    if dept_id:
        stmt = stmt.where(TenderProject.dept_id == dept_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.order_by(TenderProject.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    projects = list(result.scalars().all())

    return TenderProjectListResponse(
        projects=[TenderProjectResponse.model_validate(p) for p in projects],
        total=total,
    )


@router.post("", response_model=TenderProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: TenderProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    """创建招标项目"""
    if data.status not in ("draft", "pending_approval"):
        raise HTTPException(status_code=400, detail="新建项目状态必须为草稿或待审批")
    project = TenderProject(**data.model_dump(), created_by=current_user.sub)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return TenderProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=TenderProjectResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """获取项目详情"""
    stmt = select(TenderProject).where(TenderProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="招标项目不存在")
    return TenderProjectResponse.model_validate(project)


@router.put("/{project_id}", response_model=TenderProjectResponse)
async def update_project(
    project_id: UUID,
    data: TenderProjectUpdate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """更新招标项目"""
    stmt = select(TenderProject).where(TenderProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="招标项目不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return TenderProjectResponse.model_validate(project)


@router.delete("/{project_id}", response_model=MessageResponse)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """删除招标项目"""
    stmt = select(TenderProject).where(TenderProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="招标项目不存在")
    await db.delete(project)
    await db.commit()
    return MessageResponse(message="招标项目删除成功")


@router.post("/{project_id}/publish", response_model=TenderProjectResponse)
async def publish_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """发布招标公告"""
    stmt = select(TenderProject).where(TenderProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="招标项目不存在")
    if project.status not in ("draft", "pending_approval"):
        raise HTTPException(status_code=400, detail="当前状态不允许发布")
    project.status = "published"
    project.published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(project)
    return TenderProjectResponse.model_validate(project)
