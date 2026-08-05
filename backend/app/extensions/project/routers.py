"""FastAPI routers for report project management."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.middleware import require_permission, with_data_scope
from app.extensions.database import get_db
from app.extensions.models import ReportProject, Role, User
from app.extensions.schemas import CurrentUser

from app.extensions.auth.unified_permissions import require_project_member, require_resource_permission
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


async def _load_project_scoped(
    db: AsyncSession,
    project_id: UUID,
    scope: FilterRule,
) -> ReportProject | None:
    """Load a project row by id ONLY if the given visibility scope permits it.

    EAI-CUSTOM (L1): mirrors ``_load_kb_scoped`` in knowledge routers — unifies
    by-id access with the list endpoint's ``with_data_scope("projects")``
    FilterRule so list and by-id enforce identical visibility (created_by OR
    member_projects, or allow_all for superadmin). Returns None if the project
    does not exist or is out of scope; callers raise 404 to avoid existence
    leakage (closes M6: non-members now get 404, not 403).
    """
    column_map = {"id": ReportProject.id, "created_by": ReportProject.created_by}
    q = select(ReportProject).where(ReportProject.id == project_id).where(scope.to_sqlalchemy(ReportProject, column_map))
    return (await db.execute(q)).scalar_one_or_none()


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
    scope: FilterRule = Depends(with_data_scope("projects")),
):
    # EAI-CUSTOM (L1): visibility is now driven by the data-scope FilterRule
    # (allow_all for superadmin; OR-union of the role's project scopes
    # otherwise). The legacy is_admin/user_id knobs are kept for the
    # scope=None path inside service.list_projects (used by other callers /
    # tests) but are no-ops here when a scope is supplied.
    items, total = await service.list_projects(
        db,
        user_id=user.id,
        status=status_filter,
        report_type=report_type,
        search=search,
        skip=skip,
        limit=limit,
        scope=scope,
    )
    return ProjectListResponse(items=items, total=total)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
    scope: FilterRule = Depends(with_data_scope("projects")),
):
    # EAI-CUSTOM (L1): by-id access now goes through the same scope FilterRule
    # as list (mirrors knowledge routers' _load_kb_scoped). Existence leak
    # closed: non-members get 404 (not 403) so out-of-scope ids are
    # indistinguishable from missing ones.
    project = await _load_project_scoped(db, project_id, scope)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

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
    # FK existence checks for template and workflow
    if body.template_id:
        from app.extensions.knowledge_factory.models import ExtractionTemplate

        tmpl = await db.get(ExtractionTemplate, body.template_id)
        if not tmpl:
            raise HTTPException(status_code=422, detail=f"Template {body.template_id} not found")
    if body.workflow_id:
        from app.extensions.workflow.models import WorkflowDefinition

        wf = await db.get(WorkflowDefinition, body.workflow_id)
        if not wf:
            raise HTTPException(status_code=422, detail=f"Workflow definition {body.workflow_id} not found")

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
                        proj.status = "draft"  # EAI-CUSTOM: canonical (ADR 2026-08-02)
                        await db.commit()
        except Exception as exc:  # Auto-start is best-effort; project is still created
            import logging as _logging

            _logging.getLogger(__name__).warning("Auto-start workflow failed for project %s: %r", project.id, exc)

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
        db,
        result.id,
        _user.id,
        "project.copied",
        target_type="project",
        target_id=str(body.source_project_id),
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


# EAI-CUSTOM: orthogonal archive bucket (ADR P5) — archive/unarchive keep the
# real spine status; only archived_at marks the bucket.
@router.post("/projects/{project_id}/archive", response_model=ProjectOut)
async def archive_project(
    project_id: UUID,
    _role: str = Depends(require_resource_permission("project:edit")),
    _user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    result = await service.archive_project(db, project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.post("/projects/{project_id}/unarchive", response_model=ProjectOut)
async def unarchive_project(
    project_id: UUID,
    _role: str = Depends(require_resource_permission("project:edit")),
    _user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    result = await service.unarchive_project(db, project_id)
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
            db,
            project_id,
            user.id,
            cookies=request.cookies,
            csrf_token=csrf_token,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── Sync project documents ──


@router.post("/projects/{project_id}/sync-docs")
async def sync_project_docs(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Sync sandbox output files from the user's project thread into AIDocument records.

    This allows files generated by the AI agent in the deer-flow conversation
    to appear in the project's Editor tab.
    """
    from app.extensions.models import ProjectMember

    # Find the user's thread for this project
    stmt = select(ProjectMember.thread_id).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id,
    )
    result = await db.execute(stmt)
    thread_id = result.scalar_one_or_none()
    if not thread_id:
        return {"synced": 0, "skipped": 0, "reason": "no_thread"}

    try:
        sync_result = await service.sync_project_thread_docs(
            db,
            project_id=project_id,
            user_id=user.id,
            thread_id=thread_id,
        )
        return sync_result
    except Exception as e:
        return {"synced": 0, "skipped": 0, "reason": str(e)}


