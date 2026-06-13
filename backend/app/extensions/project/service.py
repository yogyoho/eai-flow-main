"""Database-backed service for report project management."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Integer, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import (
    ApprovalRecord,
    ApprovalWorkflow,
    Department,
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

    # Batch-resolve creator info (user name + department) for all projects
    creator_ids = {p.created_by for p in projects if p.created_by}
    creator_names: dict = {}
    creator_depts: dict = {}
    if creator_ids:
        user_stmt = select(User.id, User.username, User.full_name, User.dept_id).where(User.id.in_(creator_ids))
        user_result = await db.execute(user_stmt)
        dept_ids: set = set()
        for uid, username, full_name, dept_id in user_result.all():
            creator_names[uid] = full_name or username
            if dept_id:
                dept_ids.add(dept_id)
                creator_depts[uid] = dept_id
        if dept_ids:
            dept_stmt = select(Department.id, Department.name).where(Department.id.in_(dept_ids))
            dept_result = await db.execute(dept_stmt)
            dept_name_map = dict(dept_result.all())
            creator_depts = {uid: dept_name_map[did] for uid, did in creator_depts.items() if did in dept_name_map}

    items = []
    project_ids = [p.id for p in projects]

    # Batch query: chapter counts and completed counts per project
    chapter_stats: dict = {}
    if project_ids:
        ch_stmt = (
            select(
                ProjectChapter.project_id,
                func.count(ProjectChapter.id).label("total"),
                func.sum(
                    func.cast(
                        ProjectChapter.status.in_(("completed", "approved")),
                        Integer,
                    )
                ).label("completed"),
            )
            .where(ProjectChapter.project_id.in_(project_ids))
            .group_by(ProjectChapter.project_id)
        )
        ch_result = await db.execute(ch_stmt)
        for pid, total, done in ch_result.all():
            chapter_stats[pid] = {"total": total or 0, "completed": done or 0}

    # Batch query: member counts per project
    member_stats: dict = {}
    if project_ids:
        m_stmt = (
            select(ProjectMember.project_id, func.count(ProjectMember.id).label("count"))
            .where(ProjectMember.project_id.in_(project_ids))
            .group_by(ProjectMember.project_id)
        )
        m_result = await db.execute(m_stmt)
        member_stats = dict(m_result.all())

    # Batch query: template names
    template_ids = {p.template_id for p in projects if p.template_id}
    template_names: dict = {}
    if template_ids:
        from app.extensions.knowledge_factory.models import ExtractionTemplate
        tmpl_stmt = select(ExtractionTemplate.id, ExtractionTemplate.name).where(ExtractionTemplate.id.in_(template_ids))
        tmpl_result = await db.execute(tmpl_stmt)
        template_names = dict(tmpl_result.all())

    for p in projects:
        stats = chapter_stats.get(p.id, {"total": 0, "completed": 0})
        cc = stats["total"]
        done = stats["completed"]
        pct = round(done / cc * 100, 1) if cc > 0 else 0.0

        items.append(ProjectListItem(
            id=p.id,
            name=p.name,
            report_type=p.report_type,
            status=p.status,
            template_id=p.template_id,
            template_name=template_names.get(p.template_id) if p.template_id else None,
            chapter_count=cc,
            completed_chapter_count=done,
            progress_percentage=pct,
            member_count=member_stats.get(p.id, 0),
            created_by=p.created_by,
            created_by_name=creator_names.get(p.created_by) if p.created_by else None,
            created_by_dept=creator_depts.get(p.created_by) if p.created_by else None,
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
        workflow_id=project.workflow_id,
        temporal_workflow_id=project.temporal_workflow_id,
        current_phase_node=project.current_phase_node,
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
    member = result.scalars().first()
    if not member:
        raise ValueError("Not a project member")

    if member.thread_id:
        template_name = ""
        if project.template_id:
            from app.extensions.knowledge_factory.models import ExtractionTemplate
            tmpl = await db.get(ExtractionTemplate, project.template_id)
            if tmpl:
                template_name = tmpl.name
        return {"thread_id": member.thread_id, "project_id": str(project_id), "template_name": template_name}

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

    return {
        "thread_id": thread_id,
        "project_id": str(project_id),
        "template_name": template_context.get("template_name", ""),
    }


async def sync_project_thread_docs(
    db: AsyncSession,
    *,
    project_id,
    user_id,
    thread_id: str,
) -> dict:
    """Sync sandbox output files from a project thread into AIDocument records.

    Bridges the deer-flow agent sandbox to the document management system,
    so files generated by the AI appear in the project's Editor tab.
    """
    from deerflow.config.paths import Paths

    from app.extensions.docmgr.service import AIDocumentService

    paths = Paths()

    # Resolve the sandbox directory for the thread
    sandbox_dir = paths.sandbox_user_data_dir(thread_id=thread_id, user_id=str(user_id))

    # Also try scanning other user dirs in case of Gateway vs extensions UUID split
    if not sandbox_dir.exists():
        users_dir = paths.base_dir / "users"
        if users_dir.is_dir():
            for user_bucket in sorted(users_dir.iterdir()):
                if not user_bucket.is_dir():
                    continue
                candidate = user_bucket / "threads" / thread_id / "user-data"
                if candidate.exists():
                    sandbox_dir = candidate
                    break

    result = await AIDocumentService.sync_thread_files(
        db=db,
        user_id=user_id,
        thread_id=thread_id,
        sandbox_dir=str(sandbox_dir),
    )

    # Update project chapter stats from all synced documents
    await _refresh_project_stats(db, project_id)

    return result


async def open_chapter_document(
    db: AsyncSession,
    project_id,
    chapter_id,
    *,
    user_id,
) -> dict:
    """Find or create an AIDocument for a chapter so it can be edited in the collab editor.

    The AIDocument is seeded with the chapter's content if one is created.
    Returns the document info needed by DocCollabView ({id, title, status, doc_type, ...}).
    """
    from uuid import uuid4

    from app.extensions.docmgr.service import AIDocumentService
    from app.extensions.models import AIDocument, ProjectChapter

    # Look up the chapter
    stmt = select(ProjectChapter).where(
        ProjectChapter.id == chapter_id,
        ProjectChapter.project_id == project_id,
    )
    result = await db.execute(stmt)
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise ValueError("Chapter not found")

    # Try to find an existing AIDocument for this chapter.
    # Priority 1: chapter-specific document (created via previous open-chapter)
    chapter_doc_title = f"[chapter:{chapter_id}] {chapter.title}"
    stmt = select(AIDocument).where(
        AIDocument.title == chapter_doc_title,
        AIDocument.project_id == project_id,
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if doc:
        return _doc_info(doc)

    # Priority 2: a finalized document whose content contains this chapter as a heading.
    # Use broad match — AI may generate headings like "## 1.2 Design Title" or "## A.2 Title".
    stmt2 = select(AIDocument).where(
        AIDocument.project_id == project_id,
        AIDocument.status.in_(["final", "active"]),
        AIDocument.content.ilike(f"%{chapter.title}%"),
    ).limit(1)
    result2 = await db.execute(stmt2)
    doc2 = result2.scalar_one_or_none()

    if doc2:
        return _doc_info(doc2)

    # Priority 3: a file_ref document whose content contains the chapter title.
    # AI-generated reports have all chapters in a single .md file on disk.
    stmt3 = select(AIDocument).where(
        AIDocument.project_id == project_id,
        AIDocument.status.in_(["final", "active"]),
        AIDocument.doc_type == "file_ref",
    ).limit(10)
    result3 = await db.execute(stmt3)
    for doc3 in result3.scalars().all():
        if doc3.file_ref_path:
            from pathlib import Path
            file_path = Path(doc3.file_ref_path)
            if file_path.exists():
                try:
                    text = file_path.read_text(encoding="utf-8")
                    if chapter.title in text:
                        return _doc_info(doc3)
                except (OSError, UnicodeDecodeError):
                    pass

    # Fallback: create a new AIDocument for this chapter
    doc = AIDocument(
        id=uuid4(),
        user_id=user_id,
        title=chapter_doc_title,
        content=chapter.content or "",
        folder="project-chapters",
        project_id=project_id,
        doc_type="document",
        status="active",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return _doc_info(doc)


def _doc_info(doc) -> dict:
    """Format an AIDocument for the frontend."""
    return {
        "id": str(doc.id),
        "title": doc.title,
        "content": doc.content,
        "status": doc.status or "active",
        "doc_type": doc.doc_type or "document",
        "project_id": str(doc.project_id) if doc.project_id else None,
        "source_thread_id": doc.source_thread_id,
        "folder": doc.folder,
        "file_ref_path": doc.file_ref_path,
        "file_size": doc.file_size,
        "file_mime": doc.file_mime,
        "created_at": str(doc.created_at) if doc.created_at else None,
        "updated_at": str(doc.updated_at) if doc.updated_at else None,
    }


async def create_project(
    db: AsyncSession,
    *,
    name: str,
    report_type: str,
    created_by=None,
    template_id=None,
    workflow_id=None,
    members_data: list[dict] | None = None,
) -> ProjectOut:
    has_template = bool(template_id)
    project = ReportProject(
        name=name,
        report_type=report_type,
        created_by=created_by,
        template_id=template_id,
        workflow_id=workflow_id,
        status="active",
    )
    db.add(project)
    await db.flush()

    if created_by and not members_data:
        # Only auto-add creator as owner when no explicit members are specified
        # (backward compatible with API creation without the members field).
        # When members_data is provided (from the creation wizard), the leader
        # is already included in the list.
        member = ProjectMember(
            project_id=project.id,
            user_id=created_by,
            role="owner",
        )
        db.add(member)
        await db.flush()

    # Add members with duties if provided
    if members_data:
        for md in members_data:
            if md["user_id"] == created_by:
                continue  # Creator already added as owner above
            m = ProjectMember(
                project_id=project.id,
                user_id=md["user_id"],
                role=md.get("role", "writer"),
                source_org_unit_id=md.get("source_org_unit_id"),
                phase_duties=md.get("phase_duties"),
            )
            db.add(m)
        await db.flush()
    elif workflow_id:
        # Auto-assign org_bindings from workflow definition
        await _auto_assign_org_bindings(db, project, workflow_id)

    if template_id:
        await _import_template_outline(db, project.id, template_id)

    return await get_project(db, project.id)


async def copy_project(
    db: AsyncSession,
    *,
    source_project_id,
    name: str,
    created_by=None,
    copy_members: bool = True,
    copy_outline: bool = True,
    copy_workflow: bool = True,
) -> ProjectOut | None:
    """Create a new project by copying structure from an existing one."""
    source = await db.get(ReportProject, source_project_id)
    if not source:
        return None

    new_project = ReportProject(
        name=name,
        report_type=source.report_type,
        created_by=created_by,
        template_id=source.template_id,
        workflow_id=source.workflow_id if copy_workflow else None,
        status="active",
    )
    db.add(new_project)
    await db.flush()

    # Add creator as owner
    if created_by:
        member = ProjectMember(
            project_id=new_project.id,
            user_id=created_by,
            role="owner",
        )
        db.add(member)
        await db.flush()

    # Copy members
    if copy_members:
        stmt = select(ProjectMember).where(ProjectMember.project_id == source_project_id)
        result = await db.execute(stmt)
        for m in result.scalars().all():
            if m.user_id == created_by:
                continue  # Skip creator — already added as owner
            new_member = ProjectMember(
                project_id=new_project.id,
                user_id=m.user_id,
                role=m.role,
                source_org_unit_id=m.source_org_unit_id,
                phase_duties=m.phase_duties,
            )
            db.add(new_member)
        await db.flush()

    # Copy outline (chapters)
    if copy_outline:
        stmt = (
            select(ProjectChapter)
            .where(ProjectChapter.project_id == source_project_id)
            .order_by(ProjectChapter.sort_order)
        )
        result = await db.execute(stmt)
        source_chapters = result.scalars().all()

        # Map old chapter IDs to new chapter IDs for parent_id resolution
        id_map: dict = {}
        for ch in source_chapters:
            new_ch = ProjectChapter(
                project_id=new_project.id,
                parent_id=id_map.get(ch.parent_id) if ch.parent_id else None,
                title=ch.title,
                level=ch.level,
                sort_order=ch.sort_order,
                status="pending",  # Reset status for new project
                purpose=ch.purpose,
                generation_hint=ch.generation_hint,
                word_count_target=ch.word_count_target,
                phase_node=ch.phase_node if copy_workflow else None,
            )
            db.add(new_ch)
            await db.flush()
            id_map[ch.id] = new_ch.id

    return await get_project(db, new_project.id)


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


async def _refresh_project_stats(db: AsyncSession, project_id) -> None:
    """Update project chapter stats from synced AIDocument records.

    Scans AIDocuments linked to this project and updates:
    - Chapter word_count_current (from document content length)
    - Chapter status (pending → writing if content exists)
    """
    from sqlalchemy import func as sa_func, update as sa_update

    from app.extensions.models import AIDocument, ProjectChapter

    # Count documents and compute total words from project AIDocuments.
    # For file_ref documents (content stored on disk), read the file to get content length.
    doc_stmt = select(AIDocument).where(AIDocument.project_id == project_id)
    result = await db.execute(doc_stmt)
    docs = result.scalars().all()
    doc_count = len(docs)
    total_words = 0
    for doc in docs:
        if doc.content and len(doc.content) > 0:
            total_words += len(doc.content)
        elif doc.file_ref_path:
            # file_ref documents — read from disk
            from pathlib import Path
            fp = Path(doc.file_ref_path)
            if fp.exists():
                try:
                    total_words += fp.stat().st_size
                except OSError:
                    pass

    # Mark chapters as "writing" if they have associated documents
    chapters_with_docs = (
        select(AIDocument.chapter_id)
        .where(AIDocument.project_id == project_id, AIDocument.chapter_id.isnot(None))
        .distinct()
    )
    result = await db.execute(chapters_with_docs)
    chapter_ids = [row[0] for row in result.all()]

    if chapter_ids:
        # Update chapter word counts from associated document content
        for cid in chapter_ids:
            word_stmt = select(sa_func.coalesce(sa_func.sum(sa_func.length(AIDocument.content)), 0)).where(
                AIDocument.project_id == project_id,
                AIDocument.chapter_id == cid,
            )
            r = await db.execute(word_stmt)
            words = r.scalar_one() or 0

            await db.execute(
                sa_update(ProjectChapter)
                .where(ProjectChapter.id == cid)
                .values(
                    word_count_current=words,
                    status="writing",
                )
            )
    elif doc_count > 0:
        # No chapter-specific docs, but project has documents.
        # Distribute word count evenly across first N chapters.
        ch_stmt = (
            select(ProjectChapter.id)
            .where(ProjectChapter.project_id == project_id)
            .order_by(ProjectChapter.sort_order)
            .limit(min(doc_count, 34))
        )
        result = await db.execute(ch_stmt)
        all_ch_ids = [row[0] for row in result.all()]
        words_per_chapter = total_words // max(len(all_ch_ids), 1) if total_words else 0

        for cid in all_ch_ids:
            await db.execute(
                sa_update(ProjectChapter)
                .where(ProjectChapter.id == cid)
                .values(
                    word_count_current=words_per_chapter,
                    status="writing",
                )
            )

    await db.flush()


async def _auto_assign_org_bindings(db: AsyncSession, project: ReportProject, workflow_id) -> None:
    """Auto-assign org unit bindings from workflow template to project members.

    If the workflow has org_bindings mapping phase nodes to department codes,
    look up users in those departments and auto-create ProjectMember rows
    with source_org_unit_id set.
    """
    from app.extensions.workflow.models import WorkflowDefinition

    defn = await db.get(WorkflowDefinition, workflow_id)
    if not defn or not defn.org_bindings:
        return

    from app.extensions.models import Department, User, UserDepartment

    for phase_node, binding in defn.org_bindings.items():
        dept_code = binding.get("dept_code") or binding.get("department_code")
        if not dept_code:
            continue

        # Resolve department by code
        dept_stmt = select(Department).where(Department.code == dept_code)
        dept_result = await db.execute(dept_stmt)
        dept = dept_result.scalar_one_or_none()
        if not dept:
            continue

        # Find users in this department
        ud_stmt = select(UserDepartment.user_id).where(UserDepartment.dept_id == dept.id)
        ud_result = await db.execute(ud_stmt)
        dept_user_ids = [row[0] for row in ud_result.all()]

        if not dept_user_ids:
            continue

        # Get department manager (leader_id) if set
        leader_id = dept.leader_id

        # Auto-assign department members to project
        for uid in dept_user_ids:
            # Check if already a member
            existing_stmt = select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == uid,
            )
            existing_result = await db.execute(existing_stmt)
            if existing_result.scalar_one_or_none():
                continue

            # Determine role and duties
            role = "writer"
            phase_duties = {}
            if uid == leader_id:
                phase_duties[phase_node] = {"slot_type": "leader", "role": "组长"}
                role = "leader"
            else:
                phase_duties[phase_node] = {"slot_type": "writer", "role": "组员"}

            member = ProjectMember(
                project_id=project.id,
                user_id=uid,
                role=role,
                source_org_unit_id=dept.id,
                phase_duties=phase_duties if phase_duties else None,
            )
            db.add(member)

    await db.flush()


async def update_project(db: AsyncSession, project_id, **kwargs) -> ProjectOut | None:
    from .schemas import validate_status_transition

    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        return None

    # Validate status transition if status is being changed
    new_status = kwargs.get("status")
    if new_status is not None and new_status != project.status:
        err = validate_status_transition(project.status, new_status)
        if err:
            raise HTTPException(status_code=400, detail=err)

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

    # Null out AIDocument.project_id references so the FK constraint does not
    # block the CASCADE delete at the database level.  This is needed because
    # the ai_documents FK currently lacks ON DELETE SET NULL in some databases.
    from app.extensions.models import AIDocument
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(AIDocument)
        .where(AIDocument.project_id == project_id)
        .values(project_id=None)
    )

    await db.delete(project)
    await db.flush()
    return True


# ── Members ──


async def add_member(db: AsyncSession, project_id, user_id, role: str = "writer") -> bool:
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


async def update_member(
    db: AsyncSession, project_id, user_id, *, role: str | None = None, phase_duties: dict | None = None,
) -> bool:
    """Update a project member's role and/or phase_duties."""
    stmt = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    )
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()
    if not member:
        return False
    if role is not None:
        member.role = role
    if phase_duties is not None:
        member.phase_duties = phase_duties
    await db.flush()
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
    is_admin: bool = False,
) -> dict:
    workflow = await db.get(ApprovalWorkflow, workflow_id)
    if not workflow or workflow.project_id != project_id:
        raise HTTPException(status_code=404, detail="审核步骤不存在")

    if not is_admin and workflow.reviewer_id != reviewer_id:
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
    from sqlalchemy.orm import selectinload

    all_steps = await db.execute(
        select(ApprovalWorkflow)
        .where(ApprovalWorkflow.project_id == project_id)
        .options(selectinload(ApprovalWorkflow.records))
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


# ── Chapter updates ──


async def update_chapter(db: AsyncSession, chapter_id, **kwargs) -> ProjectChapter | None:
    """Update a chapter's fields and auto-parse traceability sources if content changes."""
    chapter = await db.get(ProjectChapter, chapter_id)
    if not chapter:
        return None

    content_changed = "content" in kwargs and kwargs["content"] != chapter.content

    for k, v in kwargs.items():
        setattr(chapter, k, v)

    await db.flush()

    if content_changed and chapter.content:
        await _auto_parse_sources(db, chapter_id, chapter.content)

    return chapter


async def _auto_parse_sources(db: AsyncSession, chapter_id, content: str) -> None:
    """Parse [source:type:ref] markers and persist to content_sources table."""
    from app.extensions.workflow.traceability import parse_source_markers
    from app.extensions.workflow.models import ContentSource

    parsed = parse_source_markers(content)
    if not parsed:
        return

    await db.execute(
        ContentSource.__table__.delete().where(ContentSource.chapter_id == chapter_id)
    )

    for s in parsed:
        source = ContentSource(
            chapter_id=chapter_id,
            block_index=s.block_index,
            source_type=s.source_type,
            source_ref=s.source_ref,
            snippet=s.snippet,
        )
        db.add(source)

    await db.flush()


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

    # 2. Also include synced AIDocument records for this project
    from app.extensions.models import AIDocument
    doc_stmt = select(AIDocument).where(
        AIDocument.project_id == project_id,
        AIDocument.file_ref_path.isnot(None),
    )
    doc_result = await db.execute(doc_stmt)
    for doc in doc_result.scalars().all():
        files.append({
            "name": doc.title or "Untitled",
            "size": doc.file_size,
            "mime_type": doc.file_mime,
            "thread_id": doc.source_thread_id,
            "member": "AI",
            "updated_at": str(doc.updated_at) if doc.updated_at else None,
            "source": "aidocument",
        })

    return files


# ── Phase Board ──


async def get_phase_board(db: AsyncSession, project_id: UUID, phase_node: str) -> dict | None:
    """Get phase board data: chapters, members, and review summary for a specific phase."""
    project = await _get_project_or_404(db, project_id)
    if not project:
        return None

    # Resolve phase label from workflow graph
    phase_label = phase_node
    if project.workflow_id:
        from app.extensions.workflow.models import WorkflowDefinition

        defn = await db.get(WorkflowDefinition, project.workflow_id)
        if defn and defn.graph_json:
            for node in defn.graph_json.get("nodes", []):
                if node["id"] == phase_node:
                    phase_label = node.get("data", {}).get("label", phase_node)
                    break

    # Get chapters — optionally filter by phase's chapter_range if defined in the graph node
    chapter_stmt = select(ProjectChapter).where(
        ProjectChapter.project_id == project_id,
    ).order_by(ProjectChapter.sort_order)
    chapter_result = await db.execute(chapter_stmt)
    all_chapters = chapter_result.scalars().all()

    # Try to filter by chapter_range from the workflow node
    filtered_chapters = all_chapters
    if project.workflow_id:
        from app.extensions.workflow.models import WorkflowDefinition

        defn = await db.get(WorkflowDefinition, project.workflow_id)
        if defn and defn.graph_json:
            for node in defn.graph_json.get("nodes", []):
                if node["id"] == phase_node:
                    cr = node.get("data", {}).get("chapter_range")
                    if cr and len(cr) == 2:
                        # Filter by level-1 chapter sort_order range
                        level1_chapters = [c for c in all_chapters if c.level == 1]
                        start_idx, end_idx = cr
                        if 0 <= start_idx < len(level1_chapters) and 0 < end_idx <= len(level1_chapters):
                            selected_ids = {c.id for c in level1_chapters[start_idx:end_idx]}
                            # Include children of selected chapters too
                            filtered_chapters = [
                                c for c in all_chapters
                                if c.id in selected_ids or c.parent_id in selected_ids
                            ]
                    break

    # Build assigned names map
    assigned_ids = {c.assigned_to for c in filtered_chapters if c.assigned_to}
    assigned_names = {}
    for uid in assigned_ids:
        assigned_names[uid] = await _resolve_username(db, uid)

    chapters_out = [
        {
            "id": c.id,
            "title": c.title,
            "status": c.status,
            "assigned_to": c.assigned_to,
            "assigned_name": assigned_names.get(c.assigned_to),
            "level": c.level,
            "sort_order": c.sort_order,
            "word_count_target": c.word_count_target,
            "word_count_current": c.word_count_current,
        }
        for c in filtered_chapters
    ]

    # Get members with duties for this phase
    member_stmt = select(ProjectMember).where(ProjectMember.project_id == project_id)
    member_result = await db.execute(member_stmt)
    members = member_result.scalars().all()

    members_out = []
    for m in members:
        duty = None
        if m.phase_duties and phase_node in m.phase_duties:
            duty = m.phase_duties[phase_node].get("duty")
        username = await _resolve_username(db, m.user_id)
        members_out.append({
            "user_id": m.user_id,
            "username": username,
            "role": m.role,
            "duty": duty,
        })

    total = len(filtered_chapters)
    completed = sum(1 for c in filtered_chapters if c.status == "completed")

    return {
        "phase_node": phase_node,
        "phase_label": phase_label,
        "chapters": chapters_out,
        "members": members_out,
        "total_chapters": total,
        "completed_chapters": completed,
    }


async def batch_assign_chapters(
    db: AsyncSession,
    project_id: UUID,
    assignments: list[dict],
) -> dict:
    """Batch assign chapters to users. Each assignment: {chapter_id, assigned_to}."""
    updated = 0
    for a in assignments:
        chapter_id = a.get("chapter_id")
        assigned_to = a.get("assigned_to")
        if not chapter_id:
            continue

        stmt = (
            ProjectChapter.__table__.update()
            .where(ProjectChapter.id == chapter_id)
            .where(ProjectChapter.project_id == project_id)
            .values(assigned_to=assigned_to)
        )
        result = await db.execute(stmt)
        updated += result.rowcount

    await db.commit()
    return {"updated": updated, "total": len(assignments)}
