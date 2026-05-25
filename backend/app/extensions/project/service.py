"""Database-backed service for report project management."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
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

    # Auto-add creator as manager
    if created_by:
        member = ProjectMember(
            project_id=project.id,
            user_id=created_by,
            role="manager",
        )
        db.add(member)
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


# ── Writing & Editing Thread Management ──


async def _get_project_or_404(db: AsyncSession, project_id):
    """Get project or raise ValueError."""
    stmt = select(ReportProject).where(ReportProject.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise ValueError("Project not found")
    return project


async def _get_chapter_or_404(db: AsyncSession, chapter_id):
    """Get chapter or raise ValueError."""
    stmt = select(ProjectChapter).where(ProjectChapter.id == chapter_id)
    result = await db.execute(stmt)
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise ValueError("Chapter not found")
    return chapter


async def _create_deerflow_thread(metadata: dict, cookies: dict | None = None, csrf_token: str | None = None) -> str:
    """Create a DeerFlow thread via the Gateway threads API."""
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


async def _start_deerflow_run(thread_id: str, message: str, *, cookies: dict | None = None, csrf_token: str | None = None) -> str:
    """Start a DeerFlow run on an existing thread with a human message.

    Returns the run_id.
    """
    import httpx
    import os

    gateway_port = os.environ.get("GATEWAY_PORT", "8001")

    headers = {}
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token

    run_payload = {
        "assistant_id": None,
        "input": {
            "messages": [
                {"role": "human", "content": message},
            ],
        },
        "metadata": {"source": "ai_tool_action"},
        "multitask_strategy": "reject",
    }

    async with httpx.AsyncClient(cookies=cookies) as client:
        resp = await client.post(
            f"http://localhost:{gateway_port}/api/threads/{thread_id}/runs",
            json=run_payload,
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("run_id", "")


async def start_writing(db: AsyncSession, project_id, *, user_id=None, cookies=None, csrf_token=None):
    """Create a project-level thread for AI writing (Stage 3).

    Returns {"thread_id": ..., "project_id": ...}
    """
    project = await _get_project_or_404(db, project_id)

    # Reuse existing thread if already created
    if project.thread_id:
        return {"thread_id": project.thread_id, "project_id": project_id}

    thread_id = await _create_deerflow_thread({
        "project_id": str(project_id),
        "type": "report_project",
        "report_type": project.report_type,
    }, cookies=cookies, csrf_token=csrf_token)

    project.thread_id = thread_id
    await db.flush()

    return {"thread_id": thread_id, "project_id": project_id}


async def start_chapter_editing(db: AsyncSession, project_id, chapter_id, *, user_id=None, cookies=None, csrf_token=None):
    """Create a chapter-level thread for collaborative editing (Stage 4).

    Returns {"thread_id": ..., "project_id": ..., "chapter_id": ...}
    """
    project = await _get_project_or_404(db, project_id)
    chapter = await _get_chapter_or_404(db, chapter_id)

    if chapter.project_id != project_id:
        raise ValueError("Chapter does not belong to this project")

    thread_id = await _create_deerflow_thread({
        "project_id": str(project_id),
        "chapter_id": str(chapter_id),
        "parent_thread_id": project.thread_id or "",
        "type": "chapter_edit",
        "assigned_to": str(chapter.assigned_to) if chapter.assigned_to else "",
    }, cookies=cookies, csrf_token=csrf_token)

    # Update chapter status to "editing"
    chapter.status = "editing"
    await db.flush()

    return {"thread_id": thread_id, "project_id": project_id, "chapter_id": chapter_id}


# ── AI Action ──

ACTION_LABELS = {
    "polish": "内容润色",
    "expand": "内容扩写",
    "condense": "内容缩写",
    "format_check": "格式检查",
    "compliance_check": "合规性检查",
    "terminology_check": "术语统一检查",
}

ACTION_PROMPTS = {
    "polish": "请对以下章节内容进行润色，优化语言表述，提升文字质量。保持原意不变，不增删实质性内容。",
    "expand": "请根据该章节的编写目的和要求，对以下内容进行扩写，丰富细节和数据支撑。目标字数：{target_word_count}字。",
    "condense": "请精简以下章节内容，去除冗余表述，保留核心信息。目标字数：{target_word_count}字。",
    "format_check": "请检查以下章节内容的格式问题，包括标点符号、编号规范、格式一致性、段落结构等，列出问题并给出修正建议。",
    "compliance_check": "请对照以下法规/标准验证章节内容的合规性。检查标准：{standard}。如未指定标准，请对照项目报告类型的通用规范进行检查。",
    "terminology_check": "请检查以下章节（以及全文上下文）中的专业术语使用是否一致、准确。列出不一致或可能有误的术语及其出现位置。",
}


async def execute_ai_action(
    db: AsyncSession,
    project_id,
    chapter_ids: list,
    action: str,
    params: dict | None = None,
    *,
    user_id=None,
    cookies=None,
    csrf_token=None,
) -> dict:
    """Create a temporary thread for an AI toolbox action.

    Returns {"thread_id": ..., "task_count": ...}
    """
    from .schemas import VALID_AI_ACTIONS

    if action not in VALID_AI_ACTIONS:
        raise ValueError(f"Invalid action: {action}. Valid: {VALID_AI_ACTIONS}")

    project = await _get_project_or_404(db, project_id)

    # Fetch chapters
    chapters = []
    for ch_id in chapter_ids:
        chapter = await _get_chapter_or_404(db, ch_id)
        if chapter.project_id != project_id:
            raise ValueError(f"Chapter {ch_id} does not belong to this project")
        chapters.append(chapter)

    if not chapters:
        raise ValueError("No valid chapters found")

    # Build tool-specific prompt
    action_prompt = ACTION_PROMPTS.get(action, "")
    target_word_count = (params or {}).get("target_word_count", "")
    standard = (params or {}).get("standard", "")
    action_prompt = action_prompt.format(
        target_word_count=target_word_count or "（保持原字数）",
        standard=standard or "行业通用规范",
    )

    # Build chapter context
    chapter_context_parts = []
    for ch in chapters:
        purpose_line = f"\n编写目的：{ch.purpose}" if ch.purpose else ""
        hint_line = f"\n编写提示：{ch.generation_hint}" if ch.generation_hint else ""
        content_line = f"\n\n当前内容：\n{ch.content}" if ch.content else "\n\n当前内容：（空）"
        chapter_context_parts.append(f"### {ch.title}{purpose_line}{hint_line}{content_line}")

    system_prompt = (
        f"你是专业的报告撰写辅助AI。当前任务：{ACTION_LABELS.get(action, action)}\n\n"
        f"## 项目信息\n项目名称：{project.name}\n\n"
        f"## 任务指令\n{action_prompt}\n\n"
        f"## 目标章节\n" + "\n".join(chapter_context_parts)
    )

    if project.template_id:
        system_prompt += "\n\n请确保修改后的内容符合项目的编写规范和合规要求。"
        system_prompt += "\n完成后请使用 write_chapter 工具将结果写回对应章节。"

    # Create temporary thread
    thread_id = await _create_deerflow_thread(
        {
            "project_id": str(project_id),
            "type": "ai_tool_action",
            "action": action,
            "chapter_ids": [str(ch_id) for ch_id in chapter_ids],
        },
        cookies=cookies,
        csrf_token=csrf_token,
    )

    # Build the human message that triggers the agent
    chapter_names = "、".join(ch.title for ch in chapters)
    human_message = (
        f"请执行「{ACTION_LABELS.get(action, action)}」任务。\n\n"
        f"目标章节：{chapter_names}\n\n"
        f"以下是完整的任务指令和章节上下文：\n\n{system_prompt}"
    )

    # Start a run on the thread so the agent auto-executes
    await _start_deerflow_run(thread_id, human_message, cookies=cookies, csrf_token=csrf_token)

    return {"thread_id": thread_id, "task_count": len(chapters)}


# ── Permission query & Approval workflow ──


async def get_my_permissions(
    db: AsyncSession, project_id: UUID, user_id: UUID, is_admin: bool = False
) -> dict:
    from app.extensions.project.permissions import get_user_project_permissions, get_default_tab
    role, permissions = await get_user_project_permissions(db, project_id, user_id, is_admin)
    return {
        "role": role,
        "permissions": permissions,
        "default_tab": get_default_tab(role) if role else "dashboard",
    }


async def submit_approval(
    db: AsyncSession, project_id: UUID, manager_id: UUID,
    steps: list[dict],
) -> dict:
    """Manager submits project for approval, creating workflow steps."""
    from app.extensions.models import ApprovalWorkflow

    project = await _get_project_or_404(db, project_id)

    # Delete existing workflows if any
    existing = await db.execute(
        select(ApprovalWorkflow).where(ApprovalWorkflow.project_id == project_id)
    )
    for wf in existing.scalars().all():
        await db.delete(wf)

    # Create new workflow steps
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

    project.current_stage = 5
    await db.flush()
    return {"project_id": project_id, "status": "submitted", "step_count": len(steps)}


async def approval_action(
    db: AsyncSession, project_id: UUID, workflow_id: UUID,
    reviewer_id: UUID, action: str, comment: str | None,
) -> dict:
    """Execute an approval action (approve/reject) on a workflow step."""
    from app.extensions.models import ApprovalWorkflow, ApprovalRecord

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
            project.current_stage = 6

    elif action == "reject":
        workflow.status = "rejected"
        project = await _get_project_or_404(db, project_id)
        project.current_stage = 4
        subsequent = await db.execute(
            select(ApprovalWorkflow).where(
                ApprovalWorkflow.project_id == project_id,
                ApprovalWorkflow.step_order > workflow.step_order,
            )
        )
        for s in subsequent.scalars().all():
            s.status = "pending"

    await db.flush()
    project = await _get_project_or_404(db, project_id)
    return {"workflow_id": workflow_id, "action": action, "new_stage": project.current_stage}


async def get_approval_status(db: AsyncSession, project_id: UUID) -> dict:
    """Get current approval status for a project."""
    from app.extensions.models import ApprovalWorkflow

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