@router.get("/projects/{project_id}/files")
async def get_project_files(
    project_id: UUID,
    request: Request,
    _member: CurrentUser = Depends(require_project_member()),
    db: AsyncSession = Depends(get_db),
):
    csrf_token = request.cookies.get("csrf_token")
    return await service.get_project_files(
        db,
        project_id,
        cookies=request.cookies,
        csrf_token=csrf_token,
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
    from app.extensions.auth.registry import get_permission_registry
    from app.extensions.auth.unified_permissions import (
        get_user_permissions,
        resolve_user_project_role,
    )

    # EAI-CUSTOM (I2): admin bypass via registry helper (yaml authority), not DB role row
    from app.extensions.auth.admin import is_superadmin

    is_admin = await is_superadmin(db, user.id)

    if is_admin:
        registry = get_permission_registry()
        all_perms: set[str] = set()
        for perms in registry.get_project_roles().values():
            all_perms.update(perms)
        return ProjectPermissionsOut(
            role="owner",
            permissions=sorted(all_perms),
            phase_duties=None,
            is_admin=True,
        )

    perms = await get_user_permissions(db, user.id, project_id, None)
    project_role = await resolve_user_project_role(db, user.id, project_id, None)
    return ProjectPermissionsOut(
        role=project_role.value if project_role else None,
        permissions=sorted(perms),
        phase_duties=None,
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
    await log_activity(db, project_id, _user.id, "member.added", target_type="member", target_id=str(body.user_id), detail=f"Added member with role '{body.role}'")


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
    db: AsyncSession,
    project_id: UUID,
    chapter_id: UUID,
    user: CurrentUser,
) -> None:
    """Check that the user can edit the given chapter within its phase scope.

    Owners and phase leads (managers) always pass. For other roles, the
    chapter must belong to the project's current phase (project.current_phase_node).
    """
    # Resolve project role
    # EAI-CUSTOM (I2): admin bypass via registry helper (yaml authority), not DB role row
    from app.extensions.auth.admin import is_superadmin

    if await is_superadmin(db, user.id):
        return

    from app.extensions.auth.unified_permissions import resolve_user_project_role
    from app.extensions.models.role_permission import ProjectRole

    project_role = await resolve_user_project_role(db, user.id, project_id)
    if project_role in (ProjectRole.OWNER, ProjectRole.PHASE_LEAD):
        return  # Owners and phase leads (managers) have full access

    # For non-owner/non-phase-lead: check phase scope
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
            detail=f"Cannot edit chapters in phase '{chapter.phase_node}'. Current active phase is '{project.current_phase_node}'.",
        )


class ChapterStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _canonical_status(cls, v: str) -> str:
        # EAI-CUSTOM: canonical chapter status (ADR 2026-08-02 P5) — strict check,
        # legacy normalize shim removed (fail-closed).
        from app.extensions.writing.state_machine import VALID_CHAPTER_TRANSITIONS

        if v not in VALID_CHAPTER_TRANSITIONS:
            raise ValueError(f"Invalid chapter status: {v!r}")
        return v


