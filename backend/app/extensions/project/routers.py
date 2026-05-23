"""FastAPI routers for report project management (workflow-driven)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

from .schemas import (
    ApprovalActionRequest,
    ChapterContentUpdate,
    MemberCreate,
    MemberOut,
    OutlineBatchUpdate,
    ProjectCreate,
    ProjectListResponse,
    ProjectOut,
    ProjectUpdate,
    StartEditingResponse,
    StartWritingResponse,
)
from . import service

router = APIRouter(prefix="/api/extensions/project", tags=["project"])

CurrentUserWithAccess = Annotated[CurrentUser, Depends(require_permission("system:access"))]


# ── Projects ──


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    report_type: str | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    items, total = await service.list_projects(
        db, status=status_filter, report_type=report_type, search=search, skip=skip, limit=limit,
    )
    return ProjectListResponse(items=items, total=total)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    result = await service.get_project(db, project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    return await service.create_project(
        db,
        name=body.name,
        report_type=body.report_type,
        template_id=body.template_id,
        created_by=_user.id,
    )


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    result = await service.update_project(db, project_id, **body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    ok = await service.delete_project(db, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")


# ── Outline ──


@router.get("/projects/{project_id}/outline")
async def get_outline(
    project_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    return await service.get_outline_tree(db, project_id)


@router.put("/projects/{project_id}/outline")
async def replace_outline(
    project_id: UUID,
    body: OutlineBatchUpdate,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    return await service.replace_outline(db, project_id, body.chapters)


@router.patch("/projects/{project_id}/chapters/{chapter_id}")
async def update_chapter(
    project_id: UUID,
    chapter_id: UUID,
    body: ChapterContentUpdate,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    result = await service.update_chapter(db, chapter_id, **body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return result


@router.post("/projects/{project_id}/confirm-outline", response_model=ProjectOut)
async def confirm_outline(
    project_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    result = await service.confirm_outline(db, project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


# ── Members ──


@router.post("/projects/{project_id}/members", status_code=status.HTTP_204_NO_CONTENT)
async def add_member(
    project_id: UUID,
    body: MemberCreate,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    ok = await service.add_member(db, project_id, body.user_id, body.role)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    project_id: UUID,
    user_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    ok = await service.remove_member(db, project_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Member not found")


# ── Writing & Editing ──


@router.post("/projects/{project_id}/start-writing", response_model=StartWritingResponse)
async def start_writing(
    project_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Create a project-level thread for AI writing (Stage 3) and return thread_id."""
    try:
        result = await service.start_writing(db, project_id, user_id=_user.id)
        return StartWritingResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/projects/{project_id}/chapters/{chapter_id}/start-editing", response_model=StartEditingResponse)
async def start_chapter_editing(
    project_id: UUID,
    chapter_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Create a chapter-level thread for collaborative editing (Stage 4)."""
    try:
        result = await service.start_chapter_editing(db, project_id, chapter_id, user_id=_user.id)
        return StartEditingResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
