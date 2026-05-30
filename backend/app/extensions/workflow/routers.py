"""FastAPI routers for workflow definitions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

from app.extensions.models import ProjectChapter

from .models import ContentSource, WorkflowDefinition
from .schemas import (
    ContentSourceListResponse,
    ContentSourceOut,
    DAGValidationResult,
    WorkflowDefinitionCreate,
    WorkflowDefinitionListItem,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionOut,
    WorkflowDefinitionUpdate,
)
from .service import validate_dag
from .traceability import find_missing_sources

router = APIRouter(prefix="/api/extensions/workflow", tags=["workflow"])

CurrentUserWithAccess = Annotated[CurrentUser, Depends(require_permission("system:access"))]


# ── Definitions ──


@router.get("/definitions", response_model=WorkflowDefinitionListResponse)
async def list_definitions(
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
    is_template: bool | None = Query(None),
    report_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    stmt = select(WorkflowDefinition)
    count_stmt = select(func.count()).select_from(WorkflowDefinition)

    if is_template is not None:
        stmt = stmt.where(WorkflowDefinition.is_template == is_template)
        count_stmt = count_stmt.where(WorkflowDefinition.is_template == is_template)
    if report_type is not None:
        stmt = stmt.where(WorkflowDefinition.report_type == report_type)
        count_stmt = count_stmt.where(WorkflowDefinition.report_type == report_type)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(WorkflowDefinition.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return WorkflowDefinitionListResponse(
        items=[WorkflowDefinitionListItem.model_validate(w) for w in items],
        total=total,
    )


@router.get("/definitions/{definition_id}", response_model=WorkflowDefinitionOut)
async def get_definition(
    definition_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    result = await db.get(WorkflowDefinition, definition_id)
    if not result:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    return WorkflowDefinitionOut.model_validate(result)


@router.post("/definitions", response_model=WorkflowDefinitionOut, status_code=status.HTTP_201_CREATED)
async def create_definition(
    body: WorkflowDefinitionCreate,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    definition = WorkflowDefinition(
        name=body.name,
        report_type=body.report_type,
        graph_json=body.graph_json,
        is_template=body.is_template,
        created_by=user.id,
    )
    db.add(definition)
    await db.commit()
    await db.refresh(definition)
    return WorkflowDefinitionOut.model_validate(definition)


@router.put("/definitions/{definition_id}", response_model=WorkflowDefinitionOut)
async def update_definition(
    definition_id: UUID,
    body: WorkflowDefinitionUpdate,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    definition = await db.get(WorkflowDefinition, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow definition not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(definition, key, value)

    await db.commit()
    await db.refresh(definition)
    return WorkflowDefinitionOut.model_validate(definition)


@router.delete("/definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_definition(
    definition_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    definition = await db.get(WorkflowDefinition, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    await db.delete(definition)
    await db.commit()


@router.post("/definitions/validate", response_model=DAGValidationResult)
async def validate_definition(
    body: dict,
    _user: CurrentUserWithAccess,
):
    result = validate_dag(body)
    return DAGValidationResult(**result)


# ── Source Traceability ──


@router.get("/projects/{project_id}/chapters/{chapter_id}/sources", response_model=ContentSourceListResponse)
async def get_chapter_sources(
    project_id: UUID,
    chapter_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContentSource)
        .where(ContentSource.chapter_id == chapter_id)
        .order_by(ContentSource.block_index)
    )
    sources = result.scalars().all()
    stats: dict[str, int] = {}
    for s in sources:
        stats[s.source_type] = stats.get(s.source_type, 0) + 1
    return ContentSourceListResponse(
        sources=[ContentSourceOut.model_validate(s) for s in sources],
        stats=stats,
    )


@router.get("/projects/{project_id}/chapters/{chapter_id}/sources/missing")
async def get_missing_sources_endpoint(
    project_id: UUID,
    chapter_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    chapter = await db.get(ProjectChapter, chapter_id)
    if not chapter or not chapter.content:
        return {"missing": []}
    return {"missing": find_missing_sources(chapter.content)}
