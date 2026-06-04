"""FastAPI routers for report project management."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.models import Role
from app.extensions.schemas import CurrentUser

from .permissions import require_resource_permission
from .schemas import (
    ApprovalActionRequest,
    ApprovalStatusOut,
    ApprovalSubmitRequest,
    BatchAssignRequest,
    MemberCreate,
    MemberUpdate,
    PhaseBoardResponse,
    PhaseReadinessResponse,
    ProjectCopyFrom,
    ProjectCreate,
    ProjectListResponse,
    ProjectOut,
    ProjectPermissionsOut,
    ProjectUpdate,
)
from . import service

router = APIRouter(prefix="/api/extensions/project", tags=["project"])

CurrentUserWithAccess = Annotated[CurrentUser, Depends(require_permission("system:access"))]
ProjectCreator = Annotated[CurrentUser, Depends(require_permission("project:create"))]


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
    _user: ProjectCreator,
    db: AsyncSession = Depends(get_db),
):
    members_data = None
    if body.members:
        members_data = [m.model_dump() for m in body.members]

    project = await service.create_project(
        db,
        name=body.name,
        report_type=body.report_type,
        template_id=body.template_id,
        workflow_id=body.workflow_id,
        created_by=_user.id,
        members_data=members_data,
    )

    await log_activity(db, project.id, _user.id, "project.created", detail=f"Created project '{body.name}'")

    # Auto-start workflow if requested and workflow_id provided
    if body.auto_start_workflow and body.workflow_id and project.id:
        try:
            from app.extensions.workflow.temporal.client import start_workflow as _start_wf
            from app.extensions.workflow.models import WorkflowDefinition

            definition = await db.get(WorkflowDefinition, body.workflow_id)
            if definition and definition.graph_json:
                workflow_id_result = await _start_wf(
                    workflow_name="DynamicGraphWorkflow",
                    params={
                        "graph_json": definition.graph_json,
                        "project_id": str(project.id),
                    },
                )
                if workflow_id_result:
                    from app.extensions.models import ReportProject
                    proj = await db.get(ReportProject, project.id)
                    if proj:
                        proj.workflow_id = body.workflow_id
                        proj.temporal_workflow_id = workflow_id_result
                        proj.status = "in_progress"
                        await db.commit()
        except Exception:
            pass  # Auto-start is best-effort; project is still created

    return project


@router.post("/projects/copy-from", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def copy_project(
    body: ProjectCopyFrom,
    _user: ProjectCreator,
    db: AsyncSession = Depends(get_db),
):
    """Create a new project by copying structure from an existing one."""
    result = await service.copy_project(
        db,
        source_project_id=body.source_project_id,
        name=body.name,
        created_by=_user.id,
        copy_members=body.copy_members,
        copy_outline=body.copy_outline,
        copy_workflow=body.copy_workflow,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Source project not found")
    await log_activity(
        db, result.id, _user.id, "project.copied",
        target_type="project", target_id=str(body.source_project_id),
        detail=f"Copied from project as '{body.name}'",
    )
    return result


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


# ── Enter project (thread binding) ──


@router.post("/projects/{project_id}/enter")
async def enter_project(
    project_id: UUID,
    request: Request,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    csrf_token = request.cookies.get("csrf_token")
    try:
        result = await service.enter_project(
            db, project_id, user.id,
            cookies=request.cookies, csrf_token=csrf_token,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/projects/{project_id}/files")
async def get_project_files(
    project_id: UUID,
    request: Request,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    csrf_token = request.cookies.get("csrf_token")
    return await service.get_project_files(
        db, project_id, cookies=request.cookies, csrf_token=csrf_token,
    )


# ── My Permissions ──


@router.get("/projects/{project_id}/my-permissions", response_model=ProjectPermissionsOut)
async def get_my_permissions(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Get current user's effective permissions within a project.

    Returns permissions derived from:
    1. System Role.permissions (if user has a role)
    2. Project role (owner gets all, member gets filtered)
    3. Phase duties bonus (lead/writer/reviewer get extra permissions)
    """
    from app.extensions.models import ProjectMember, User
    from app.extensions.project.project_permissions import (
        PROJECT_PERMISSIONS,
        get_project_role_permissions,
    )

    is_admin = False
    system_role = None
    if user.role_id:
        role_obj = await db.get(Role, user.role_id)
        if role_obj:
            permissions = role_obj.permissions or []
            if "*" in permissions or role_obj.is_system:
                is_admin = True
            else:
                system_role = role_obj

    if is_admin:
        return ProjectPermissionsOut(
            role="owner",
            permissions=list(PROJECT_PERMISSIONS),
            phase_duties=None,
            is_admin=True,
        )

    # Look up project membership
    stmt = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id,
    )
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()

    if member is None:
        return ProjectPermissionsOut(role=None, permissions=[], phase_duties=None, is_admin=False)

    permissions = get_project_role_permissions(
        project_role=member.role,
        system_role=system_role,
        phase_duties=member.phase_duties,
    )

    return ProjectPermissionsOut(
        role=member.role,
        permissions=permissions,
        phase_duties=member.phase_duties,
        is_admin=False,
    )


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
    await log_activity(db, project_id, _user.id, "member.added", target_type="member", target_id=str(body.user_id),
                       detail=f"Added member with role '{body.role}'")


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
    await log_activity(db, project_id, _user.id, "member.removed", target_type="member", target_id=str(user_id))