@router.post("/projects/{project_id}/chapters/{chapter_id}/open")
async def open_chapter_for_editing(
    project_id: UUID,
    chapter_id: UUID,
    _member: CurrentUser = Depends(require_project_member()),
    user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    """Open a chapter for editing in the collaborative editor.

    Creates (or finds) an AIDocument seeded with chapter content,
    so the BlockNote collaborative editor can edit it.
    Returns the document info needed by DocCollabView.

    EAI-CUSTOM (Task 12 follow-up): ``require_project_member()`` gates membership
    (superadmin-bypassing) on top of the in-handler ``_check_phase_access`` phase
    scope check — closes IDOR where a non-member without an active phase could pass.
    """
    await _check_phase_access(db, project_id, chapter_id, user)

    try:
        doc_info = await service.open_chapter_document(db, project_id, chapter_id, user_id=user.id)
        return doc_info
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/projects/{project_id}/chapters/{chapter_id}/status")
async def update_chapter_status(
    project_id: UUID,
    chapter_id: UUID,
    body: ChapterStatusUpdate,
    _role: str = Depends(require_resource_permission("chapter:write_any")),
    user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    """Update a chapter's status (pending → draft → reviewing → approved).

    EAI-CUSTOM: status is canonicalized + transition-validated (ADR 2026-08-02).
    Same-state writes are allowed as no-ops so legacy frontend flows that write
    an already-set status do not 400.
    """
    await _check_phase_access(db, project_id, chapter_id, user)

    from app.extensions.models import ProjectChapter
    from app.extensions.writing.state_machine import validate_chapter_transition

    cur = await db.execute(
        select(ProjectChapter.status).where(
            ProjectChapter.id == chapter_id,
            ProjectChapter.project_id == project_id,
        )
    )
    cur_status = cur.scalar_one_or_none()
    if cur_status is None:
        raise HTTPException(status_code=404, detail="Chapter not found")

    if body.status != cur_status:
        err = validate_chapter_transition(cur_status, body.status)
        if err:
            raise HTTPException(status_code=400, detail=err)

    stmt = ProjectChapter.__table__.update().where(ProjectChapter.id == chapter_id).where(ProjectChapter.project_id == project_id).values(status=body.status)
    result = await db.execute(stmt)
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Chapter not found")
    await log_activity(db, project_id, user.id, "chapter.status_updated", target_type="chapter", target_id=str(chapter_id), detail=f"Status changed to '{body.status}'")
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
    """DEPRECATED (2026-06-13): Use /projects/{id}/finalize instead."""
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use /projects/{id}/finalize instead.",
    )


@router.post("/projects/{project_id}/approval-action")
async def approval_action(
    project_id: UUID,
    body: ApprovalActionRequest,
    _role: str = Depends(require_resource_permission("approval:review")),
    user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    """DEPRECATED (2026-06-13): Use /projects/{id}/phase-reviews/{id}/action instead."""
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use /projects/{id}/phase-reviews/{id}/action instead.",
    )


@router.get("/projects/{project_id}/approval-status", response_model=ApprovalStatusOut)
async def get_approval_status(
    project_id: UUID,
    _role: str = Depends(require_resource_permission("approval:view")),
    db: AsyncSession = Depends(get_db),
):
    """DEPRECATED (2026-06-13): Use /projects/{id}/phase-reviews instead."""
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use /projects/{id}/phase-reviews instead.",
    )


# ── Phase Board ──


