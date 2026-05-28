"""资源配置路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Project, Resource
from app.schemas import (
    ResourceCreate,
    ResourceListResponse,
    ResourceResponse,
    ResourceUpdate,
)

router = APIRouter(prefix="/resources", tags=["资源配置"])


@router.get("", response_model=ResourceListResponse)
async def list_resources(
    project_id: UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    stmt = select(Resource)
    count_stmt = select(func.count(Resource.id))

    if project_id:
        stmt = stmt.where(Resource.project_id == project_id)
        count_stmt = count_stmt.where(Resource.project_id == project_id)

    result = await db.execute(stmt.offset(skip).limit(limit).order_by(Resource.created_at.desc()))
    resources = result.scalars().all()

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return ResourceListResponse(resources=[ResourceResponse.model_validate(r) for r in resources], total=total)


@router.post("", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    data: ResourceCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    project_result = await db.execute(select(Project).where(Project.id == data.project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    total_cost = None
    if data.unit_cost:
        total_cost = data.unit_cost * data.quantity

    resource = Resource(**data.model_dump(), total_cost=total_cost)
    db.add(resource)
    await db.flush()
    await db.refresh(resource)
    return ResourceResponse.model_validate(resource)


@router.put("/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: UUID,
    data: ResourceUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(Resource).where(Resource.id == resource_id))
    resource = result.scalar_one_or_none()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(resource, key, value)

    if resource.unit_cost:
        resource.total_cost = resource.unit_cost * resource.quantity

    await db.flush()
    await db.refresh(resource)
    return ResourceResponse.model_validate(resource)


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(Resource).where(Resource.id == resource_id))
    resource = result.scalar_one_or_none()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    await db.delete(resource)
