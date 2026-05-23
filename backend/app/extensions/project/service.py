"""Database-backed service for report project management."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    ChapterTreeNode,
    MemberOut,
    ProjectListItem,
    ProjectOut,
)


# ── Helpers ──


async def _resolve_username(db: AsyncSession, user_id) -> str:
    user = await db.get(User, user_id)
    return user.username if user else str(user_id)


def _chapter_to_out(chapter: ProjectChapter, children: list[ChapterOut] | None = None) -> ChapterOut:
    return ChapterOut(
        id=chapter.id,
        project_id=chapter.project_id,
        parent_id=chapter.parent_id,
        title=chapter.title,
        level=chapter.level,
        sort_order=chapter.sort_order,
        status=chapter.status,
        content=chapter.content,
        assigned_to=chapter.assigned_to,
        assigned_name=None,  # resolved separately
        word_count_target=chapter.word_count_target,
        word_count_current=chapter.word_count_current,
        purpose=chapter.purpose,
        generation_hint=chapter.generation_hint,
        children=children or [],
        created_at=chapter.created_at,
        updated_at=chapter.updated_at,
    )


def _build_chapter_tree(chapters: list[ProjectChapter], assigned_names: dict) -> list[ChapterOut]:
    """Build nested tree from flat chapter list."""
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


# ── Outline tree helpers ──


async def _create_chapters_from_tree(
    db: AsyncSession,
    project_id,
    nodes: list[ChapterTreeNode],
    parent_id=None,
    level: int = 1,
    start_order: int = 0,
) -> list[ProjectChapter]:
    """Recursively create ProjectChapter records from ChapterTreeNode list."""
    created = []
    for i, node in enumerate(nodes):
        chapter = ProjectChapter(
            project_id=project_id,
            parent_id=parent_id,
            title=node.title,
            level=level,
            sort_order=start_order + i,
            purpose=node.purpose,
            generation_hint=node.generation_hint,
            word_count_target=node.word_count_target,
        )
        db.add(chapter)
        await db.flush()
        created.append(chapter)

        if node.children:
            children = await _create_chapters_from_tree(
                db, project_id, node.children, parent_id=chapter.id, level=level + 1, start_order=0,
            )
            created.extend(children)

    return created


async def _delete_project_chapters(db: AsyncSession, project_id) -> None:
    """Delete all chapters for a project (for outline replacement)."""
    stmt = select(ProjectChapter).where(ProjectChapter.project_id == project_id)
    result = await db.execute(stmt)
    for chapter in result.scalars().all():
        await db.delete(chapter)


# ── Public API ──


async def list_projects(
    db: AsyncSession,
    *,
    status: str | None = None,
    report_type: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[ProjectListItem], int]:
    query = select(ReportProject).where(ReportProject.status != "archived")
    count_query = select(func.count(ReportProject.id)).where(ReportProject.status != "archived")

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
            current_stage=p.current_stage,
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

    # Load chapters
    chap_stmt = select(ProjectChapter).where(ProjectChapter.project_id == project_id)
    chap_result = await db.execute(chap_stmt)
    chapters = list(chap_result.scalars().all())
    assigned_names = await _get_assigned_names(db, chapters)
    chapter_tree = _build_chapter_tree(chapters, assigned_names)

    # Load members
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
        current_stage=project.current_stage,
        thread_id=project.thread_id,
        created_by=project.created_by,
        members=members,
        chapters=chapter_tree,
        chapter_count=len(chapters),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


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
        status="outline" if has_template else "setup",
        current_stage=2 if has_template else 1,
    )
    db.add(project)
    await db.flush()

    # If template_id provided, import chapters from template
    if template_id:
        await _import_template_outline(db, project.id, template_id)

    return await get_project(db, project.id)


async def _import_template_outline(db: AsyncSession, project_id, template_id) -> None:
    """Import chapter structure from a KF template."""
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


# ── Outline ──


async def get_outline_tree(db: AsyncSession, project_id) -> list[ChapterOut]:
    chap_stmt = select(ProjectChapter).where(ProjectChapter.project_id == project_id)
    chap_result = await db.execute(chap_stmt)
    chapters = list(chap_result.scalars().all())
    assigned_names = await _get_assigned_names(db, chapters)
    return _build_chapter_tree(chapters, assigned_names)


async def replace_outline(db: AsyncSession, project_id, chapters: list[ChapterTreeNode]) -> list[ChapterOut]:
    """Delete existing chapters and create new ones from the tree structure."""
    await _delete_project_chapters(db, project_id)
    await _create_chapters_from_tree(db, project_id, chapters)
    await db.flush()
    return await get_outline_tree(db, project_id)


async def update_chapter(db: AsyncSession, chapter_id, **kwargs) -> ChapterOut | None:
    stmt = select(ProjectChapter).where(ProjectChapter.id == chapter_id)
    result = await db.execute(stmt)
    chapter = result.scalar_one_or_none()
    if not chapter:
        return None

    for k, v in kwargs.items():
        if v is not None:
            setattr(chapter, k, v)

    await db.flush()
    assigned_names = await _get_assigned_names(db, [chapter])
    return _chapter_to_out(chapter)


async def confirm_outline(db: AsyncSession, project_id) -> ProjectOut | None:
    """Advance project from stage 2 (outline) to stage 3 (writing)."""
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        return None

    project.current_stage = 3
    project.status = "writing"
    await db.flush()
    return await get_project(db, project_id)


# ── Members ──


async def add_member(db: AsyncSession, project_id, user_id, role: str = "editor") -> bool:
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