@router.patch("/projects/{project_id}/members/{user_id}")
async def update_member(
    project_id: UUID,
    user_id: UUID,
    body: MemberUpdate,
    _role: str = Depends(require_resource_permission("member:add")),
    _user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    """Update a member's role and/or phase_duties."""
    from .schemas import VALID_MEMBER_ROLES

    if body.role is not None and body.role not in VALID_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {VALID_MEMBER_ROLES}")
    ok = await service.update_member(db, project_id, user_id, **body.model_dump(exclude_unset=True))
    if not ok:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"success": True}


# ── Chapter status ──


async def _check_phase_access(
    db: AsyncSession, project_id: UUID, chapter_id: UUID, user: CurrentUser,
) -> None:
    """Check that the user can edit the given chapter within its phase scope.

    Owners/managers always pass. For other roles, the chapter must belong
    to the project's current phase (project.current_phase_node).
    """
    # Resolve project role
    is_admin = False
    if user.role_id:
        role_obj = await db.get(Role, user.role_id)
        if role_obj and (role_obj.is_system or "*" in (role_obj.permissions or [])):
            is_admin = True

    if is_admin:
        return

    from .permissions import get_project_role
    from uuid import UUID as _UUID

    project_role = await get_project_role(db, project_id, user.id)
    if project_role in ("owner", "manager"):
        return  # Owners/managers have full access

    # For non-owner/manager: check phase scope
    from app.extensions.models import ReportProject, ProjectChapter

    project = await db.get(ReportProject, project_id)
    if not project or not project.current_phase_node:
        return  # No active workflow phase — allow (no phase restriction)

    chapter = await db.get(ProjectChapter, chapter_id)
    if not chapter:
        return  # Will be caught by the 404 check later

    # If chapter has a phase_node, it must match the current phase
    if chapter.phase_node and chapter.phase_node != project.current_phase_node:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot edit chapters in phase '{chapter.phase_node}'. "
                   f"Current active phase is '{project.current_phase_node}'.",
        )


class ChapterStatusUpdate(BaseModel):
    status: str


