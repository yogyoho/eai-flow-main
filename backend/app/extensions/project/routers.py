"""FastAPI routers for report project management (workflow-driven)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.models import Role
from app.extensions.schemas import CurrentUser

from .permissions import require_resource_permission
from .schemas import (
    AiActionRequest,
    AiActionResponse,
    ApprovalActionRequest,
    ApprovalStatusOut,
    ApprovalSubmitRequest,
    ChapterContentUpdate,
    MemberCreate,
    MemberOut,
    MyPermissionsResponse,
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
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    report_type: str | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    is_admin = False
    if user.role_id:
        role = await db.get(Role, user.role_id)
        if role and (role.is_system or "*" in (role.permissions or [])):
            is_admin = True

    items, total = await service.list_projects(
        db, user_id=user.id, is_admin=is_admin,
        status=status_filter, report_type=report_type, search=search, skip=skip, limit=limit,
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
    _role: str = Depends(require_resource_permission("project:edit")),
    _user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    result = await service.update_project(db, project_id, **body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    _role: str = Depends(require_resource_permission("project:delete")),
    _user: CurrentUserWithAccess = None,
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
    _role: str = Depends(require_resource_permission("outline:edit")),
    _user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    return await service.replace_outline(db, project_id, body.chapters)


@router.patch("/projects/{project_id}/chapters/{chapter_id}")
async def update_chapter(
    project_id: UUID,
    chapter_id: UUID,
    body: ChapterContentUpdate,
    _role: str = Depends(require_resource_permission("chapter:write_own")),
    user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    # Verify chapter ownership for non-managers
    if _role != "manager":
        chapter = await service.get_chapter(db, chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
        if chapter.assigned_to and chapter.assigned_to != user.id:
            raise HTTPException(status_code=403, detail="You can only edit chapters assigned to you")

    result = await service.update_chapter(db, chapter_id, **body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return result


@router.post("/projects/{project_id}/confirm-outline", response_model=ProjectOut)
async def confirm_outline(
    project_id: UUID,
    _role: str = Depends(require_resource_permission("project:advance")),
    _user: CurrentUserWithAccess = None,
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
    _role: str = Depends(require_resource_permission("member:add")),
    _user: CurrentUserWithAccess = None,
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
    _role: str = Depends(require_resource_permission("member:remove")),
    _user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    ok = await service.remove_member(db, project_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Member not found")


# ── Writing & Editing ──


@router.post("/projects/{project_id}/start-writing", response_model=StartWritingResponse)
async def start_writing(
    project_id: UUID,
    request: Request,
    _user: CurrentUserWithAccess,
    _role: str = Depends(require_resource_permission("ai:start_writing")),
    db: AsyncSession = Depends(get_db),
):
    """Create a project-level thread for AI writing (Stage 3) and return thread_id."""
    csrf_token = request.cookies.get("csrf_token")
    try:
        result = await service.start_writing(db, project_id, user_id=_user.id, cookies=request.cookies, csrf_token=csrf_token)
        return StartWritingResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/projects/{project_id}/chapters/{chapter_id}/start-editing", response_model=StartEditingResponse)
async def start_chapter_editing(
    project_id: UUID,
    chapter_id: UUID,
    _role: str = Depends(require_resource_permission("ai:start_editing")),
    user: CurrentUserWithAccess = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Create a chapter-level thread for collaborative editing (Stage 4)."""
    csrf_token = request.cookies.get("csrf_token")
    try:
        result = await service.start_chapter_editing(db, project_id, chapter_id, user_id=user.id, cookies=request.cookies, csrf_token=csrf_token)
        return StartEditingResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── AI Action ──


@router.post("/projects/{project_id}/ai-action", response_model=AiActionResponse)
async def execute_ai_action(
    project_id: UUID,
    body: AiActionRequest,
    _role: str = Depends(require_resource_permission("ai:toolbox")),
    user: CurrentUserWithAccess = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger an AI toolbox action (polish, expand, condense, format_check, etc.)."""
    csrf_token = request.cookies.get("csrf_token")
    try:
        result = await service.execute_ai_action(
            db,
            project_id,
            chapter_ids=body.chapter_ids,
            action=body.action,
            params=body.params,
            user_id=user.id,
            cookies=request.cookies,
            csrf_token=csrf_token,
        )
        return AiActionResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Permission query ---


@router.get("/projects/{project_id}/my-permissions", response_model=MyPermissionsResponse)
async def get_my_permissions(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    role_row = await db.get(Role, user.role_id) if user.role_id else None
    is_admin = role_row is not None and ("*" in (role_row.permissions or []) or role_row.is_system)
    return await service.get_my_permissions(db, project_id, user.id, is_admin=is_admin)


# --- Approval workflow ---


@router.post("/projects/{project_id}/submit-approval")
async def submit_approval(
    project_id: UUID,
    body: ApprovalSubmitRequest,
    _role: str = Depends(require_resource_permission("approval:submit")),
    db: AsyncSession = Depends(get_db),
    user: CurrentUserWithAccess = None,
):
    steps = [s.model_dump() for s in body.steps]
    return await service.submit_approval(db, project_id, user.id, steps)


@router.post("/projects/{project_id}/approval-action")
async def approval_action(
    project_id: UUID,
    body: ApprovalActionRequest,
    _role: str = Depends(require_resource_permission("approval:review")),
    user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    return await service.approval_action(db, project_id, body.workflow_id, user.id, body.action, body.comment)


@router.get("/projects/{project_id}/approval-status", response_model=ApprovalStatusOut)
async def get_approval_status(
    project_id: UUID,
    _role: str = Depends(require_resource_permission("approval:view")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_approval_status(db, project_id)


@router.get("/projects/{project_id}/approval-records")
async def get_approval_records(
    project_id: UUID,
    _role: str = Depends(require_resource_permission("approval:view")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_approval_status(db, project_id)