@router.get("/projects/{project_id}/phases/{phase_node}/board", response_model=PhaseBoardResponse)
async def get_phase_board(
    project_id: UUID,
    phase_node: str,
    _user: CurrentUser = Depends(require_project_member()),
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
    _user: CurrentUser = Depends(require_project_member()),
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
    stmt = select(ProjectChapter).where(ProjectChapter.project_id == project_id).order_by(ProjectChapter.sort_order)
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
                            scoped_chapters = [c for c in all_chapters if c.id in selected_ids or c.parent_id in selected_ids]
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
            if c.status in ("reviewing", "approved"):  # EAI-CUSTOM: canonical (ADR 2026-08-02)
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
    _user: CurrentUser = Depends(require_project_member()),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """Get activity log for a project — who did what when."""
    from app.extensions.models import ActivityLog, User as ExtUser

    stmt = select(ActivityLog, ExtUser.username, ExtUser.full_name).outerjoin(ExtUser, ActivityLog.user_id == ExtUser.id).where(ActivityLog.project_id == project_id).order_by(ActivityLog.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()

    # Total count
    count_stmt = select(func.count(ActivityLog.id)).where(ActivityLog.project_id == project_id)
    total = (await db.execute(count_stmt)).scalar() or 0

    items = []
    for log, username, full_name in rows:
        items.append(
            {
                "id": str(log.id),
                "project_id": str(log.project_id),
                "user_id": str(log.user_id) if log.user_id else None,
                "user_name": full_name or username or "System",
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "detail": log.detail,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
        )

    return {"items": items, "total": total}


# ── Phase Readiness ──


@router.get("/projects/{project_id}/phases/{phase_node}/readiness", response_model=PhaseReadinessResponse)
async def get_phase_readiness(
    project_id: UUID,
    phase_node: str,
    _user: CurrentUser = Depends(require_project_member()),
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


# ── Phase Completion (manual advancement) ──


class PhaseCompleteRequest(BaseModel):
    """Request to mark the current phase as complete and advance the workflow."""

    comment: str | None = None


@router.post("/projects/{project_id}/phase-complete")
async def complete_current_phase(
    project_id: UUID,
    body: PhaseCompleteRequest | None = None,
    _role: str = Depends(require_resource_permission("project:edit")),
    user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    """Signal the workflow that the current phase is complete.

    Sends a phase_complete signal to the running Temporal workflow,
    which triggers advance_phase and proceeds to the next node.

    EAI-CUSTOM (Task 12 follow-up): gated by ``project:edit`` (owner/phase_lead)
    to close IDOR — previously only ``system:access`` was checked.
    """
    from app.extensions.models import ReportProject
    from app.extensions.workflow.temporal.client import send_signal as _send_signal
    from app.extensions.workflow.models import WorkflowDefinition

    project = await db.get(ReportProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.current_phase_node:
        raise HTTPException(status_code=400, detail="No active phase to complete")

    current_phase = project.current_phase_node

    # Resolve phase label for logging/response
    phase_label = current_phase
    if project.workflow_id:
        defn = await db.get(WorkflowDefinition, project.workflow_id)
        if defn and defn.graph_json:
            for node in defn.graph_json.get("nodes", []):
                if node["id"] == current_phase:
                    phase_label = node.get("data", {}).get("label", current_phase)
                    break

    # Gate: verify all chapters are completed before allowing phase advance.
    # Matches the _check_phase_completion guard in the Temporal workflow
    # (_execute_phase / _execute_task) so the caller gets immediate feedback
    # instead of sending a signal that the workflow will reject.
    from app.extensions.models import ProjectChapter
    from sqlalchemy import func as _sf

    ch_stmt = (
        select(
            _sf.count(ProjectChapter.id).label("total"),
            _sf.sum(
                _sf.cast(
                    # EAI-CUSTOM: canonical (ADR 2026-08-02)
                    ProjectChapter.status.in_(["reviewing", "approved"]),
                    Integer,
                )
            ).label("done"),
        )
        .where(ProjectChapter.project_id == project_id)
        .where(ProjectChapter.level == 1)
    )
    ch_result = await db.execute(ch_stmt)
    ch_row = ch_result.one()
    chapter_total, chapter_done = (ch_row.total or 0), (ch_row.done or 0)
    if chapter_total > 0 and chapter_done < chapter_total:
        raise HTTPException(
            status_code=409,
            detail=(f"章节尚未全部完成 ({chapter_done}/{chapter_total})，共{chapter_total}章，已完成{chapter_done}章，请先完成所有章节的修改确认后再提交"),
        )

    try:
        await _send_signal(
            project_id=str(project_id),
            signal_name="phase_complete",
            args=[current_phase, {"comment": body.comment} if body and body.comment else {}],
        )
    except Exception as e:
        logger.exception("Failed to send phase_complete signal for project %s", project_id)
        raise HTTPException(status_code=503, detail=f"Workflow signal failed: {str(e)}")

    await log_activity(
        db,
        project_id,
        user.id,
        "phase.completed",
        target_type="phase",
        target_id=current_phase,
        detail=f"Marked phase '{phase_label}' as complete",
    )

    return {
        "status": "signal_sent",
        "project_id": str(project_id),
        "phase_node": current_phase,
        "phase_label": phase_label,
    }


class PhaseStatusResponse(BaseModel):
    """Current workflow phase status with available user actions."""

    project_id: str
    workflow_id: str | None = None
    current_phase_node: str | None = None
    current_phase_label: str | None = None
    workflow_status: str = "idle"
    available_actions: list[str] = []
    nodes: list[dict] = []


@router.get("/projects/{project_id}/phase-status", response_model=PhaseStatusResponse)
async def get_phase_status(
    project_id: UUID,
    _user: CurrentUser = Depends(require_project_member()),
    db: AsyncSession = Depends(get_db),
):
    """Get current workflow phase and available actions for the project.

    Returns the current phase label, workflow status, and a list of
    actions the user can take (e.g., 'complete_phase', 'start_writing').
    """
    from app.extensions.models import ReportProject
    from app.extensions.workflow.models import WorkflowDefinition

    project = await db.get(ReportProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    current_phase = project.current_phase_node
    phase_label = current_phase
    nodes: list[dict] = []
    available_actions: list[str] = []

    if project.workflow_id:
        defn = await db.get(WorkflowDefinition, project.workflow_id)
        if defn and defn.graph_json:
            graph = defn.graph_json

            # Auto-detect V2 format (mainGraph/subGraphs) and extract
            # phase-level nodes from the nested structure.
            if "mainGraph" in graph or "main_graph" in graph:
                source_graph = graph.get("mainGraph", graph.get("phaseGraph", {}))
            else:
                source_graph = graph

            # Resolve current phase label
            for node in source_graph.get("nodes", []):
                node_id = node["id"]
                node_type = node.get("type", "phase")
                node_label = node.get("data", {}).get("label", node_id)
                nodes.append(
                    {
                        "node_id": node_id,
                        "node_type": node_type,
                        "label": node_label,
                    }
                )
                if node_id == current_phase:
                    phase_label = node_label

            # Determine available actions based on current state
            if current_phase and project.status in ("draft", "in_review"):  # EAI-CUSTOM: canonical (ADR 2026-08-02)
                available_actions.append("complete_phase")
            if not current_phase and project.status in ("draft",):
                available_actions.append("start_workflow")

    # Determine workflow status
    # EAI-CUSTOM: canonical project status mapping (ADR 2026-08-02).
    wf_status = "idle"
    if project.status == "approved":
        wf_status = "completed"
    elif project.temporal_workflow_id:
        try:
            from app.extensions.workflow.temporal.client import get_workflow_status as _get_wf_status

            temporal_status = await _get_wf_status(str(project_id))
            if temporal_status:
                wf_status = temporal_status.get("status", "idle")
            else:
                wf_status = "running" if project.status in ("draft", "in_review") else "idle"
        except Exception:
            wf_status = "running" if project.status in ("draft", "in_review") else "idle"

    return PhaseStatusResponse(
        project_id=str(project_id),
        workflow_id=str(project.workflow_id) if project.workflow_id else None,
        current_phase_node=current_phase,
        current_phase_label=phase_label,
        workflow_status=wf_status,
        available_actions=available_actions,
        nodes=nodes,
    )


# ── Document lifecycle ──


class DocumentStatusUpdate(BaseModel):
    """Request to update an AIDocument status."""

    status: str  # draft | intermediate | review | final


@router.patch("/projects/{project_id}/documents/{doc_id}/status")
async def update_document_status(
    project_id: UUID,
    doc_id: UUID,
    body: DocumentStatusUpdate,
    _role: str = Depends(require_resource_permission("chapter:write_any")),
    _user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    """Update a project document's lifecycle status (draft/intermediate/review/final)."""
    valid_statuses = {"draft", "intermediate", "review", "final"}
    if body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    from app.extensions.models import AIDocument

    doc = await db.get(AIDocument, doc_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Document not found in this project")

    doc.status = body.status
    await db.commit()
    return {"doc_id": str(doc_id), "status": body.status, "updated": True}


class MergeDocumentsRequest(BaseModel):
    """Request to merge multiple AIDocuments into a final document."""

    doc_ids: list[UUID] = Field(..., min_length=2, description="Ordered list of document IDs to merge")
    title: str = Field(..., min_length=1, max_length=255, description="Title for the merged document")


@router.post("/projects/{project_id}/merge-docs", status_code=status.HTTP_201_CREATED)
async def merge_project_documents(
    project_id: UUID,
    body: MergeDocumentsRequest,
    _role: str = Depends(require_resource_permission("chapter:write_any")),
    user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    """Merge multiple intermediate AIDocuments into a single final document."""
    from uuid import uuid4
    from app.extensions.models import AIDocument

    # Validate all documents exist and belong to this project
    docs = []
    for doc_id in body.doc_ids:
        doc = await db.get(AIDocument, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
        if doc.project_id != project_id:
            raise HTTPException(status_code=400, detail=f"Document {doc_id} does not belong to this project")
        docs.append(doc)

    # Merge content with section separators
    merged_parts = []
    for doc in docs:
        if doc.content:
            merged_parts.append(doc.content.strip())
    merged_content = "\n\n---\n\n".join(merged_parts)

    # Create the merged document
    merged_doc = AIDocument(
        id=uuid4(),
        user_id=user.id,
        project_id=project_id,
        title=body.title,
        content=merged_content,
        folder="project-chapters",
        doc_type="document",
        status="final",
        parent_doc_id=None,
    )
    db.add(merged_doc)

    # Mark source documents as merged into this one
    for doc in docs:
        doc.merged_to_id = merged_doc.id
        doc.status = "intermediate"

    await db.commit()
    await db.refresh(merged_doc)

    return {
        "id": str(merged_doc.id),
        "title": merged_doc.title,
        "status": merged_doc.status,
        "size_bytes": len(merged_content.encode("utf-8")),
        "source_count": len(docs),
    }


# ── Project Statistics ──


class ProjectStatsResponse(BaseModel):
    """Aggregated project statistics for the overview cards."""

    document_count: int = 0
    document_total_size: int = 0
    chapter_count: int = 0
    active_chapter_count: int = 0
    completed_chapter_count: int = 0
    total_word_count: int = 0


@router.get("/projects/{project_id}/stats", response_model=ProjectStatsResponse)
async def get_project_stats(
    project_id: UUID,
    _user: CurrentUser = Depends(require_project_member()),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated project statistics from AIDocument and ProjectChapter tables.

    Returns document counts/sizes from the AIDocument table and chapter
    progress from the ProjectChapter table — all in a single query-efficient
    endpoint.
    """
    from app.extensions.models import AIDocument, ProjectChapter

    # Document stats from AIDocument table — include draft, final, and active
    # documents. Previously only counted status="final", which missed workflow-
    # synced draft reports and made the overview show 0 files.
    doc_stmt = select(
        func.count(AIDocument.id).label("count"),
        func.coalesce(func.sum(AIDocument.file_size), 0).label("total_size"),
    ).where(
        AIDocument.project_id == project_id,
        AIDocument.status.in_(["draft", "active", "final"]),
    )
    doc_result = await db.execute(doc_stmt)
    doc_row = doc_result.one()

    # Chapter stats from ProjectChapter table
    ch_stmt = select(
        func.count(ProjectChapter.id).label("total"),
        func.coalesce(func.sum(ProjectChapter.word_count_current), 0).label("words"),
        func.coalesce(
            func.sum(
                func.cast(
                    ProjectChapter.status.in_(["draft", "reviewing"]),  # EAI-CUSTOM: canonical (ADR P5)
                    Integer,
                )
            ),
            0,
        ).label("active_count"),
        func.coalesce(
            func.sum(
                func.cast(
                    # EAI-CUSTOM: canonical (ADR 2026-08-02)
                    ProjectChapter.status.in_(["reviewing", "approved"]),
                    Integer,
                )
            ),
            0,
        ).label("completed_count"),
    ).where(ProjectChapter.project_id == project_id)
    ch_result = await db.execute(ch_stmt)
    ch_row = ch_result.one()

    return ProjectStatsResponse(
        document_count=doc_row.count or 0,
        document_total_size=doc_row.total_size or 0,
        chapter_count=ch_row.total or 0,
        active_chapter_count=ch_row.active_count or 0,
        completed_chapter_count=ch_row.completed_count or 0,
        total_word_count=ch_row.words or 0,
    )


# ── Document Finalization ──


class FinalizeDocumentRequest(BaseModel):
    """Request to mark a document as final and sync chapter progress."""

    doc_id: UUID


class FinalizeDocumentResponse(BaseModel):
    """Response after finalizing a document."""

    doc_id: str
    status: str
    matched_chapters: int = 0
    unmatched_headings: list[str] = Field(default_factory=list)


@router.post("/projects/{project_id}/finalize-doc", response_model=FinalizeDocumentResponse)
async def finalize_document(
    project_id: UUID,
    body: FinalizeDocumentRequest,
    _role: str = Depends(require_resource_permission("chapter:write_any")),
    _user: CurrentUserWithAccess = None,
    db: AsyncSession = Depends(get_db),
):
    """Mark a document as final and parse its markdown to update chapter progress.

    Scans ## headings in the document content, fuzzy-matches them against
    the project's template chapter titles, and updates matched chapters'
    status to 'completed' with word counts from the section content.
    """
    from uuid import UUID as _UUID

    from app.extensions.models import AIDocument, ProjectChapter, ReportProject
    from app.extensions.knowledge_factory.models import ExtractionTemplate

    from .chapter_matching import (
        extract_headings,
        match_headings_to_chapters,
        split_by_headings,
    )

    doc = await db.get(AIDocument, body.doc_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Document not found in this project")

    # Resolve content: use doc.content if available, otherwise read from file_ref_path
    content = doc.content or ""
    if not content and doc.file_ref_path:
        from pathlib import Path

        file_path = Path(doc.file_ref_path)
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                pass

    if not content:
        doc.status = "final"
        await db.commit()
        return FinalizeDocumentResponse(doc_id=str(doc.id), status=doc.status, matched_chapters=0)

    # Set status to final
    doc.status = "final"
    await db.flush()

    # Collect template chapter titles for matching.
    # Template sections use arbitrary IDs (not UUIDs), so we match by title text
    # against actual ProjectChapter rows in the database.
    chapter_titles: list[dict] = []
    all_project_chapters: dict[str, str] = {}  # normalized_title -> chapter_uuid
    project = await db.get(ReportProject, project_id)
    if project and project.template_id:
        template = await db.get(ExtractionTemplate, project.template_id)
        if template and template.root_sections_json:
            sections_data = template.root_sections_json or {}
            section_list = sections_data.get("sections", [])

            def _collect(secs: list, result: list) -> None:
                for s in secs:
                    result.append({"id": s.get("id", ""), "title": s.get("title", "")})
                    _collect(s.get("children", []), result)

            _collect(section_list, chapter_titles)

        # Build a lookup from normalized chapter title -> actual DB UUID
        from .chapter_matching import _normalize

        ch_stmt = select(ProjectChapter).where(ProjectChapter.project_id == project_id)
        ch_result = await db.execute(ch_stmt)
        for ch in ch_result.scalars().all():
            all_project_chapters[_normalize(ch.title)] = str(ch.id)

    # Parse and match
    headings = extract_headings(content)
    sections = split_by_headings(content)
    matches = match_headings_to_chapters(headings, chapter_titles)

    # Update matched chapters by finding the DB row via normalized title match
    updated = 0
    for match in matches:
        heading = match["matched_heading"]
        section_text = sections.get(heading, "")
        word_count = len(section_text.encode("utf-8"))

        # Look up the actual chapter UUID from the project's chapters
        from .chapter_matching import _normalize

        chapter_uuid = all_project_chapters.get(_normalize(match["title"]))
        if not chapter_uuid:
            continue

        stmt = (
            ProjectChapter.__table__.update()
            .where(ProjectChapter.id == _UUID(chapter_uuid))
            .where(ProjectChapter.project_id == project_id)
            .values(
                status="approved",  # EAI-CUSTOM: canonical (ADR 2026-08-02)
                word_count_current=ProjectChapter.word_count_current + word_count,
            )
        )
        await db.execute(stmt)
        updated += 1

    await db.commit()
    await db.refresh(doc)

    matched_set = {m["matched_heading"] for m in matches}
    unmatched = [h for h in headings if h not in matched_set]

    return FinalizeDocumentResponse(
        doc_id=str(doc.id),
        status=doc.status,
        matched_chapters=updated,
        unmatched_headings=unmatched,
    )