@router.patch("/projects/{project_id}/chapters/{chapter_id}/status")
async def update_chapter_status(
    project_id: UUID,
    chapter_id: UUID,
    body: ChapterStatusUpdate,
    _role: str = Depends(require_resource_permission("chapter:write_any")),
    user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    """Update a chapter's status (e.g. pending → writing → in_review → completed)."""
    await _check_phase_access(db, project_id, chapter_id, user)

    from app.extensions.models import ProjectChapter

    stmt = (
        ProjectChapter.__table__.update()
        .where(ProjectChapter.id == chapter_id)
        .where(ProjectChapter.project_id == project_id)
        .values(status=body.status)
    )
    result = await db.execute(stmt)
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Chapter not found")
    await log_activity(db, project_id, user.id, "chapter.status_updated",
                       target_type="chapter", target_id=str(chapter_id),
                       detail=f"Status changed to '{body.status}'")
    return {"success": True}


# ── Approval workflow ──


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
    return await service.approval_action(db, project_id, body.workflow_id, user.id, body.action, body.comment, is_admin=(_role == "owner"))


@router.get("/projects/{project_id}/approval-status", response_model=ApprovalStatusOut)
async def get_approval_status(
    project_id: UUID,
    _role: str = Depends(require_resource_permission("approval:view")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_approval_status(db, project_id)


# ── Phase Board ──


@router.get("/projects/{project_id}/phases/{phase_node}/board", response_model=PhaseBoardResponse)
async def get_phase_board(
    project_id: UUID,
    phase_node: str,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Get phase board data: chapters + members for a specific phase."""
    result = await service.get_phase_board(db, project_id, phase_node)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.get("/projects/{project_id}/phases/{phase_node}/completion")
async def get_phase_completion(
    project_id: UUID,
    phase_node: str,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Check phase completion status — how many chapters are done vs pending.

    Returns a summary that can be used as a gate before advancing the workflow.
    """
    from app.extensions.models import ReportProject, ProjectChapter
    from app.extensions.workflow.models import WorkflowDefinition

    project = await db.get(ReportProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all level-1 chapters for the project
    stmt = (
        select(ProjectChapter)
        .where(ProjectChapter.project_id == project_id)
        .order_by(ProjectChapter.sort_order)
    )
    result = await db.execute(stmt)
    all_chapters = result.scalars().all()

    # Filter by chapter_range from workflow graph
    scoped_chapters = all_chapters
    if project.workflow_id:
        defn = await db.get(WorkflowDefinition, project.workflow_id)
        if defn and defn.graph_json:
            for node in defn.graph_json.get("nodes", []):
                if node["id"] == phase_node:
                    cr = node.get("data", {}).get("chapter_range")
                    if cr and len(cr) == 2:
                        level1 = [c for c in all_chapters if c.level == 1]
                        start_idx, end_idx = cr
                        if 0 <= start_idx < len(level1) and 0 < end_idx <= len(level1):
                            selected_ids = {c.id for c in level1[start_idx:end_idx]}
                            scoped_chapters = [
                                c for c in all_chapters
                                if c.id in selected_ids or c.parent_id in selected_ids
                            ]
                    break

    # Also include chapters tagged with phase_node
    tagged = [c for c in all_chapters if c.phase_node == phase_node]
    tagged_ids = {c.id for c in tagged}
    all_scoped_ids = tagged_ids | {c.id for c in scoped_chapters}

    # Get leaf chapters (those without children) for status counting
    parent_ids = {c.parent_id for c in all_chapters if c.parent_id}
    leaf_chapter_ids = all_scoped_ids - parent_ids

    # Count completion
    total = len(leaf_chapter_ids)
    completed = 0
    pending = 0
    incomplete: list[dict] = []

    for c in all_chapters:
        if c.id in leaf_chapter_ids:
            if c.status in ("completed", "approved"):
                completed += 1
            else:
                pending += 1
                incomplete.append({"id": str(c.id), "title": c.title, "status": c.status})

    ready = total > 0 and pending == 0

    return {
        "phase_node": phase_node,
        "total": total,
        "completed": completed,
        "pending": pending,
        "ready": ready,
        "completion_percentage": round(completed / total * 100, 1) if total > 0 else 0,
        "incomplete_chapters": incomplete,
    }


@router.post("/projects/{project_id}/phases/{phase_node}/batch-assign")
async def batch_assign(
    project_id: UUID,
    phase_node: str,
    body: BatchAssignRequest,
    _role: str = Depends(require_resource_permission("chapter:write_any")),
    _user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    """Batch assign chapters to users within a phase."""
    return await service.batch_assign_chapters(db, project_id, body.assignments)


# ── Activity Log ──


async def log_activity(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID | None,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: str | None = None,
) -> None:
    """Record an activity log entry. Call this from endpoints that perform meaningful actions."""
    from app.extensions.models import ActivityLog

    entry = ActivityLog(
        project_id=project_id,
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
    db.add(entry)


@router.get("/projects/{project_id}/activities")
async def get_project_activities(
    project_id: UUID,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """Get activity log for a project — who did what when."""
    from app.extensions.models import ActivityLog, User as ExtUser

    stmt = (
        select(ActivityLog, ExtUser.username, ExtUser.full_name)
        .outerjoin(ExtUser, ActivityLog.user_id == ExtUser.id)
        .where(ActivityLog.project_id == project_id)
        .order_by(ActivityLog.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Total count
    count_stmt = select(func.count(ActivityLog.id)).where(ActivityLog.project_id == project_id)
    total = (await db.execute(count_stmt)).scalar() or 0

    items = []
    for log, username, full_name in rows:
        items.append({
            "id": str(log.id),
            "project_id": str(log.project_id),
            "user_id": str(log.user_id) if log.user_id else None,
            "user_name": full_name or username or "System",
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "detail": log.detail,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })

    return {"items": items, "total": total}


# ── Phase Readiness ──


@router.get("/projects/{project_id}/phases/{phase_node}/readiness", response_model=PhaseReadinessResponse)
async def get_phase_readiness(
    project_id: UUID,
    phase_node: str,
    _user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Check if all required roles for a phase are filled by project members."""
    from .slot_filling import check_phase_readiness

    return await check_phase_readiness(db, project_id, phase_node)


@router.get("/projects/{project_id}/approval-records")
async def get_approval_records(
    project_id: UUID,
    _role: str = Depends(require_resource_permission("approval:view")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_approval_status(db, project_id)
