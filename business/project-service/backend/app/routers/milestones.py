"""里程碑管理路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Milestone, Project
from app.schemas import (
    MilestoneCreate,
    MilestoneListResponse,
    MilestoneResponse,
    MilestoneUpdate,
)

router = APIRouter(prefix="/milestones", tags=["里程碑管理"])


@router.get("", response_model=MilestoneListResponse)
async def list_milestones(
    project_id: UUID | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    stmt = select(Milestone)
    count_stmt = select(func.count(Milestone.id))

    if project_id:
        stmt = stmt.where(Milestone.project_id == project_id)
        count_stmt = count_stmt.where(Milestone.project_id == project_id)
    if status:
        stmt = stmt.where(Milestone.status == status)
        count_stmt = count_stmt.where(Milestone.status == status)

    result = await db.execute(stmt.offset(skip).limit(limit).order_by(Milestone.created_at.desc()))
    milestones = result.scalars().all()

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return MilestoneListResponse(milestones=[MilestoneResponse.model_validate(m) for m in milestones], total=total)


@router.post("", response_model=MilestoneResponse, status_code=status.HTTP_201_CREATED)
async def create_milestone(
    data: MilestoneCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    project_result = await db.execute(select(Project).where(Project.id == data.project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    milestone = Milestone(**data.model_dump())
    db.add(milestone)
    await db.flush()
    await db.refresh(milestone)
    return MilestoneResponse.model_validate(milestone)


@router.put("/{milestone_id}", response_model=MilestoneResponse)
async def update_milestone(
    milestone_id: UUID,
    data: MilestoneUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(Milestone).where(Milestone.id == milestone_id))
    milestone = result.scalar_one_or_none()
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(milestone, key, value)
    await db.flush()
    await db.refresh(milestone)
    return MilestoneResponse.model_validate(milestone)
