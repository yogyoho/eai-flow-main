"""FastAPI routers for report project management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.extensions.auth.middleware import require_permission
from app.extensions.schemas import CurrentUser

from .schemas import (
    MemberCreate,
    MilestoneListResponse,
    OutlineListResponse,
    OutlineUpdate,
    ProjectCreate,
    ProjectListResponse,
    ProjectOut,
    ProjectUpdate,
)
from . import service

router = APIRouter(prefix="/api/extensions/project", tags=["project"])

CurrentUserWithAccess = Annotated[CurrentUser, Depends(require_permission("system:access"))]


# ── Projects ──


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    _user: CurrentUserWithAccess,
    status: str | None = Query(None),
    report_type: str | None = Query(None),
    search: str | None = Query(None),
):
    items = await service.list_projects(status=status, report_type=report_type, search=search)
    return ProjectListResponse(items=items)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str,
    _user: CurrentUserWithAccess,
):
    result = await service.get_project(project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    _user: CurrentUserWithAccess,
):
    return await service.create_project(
        name=body.name,
        report_type=body.report_type,
        client=body.client,
        target_standard=body.target_standard,
        template_id=body.template_id,
        compliance_rule_set_id=body.compliance_rule_set_id,
        law_ids=body.law_ids,
        members=[m.model_dump() for m in body.members] if body.members else None,
        created_by=_user.user_id if hasattr(_user, "user_id") else "",
    )


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    _user: CurrentUserWithAccess,
):
    result = await service.update_project(project_id, **body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    _user: CurrentUserWithAccess,
):
    ok = await service.delete_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")


# ── Outlines ──


@router.get("/projects/{project_id}/outline", response_model=OutlineListResponse)
async def list_outlines(
    project_id: str,
    _user: CurrentUserWithAccess,
):
    items = await service.list_outlines(project_id)
    return OutlineListResponse(items=items)


@router.patch("/projects/{project_id}/outline/{outline_id}")
async def update_outline(
    project_id: str,
    outline_id: str,
    body: OutlineUpdate,
    _user: CurrentUserWithAccess,
):
    result = await service.update_outline(outline_id, **body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Outline not found")
    return result


# ── Members ──


@router.post("/projects/{project_id}/members", status_code=status.HTTP_204_NO_CONTENT)
async def add_member(
    project_id: str,
    body: MemberCreate,
    _user: CurrentUserWithAccess,
):
    ok = await service.add_member(project_id, body.user_id, body.role)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    project_id: str,
    user_id: str,
    _user: CurrentUserWithAccess,
):
    ok = await service.remove_member(project_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")


# ── Milestones ──


@router.get("/projects/{project_id}/milestones", response_model=MilestoneListResponse)
async def list_milestones(
    project_id: str,
    _user: CurrentUserWithAccess,
):
    items = await service.list_milestones(project_id)
    return MilestoneListResponse(items=items)
