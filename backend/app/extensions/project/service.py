"""Database-backed service for report project management."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import (
    ApprovalRecord,
    ApprovalWorkflow,
    ProjectChapter,
    ProjectMember,
    ReportProject,
    User,
)

from .schemas import (
    ChapterOut,
    MemberOut,
    ProjectListItem,
    ProjectOut,
)


# ── Helpers ──


async def _resolve_username(db: AsyncSession, user_id) -> str:
    user = await db.get(User, user_id)
    return user.username if user else str(user_id)


def _build_chapter_tree(chapters: list[ProjectChapter], assigned_names: dict) -> list[ChapterOut]:
    by_id = {c.id: c for c in chapters}
    children_map: dict = {c.id: [] for c in chapters}
    roots = []

    for c in chapters:
        if c.parent_id and c.parent_id in by_id:
            children_map[c.parent_id].append(c)
        else:
            roots.append(c)

    def _to_out(c: ProjectChapter) -> ChapterOut:
        child_outs = [_to_out(child) for child in sorted(children_map.get(c.id, []), key=lambda x: x.sort_order)]
        return ChapterOut(
            id=c.id,
            project_id=c.project_id,
            parent_id=c.parent_id,
            title=c.title,
            level=c.level,
            sort_order=c.sort_order,
            status=c.status,
            content=c.content,
            assigned_to=c.assigned_to,
            assigned_name=assigned_names.get(c.assigned_to),
            word_count_target=c.word_count_target,
            word_count_current=c.word_count_current,
            purpose=c.purpose,
            generation_hint=c.generation_hint,
            children=child_outs,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )

    return [_to_out(r) for r in sorted(roots, key=lambda x: x.sort_order)]


async def _get_assigned_names(db: AsyncSession, chapters: list[ProjectChapter]) -> dict:
    user_ids = {c.assigned_to for c in chapters if c.assigned_to}
    if not user_ids:
        return {}
    stmt = select(User.id, User.username).where(User.id.in_(user_ids))
    result = await db.execute(stmt)
    return dict(result.all())


async def _get_project_or_404(db: AsyncSession, project_id):
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise ValueError("Project not found")
    return project


async def _create_deerflow_thread(metadata: dict, cookies: dict | None = None, csrf_token: str | None = None) -> str:
    import httpx
    import os

    gateway_port = os.environ.get("GATEWAY_PORT", "8001")
    thread_id = str(__import__("uuid").uuid4())

    headers = {}
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token

    async with httpx.AsyncClient(cookies=cookies) as client:
        resp = await client.post(
            f"http://localhost:{gateway_port}/api/threads",
            json={"thread_id": thread_id, "metadata": metadata},
            headers=headers,
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["thread_id"]


def _write_project_context(thread_id: str, user_id: str, metadata: dict) -> None:
    """Write project context to the thread directory for DynamicContextMiddleware."""
    import json

    from deerflow.config.paths import get_paths

    paths = get_paths()
    thread_dir = paths.thread_dir(thread_id, user_id=user_id)
    thread_dir.mkdir(parents=True, exist_ok=True)
    context_file = thread_dir / "project-context.json"
    context_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))


# ── Public API ──


async def list_projects(
    db: AsyncSession,
    *,
    user_id: object | None = None,
    is_admin: bool = False,
    status: str | None = None,
    report_type: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[ProjectListItem], int]:
    query = select(ReportProject).where(ReportProject.status != "archived")
    count_query = select(func.count(ReportProject.id)).where(ReportProject.status != "archived")

    if user_id and not is_admin:
        member_exists = (
            select(ProjectMember.id)
            .where(ProjectMember.project_id == ReportProject.id, ProjectMember.user_id == user_id)
            .correlate(ReportProject)
            .exists()
        )
        user_filter = or_(ReportProject.created_by == user_id, member_exists)
        query = query.where(user_filter)
        count_query = count_query.where(user_filter)

    if status:
        query = query.where(ReportProject.status == status)
        count_query = count_query.where(ReportProject.status == status)
    if report_type:
        query = query.where(ReportProject.report_type == report_type)
        count_query = count_query.where(ReportProject.report_type == report_type)
    if search:
        pattern = f"%{search}%"
        query = query.where(ReportProject.name.ilike(pattern))
        count_query = count_query.where(ReportProject.name.ilike(pattern))

    query = query.order_by(ReportProject.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    projects = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    items = []
    for p in projects:
        chapter_count_stmt = select(func.count(ProjectChapter.id)).where(ProjectChapter.project_id == p.id)
        cc = (await db.execute(chapter_count_stmt)).scalar() or 0

        member_count_stmt = select(func.count(ProjectMember.id)).where(ProjectMember.project_id == p.id)
        mc = (await db.execute(member_count_stmt)).scalar() or 0

        template_name = None
        if p.template_id:
            from app.extensions.knowledge_factory.models import ExtractionTemplate
            tmpl = await db.get(ExtractionTemplate, p.template_id)
            if tmpl:
                template_name = tmpl.name

        items.append(ProjectListItem(
            id=p.id,
            name=p.name,
            report_type=p.report_type,
            status=p.status,
            template_id=p.template_id,
            template_name=template_name,
            chapter_count=cc,
            member_count=mc,
            created_by=p.created_by,
            created_at=p.created_at,
            updated_at=p.updated_at,
        ))

    return items, total


async def get_project(db: AsyncSession, project_id) -> ProjectOut | None:
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        return None

    chap_stmt = select(ProjectChapter).where(ProjectChapter.project_id == project_id)
    chap_result = await db.execute(chap_stmt)
    chapters = list(chap_result.scalars().all())
    assigned_names = await _get_assigned_names(db, chapters)
    chapter_tree = _build_chapter_tree(chapters, assigned_names)

    mem_stmt = select(ProjectMember).where(ProjectMember.project_id == project_id)
    mem_result = await db.execute(mem_stmt)
    members = []
    for m in mem_result.scalars().all():
        members.append(MemberOut(
            id=m.id,
            project_id=m.project_id,
            user_id=m.user_id,
            username=await _resolve_username(db, m.user_id),
            role=m.role,
            created_at=m.created_at,
        ))

    return ProjectOut(
        id=project.id,
        name=project.name,
        report_type=project.report_type,
        template_id=project.template_id,
        status=project.status,
        thread_id=project.thread_id,
        created_by=project.created_by,
        members=members,
        chapters=chapter_tree,
        chapter_count=len(chapters),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


async def enter_project(
    db: AsyncSession,
    project_id,
    user_id,
    *,
    cookies: dict | None = None,
    csrf_token: str | None = None,
) -> dict:
    project = await _get_project_or_404(db, project_id)

    stmt = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    )
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()
    if not member:
        raise ValueError("Not a project member")

    if member.thread_id:
        return {"thread_id": member.thread_id, "project_id": str(project_id)}

    template_context = {}
    if project.template_id:
        from app.extensions.knowledge_factory.models import ExtractionTemplate
        tmpl = await db.get(ExtractionTemplate, project.template_id)
        if tmpl:
            template_context = {
                "template_name": tmpl.name,
                "domain": tmpl.domain,
                "sections": tmpl.root_sections_json,
            }

    metadata = {
        "project_id": str(project_id),
        "type": "report_project",
        "report_type": project.report_type,
        "project_name": project.name,
        "template": template_context,
    }

    thread_id = await _create_deerflow_thread(metadata, cookies=cookies, csrf_token=csrf_token)
    member.thread_id = thread_id
    await db.flush()

    _write_project_context(thread_id, str(user_id), metadata)

    return {"thread_id": thread_id, "project_id": str(project_id)}


async def create_project(
    db: AsyncSession,
    *,
    name: str,
    report_type: str,
    created_by=None,
    template_id=None,
) -> ProjectOut:
    has_template = bool(template_id)
    project = ReportProject(
        name=name,
        report_type=report_type,
        created_by=created_by,
        template_id=template_id,
        status="active",
    )
    db.add(project)
    await db.flush()

    if created_by:
        member = ProjectMember(
            project_id=project.id,
            user_id=created_by,
            role="owner",
        )
        db.add(member)
        await db.flush()

    if template_id:
        await _import_template_outline(db, project.id, template_id)

    return await get_project(db, project.id)


async def _import_template_outline(db: AsyncSession, project_id, template_id) -> None:
    from app.extensions.knowledge_factory.models import ExtractionTemplate

    template = await db.get(ExtractionTemplate, template_id)
    if not template:
        return

    sections_data = template.root_sections_json or {}
    section_list = sections_data.get("sections", [])
    if not section_list:
        return

    async def _create_from_section(sec: dict, parent_id=None, level: int = 1, order: int = 0) -> None:
        chapter = ProjectChapter(
            project_id=project_id,
            parent_id=parent_id,
            title=sec.get("title", "Untitled"),
            level=level,
            sort_order=order,
            purpose=sec.get("purpose"),
            generation_hint=sec.get("generation_hint"),
            word_count_target=sec.get("content_contract", {}).get("min_word_count", 3000) if isinstance(sec.get("content_contract"), dict) else 3000,
        )
        db.add(chapter)
        await db.flush()

        for j, child in enumerate(sec.get("children", [])):
            await _create_from_section(child, parent_id=chapter.id, level=level + 1, order=j)

    for i, sec in enumerate(section_list):
        await _create_from_section(sec, order=i)


async def update_project(db: AsyncSession, project_id, **kwargs) -> ProjectOut | None:
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        return None

    for k, v in kwargs.items():
        if v is not None:
            setattr(project, k, v)

    await db.flush()
    return await get_project(db, project_id)


async def delete_project(db: AsyncSession, project_id) -> bool:
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        return False
    await db.delete(project)
    return True


# ── Members ──


async def add_member(db: AsyncSession, project_id, user_id, role: str = "member") -> bool:
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        return False

    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        return True

    member = ProjectMember(project_id=project_id, user_id=user_id, role=role)
    db.add(member)
    await db.flush()
    return True


async def remove_member(db: AsyncSession, project_id, user_id) -> bool:
    stmt = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    )
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()
    if not member:
        return False
    await db.delete(member)
    return True


# ── Approval workflow ──


async def submit_approval(
    db: AsyncSession, project_id: UUID, manager_id: UUID,
    steps: list[dict],
) -> dict:
    project = await _get_project_or_404(db, project_id)

    existing = await db.execute(
        select(ApprovalWorkflow).where(ApprovalWorkflow.project_id == project_id)
    )
    for wf in existing.scalars().all():
        await db.delete(wf)

    for step_data in steps:
        workflow = ApprovalWorkflow(
            project_id=project_id,
            step_order=step_data["step_order"],
            step_name=step_data["step_name"],
            role_required="reviewer",
            reviewer_id=step_data["reviewer_id"],
            status="pending",
        )
        db.add(workflow)

    await db.flush()
    return {"project_id": project_id, "status": "submitted", "step_count": len(steps)}


async def approval_action(
    db: AsyncSession, project_id: UUID, workflow_id: UUID,
    reviewer_id: UUID, action: str, comment: str | None,
) -> dict:
    workflow = await db.get(ApprovalWorkflow, workflow_id)
    if not workflow or workflow.project_id != project_id:
        raise HTTPException(status_code=404, detail="审核步骤不存在")

    if workflow.reviewer_id != reviewer_id:
        raise HTTPException(status_code=403, detail="您不是此步骤的指定审核人")

    if workflow.status != "pending":
        raise HTTPException(status_code=400, detail="此步骤已处理")

    record = ApprovalRecord(
        workflow_id=workflow_id,
        project_id=project_id,
        action=action,
        reviewer_id=reviewer_id,
        comment=comment,
    )
    db.add(record)

    if action == "approve":
        workflow.status = "approved"
        all_steps = await db.execute(
            select(ApprovalWorkflow)
            .where(ApprovalWorkflow.project_id == project_id)
            .order_by(ApprovalWorkflow.step_order)
        )
        steps = all_steps.scalars().all()
        if all(s.status == "approved" for s in steps):
            project = await _get_project_or_404(db, project_id)
            project.status = "completed"

    elif action == "reject":
        workflow.status = "rejected"
        subsequent = await db.execute(
            select(ApprovalWorkflow).where(
                ApprovalWorkflow.project_id == project_id,
                ApprovalWorkflow.step_order > workflow.step_order,
            )
        )
        for s in subsequent.scalars().all():
            s.status = "pending"

    await db.flush()
    return {"workflow_id": workflow_id, "action": action}


async def get_approval_status(db: AsyncSession, project_id: UUID) -> dict:
    all_steps = await db.execute(
        select(ApprovalWorkflow)
        .where(ApprovalWorkflow.project_id == project_id)
        .order_by(ApprovalWorkflow.step_order)
    )
    steps = all_steps.scalars().all()

    current_step = None
    for s in steps:
        if s.status == "pending":
            current_step = s.step_order
            break

    return {
        "project_id": project_id,
        "current_step": current_step,
        "total_steps": len(steps),
        "steps": steps,
        "all_approved": len(steps) > 0 and all(s.status == "approved" for s in steps),
    }


# ── Project file aggregation ──


async def get_project_files(db: AsyncSession, project_id, *, cookies=None, csrf_token=None) -> list[dict]:
    """Aggregate files from all member threads via Gateway upload list API."""
    import httpx
    import os

    stmt = select(ProjectMember).where(ProjectMember.project_id == project_id)
    result = await db.execute(stmt)
    members = result.scalars().all()

    gateway_port = os.environ.get("GATEWAY_PORT", "8001")
    headers = {}
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token

    files = []
    async with httpx.AsyncClient(cookies=cookies) as client:
        for m in members:
            username = await _resolve_username(db, m.user_id)
            if not m.thread_id:
                continue
            try:
                resp = await client.get(
                    f"http://localhost:{gateway_port}/api/threads/{m.thread_id}/uploads/list",
                    headers=headers,
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for f in data.get("files", []):
                        f["thread_id"] = m.thread_id
                        f["member"] = username
                        files.append(f)
            except Exception:
                pass

    return files
