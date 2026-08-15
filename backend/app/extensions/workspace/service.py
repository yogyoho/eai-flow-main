"""Collab Workspace — 业务服务。

EAI-CUSTOM: 全新模块，零引用 extensions/project/workflow/approval。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import AIDocument

from .models import (
    CollabActivity,
    CollabAgentRun,
    CollabGate,
    CollabMember,
    CollabProject,
    CollabSection,
    CollabTask,
)
from .tier import recompute_tier

# ── Helpers ──


def _now() -> datetime:
    # EAI-CUSTOM: DB 列是 TIMESTAMP WITHOUT TIME ZONE，须返回 naive UTC
    # （asyncpg 拒绝 offset-aware/naive 混用，见 bug-710）
    return datetime.now(UTC).replace(tzinfo=None)


async def _get_project_or_404(db: AsyncSession, project_id: UUID) -> CollabProject:
    project = await db.get(CollabProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


async def _is_member(db: AsyncSession, project_id: UUID, user_id: UUID) -> bool:
    row = await db.scalar(
        select(CollabMember.id).where(
            CollabMember.project_id == project_id,
            CollabMember.member_type == "human",
            CollabMember.user_id == user_id,
        )
    )
    return row is not None


async def _require_member(db: AsyncSession, project_id: UUID, user_id: UUID) -> None:
    if not await _is_member(db, project_id, user_id):
        raise HTTPException(status_code=403, detail="非项目成员")


async def log_activity(
    db: AsyncSession,
    project_id: UUID,
    action: str,
    *,
    actor_type: str = "human",
    actor_id: str | None = None,
    target: str | None = None,
    detail: dict | None = None,
) -> None:
    db.add(
        CollabActivity(
            project_id=project_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target=target,
            detail=detail,
        )
    )


# ── Project CRUD ──


async def create_project(db: AsyncSession, *, name: str, kind: str, user_id: UUID, doc_id: UUID | None = None) -> CollabProject:
    project = CollabProject(
        name=name,
        kind=kind,
        doc_id=doc_id,
        owner_id=user_id,
        created_by=user_id,
        status="active",
        tier_state="tier1",
    )
    db.add(project)
    await db.flush()

    # owner 自动成为成员（owner 角色）
    db.add(
        CollabMember(
            project_id=project.id,
            member_type="human",
            user_id=user_id,
            role="owner",
        )
    )
    await db.flush()
    await db.refresh(project)  # 加载 server defaults（created_at/updated_at）
    await log_activity(db, project.id, "project_created", actor_id=str(user_id))
    return project


async def list_projects(db: AsyncSession, *, user_id: UUID) -> list[CollabProject]:
    stmt = select(CollabProject).join(CollabMember, CollabMember.project_id == CollabProject.id).where(CollabMember.member_type == "human", CollabMember.user_id == user_id).order_by(CollabProject.updated_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_project(db: AsyncSession, project_id: UUID) -> CollabProject:
    return await _get_project_or_404(db, project_id)


async def update_project(db: AsyncSession, project_id: UUID, **kwargs) -> CollabProject:
    project = await _get_project_or_404(db, project_id)
    if "status" in kwargs and kwargs["status"] == "archived":
        project.status = "archived"
    else:
        for k, v in kwargs.items():
            if v is not None:
                setattr(project, k, v)
    if project.status == "submitted_for_release":
        await recompute_tier(db, project)
    await db.flush()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project_id: UUID) -> bool:
    project = await _get_project_or_404(db, project_id)
    project.status = "archived"
    await db.flush()
    return True


async def release_project(db: AsyncSession, project_id: UUID, user_id: UUID) -> CollabProject:
    """POST /release 最小占位：status→submitted_for_release + 建 project_release 闸门 + 升 T3。"""
    project = await _get_project_or_404(db, project_id)
    project.status = "submitted_for_release"
    await recompute_tier(db, project)

    # 建 scope=project_release 闸门（默认参与者 = 项目 owner）
    owner_member = await db.scalar(
        select(CollabMember).where(
            CollabMember.project_id == project_id,
            CollabMember.role == "owner",
        )
    )
    participants = [{"type": "human", "user_id": str(project.owner_id), "weight": 1.0}] if project.owner_id else []
    if owner_member and owner_member.user_id:
        participants = [{"type": "human", "user_id": str(owner_member.user_id), "weight": 1.0}]
    db.add(
        CollabGate(
            project_id=project_id,
            scope="project_release",
            state="pending",
            mode="all_must_approve",
            participants=participants,
        )
    )
    await db.flush()
    await db.refresh(project)  # 加载 server defaults，避免 MissingGreenlet
    await log_activity(db, project_id, "project_released", actor_id=str(user_id))
    return project


# ── Sections ──


def _extract_headings(markdown: str) -> list[str]:
    """从 markdown 提取 ## 二级标题（promote-to-report 用）。"""
    if not markdown:
        return []
    headings = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and len(stripped) > 3:
            headings.append(stripped[3:].strip())
    return headings


async def materialize_sections_from_doc(db: AsyncSession, project: CollabProject, *, user_id: UUID) -> list[CollabSection]:
    """promote-to-report：从项目 doc 的 ## 标题物化 collab_sections，翻 kind。

    原文档作为首个/根 section 的 doc_id，内容保留；项目 doc_id 置 NULL。
    """
    doc = None
    if project.doc_id:
        doc = await db.get(AIDocument, project.doc_id)

    headings = _extract_headings(doc.content) if doc and doc.content else []
    if not headings and doc:
        # 无 ## 标题则整篇作为一个 section
        headings = [project.name]

    sections: list[CollabSection] = []
    first = True
    for i, title in enumerate(headings):
        sec = CollabSection(
            project_id=project.id,
            title=title,
            level=1,
            sort_order=i,
            status="draft",
            doc_id=project.doc_id if first else None,  # 原文档作为首个 section
            content=doc.content if first and doc else None,
            word_count_target=3000,
        )
        db.add(sec)
        await db.flush()
        await db.refresh(sec)
        sections.append(sec)
        first = False

    project.doc_id = None  # kind=report 用 collab_sections
    project.kind = "report"
    await db.flush()
    await log_activity(db, project.id, "promoted_to_report", actor_id=str(user_id), detail={"sections": len(sections)})
    return sections


async def create_section(db: AsyncSession, project_id: UUID, *, title: str, parent_id: UUID | None = None, word_count_target: int = 3000, user_id: UUID) -> CollabSection:
    project = await _get_project_or_404(db, project_id)
    level = 2 if parent_id else 1
    sort_order = await db.scalar(select(CollabSection.sort_order).where(CollabSection.project_id == project_id, CollabSection.parent_id == parent_id).order_by(CollabSection.sort_order.desc()).limit(1)) or 0
    sec = CollabSection(
        project_id=project_id,
        parent_id=parent_id,
        title=title,
        level=level,
        sort_order=sort_order + 1,
        status="pending",
        word_count_target=word_count_target,
    )
    db.add(sec)
    await db.flush()
    await db.refresh(sec)
    await recompute_tier(db, project)
    await log_activity(db, project_id, "section_created", actor_id=str(user_id), target=str(sec.id))
    return sec


async def list_sections(db: AsyncSession, project_id: UUID) -> list[CollabSection]:
    result = await db.execute(select(CollabSection).where(CollabSection.project_id == project_id).order_by(CollabSection.sort_order))
    return list(result.scalars().all())


async def update_section(db: AsyncSession, section_id: UUID, **kwargs) -> CollabSection:
    sec = await db.get(CollabSection, section_id)
    if not sec:
        raise HTTPException(status_code=404, detail="章节不存在")
    for k, v in kwargs.items():
        if v is not None:
            setattr(sec, k, v)
    await db.flush()
    return sec


# ── Members ──


async def add_member(db: AsyncSession, project_id: UUID, *, member_type: str, user_id: UUID | None = None, agent_name: str | None = None, role: str = "editor", actor: UUID) -> CollabMember:
    project = await _get_project_or_404(db, project_id)
    member = CollabMember(
        project_id=project_id,
        member_type=member_type,
        user_id=user_id,
        agent_name=agent_name,
        role=role,
    )
    db.add(member)
    await db.flush()
    await db.refresh(member)  # 加载 server defaults（joined_at），避免 MissingGreenlet
    await recompute_tier(db, project)
    await log_activity(db, project_id, "member_added", actor_id=str(actor), detail={"type": member_type, "role": role})
    return member


async def remove_member(db: AsyncSession, project_id: UUID, member_id: UUID, *, actor: UUID) -> bool:
    project = await _get_project_or_404(db, project_id)
    member = await db.get(CollabMember, member_id)
    if not member or member.project_id != project_id:
        return False
    await db.delete(member)
    await db.flush()
    await recompute_tier(db, project)
    await log_activity(db, project_id, "member_removed", actor_id=str(actor))
    return True


async def update_member_role(db: AsyncSession, project_id: UUID, member_id: UUID, *, role: str, actor: UUID) -> CollabMember:
    member = await db.get(CollabMember, member_id)
    if not member or member.project_id != project_id:
        raise HTTPException(status_code=404, detail="成员不存在")
    member.role = role
    await db.flush()
    await db.refresh(member)
    await log_activity(db, project_id, "member_role_updated", actor_id=str(actor))
    return member


async def list_members(db: AsyncSession, project_id: UUID) -> list[CollabMember]:
    result = await db.execute(select(CollabMember).where(CollabMember.project_id == project_id).order_by(CollabMember.joined_at))
    return list(result.scalars().all())


# ── Tasks ──


async def create_task(
    db: AsyncSession,
    project_id: UUID,
    *,
    title: str,
    kind: str,
    user_id: UUID,
    section_ref: UUID | None = None,
    doc_id: UUID | None = None,
    context: dict | None = None,
    due_at: datetime | None = None,
) -> CollabTask:
    await _get_project_or_404(db, project_id)
    task = CollabTask(
        project_id=project_id,
        title=title,
        kind=kind,
        assignee_type=None,  # 未指派（human/agent 由 assign_task 设置）
        status="pending",
        section_ref=section_ref,
        doc_id=doc_id,
        context=context,
        due_at=due_at,
        created_by=user_id,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    await log_activity(db, project_id, "task_created", actor_id=str(user_id), target=str(task.id))
    return task


async def assign_task(
    db: AsyncSession,
    project_id: UUID,
    task_id: UUID,
    *,
    assignee_type: str,
    user_id: UUID | None = None,
    agent_name: str | None = None,
    actor: UUID,
) -> CollabTask:
    task = await db.get(CollabTask, task_id)
    if not task or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    task.assignee_type = assignee_type
    task.assignee_user_id = user_id
    task.assignee_agent_name = agent_name
    task.status = "pending"
    await db.flush()
    await db.refresh(task)  # 加载 server-side defaults（created_at/updated_at），避免 MissingGreenlet

    # 指派时自动建 scope=task 闸门（默认参与者 = 指派对象 + 项目 owner）
    project = await _get_project_or_404(db, project_id)
    participants: list[dict] = []
    if assignee_type == "human" and user_id:
        participants.append({"type": "human", "user_id": str(user_id), "weight": 1.0})
    elif assignee_type == "agent" and agent_name:
        participants.append({"type": "agent", "agent_name": agent_name, "weight": 1.0})
    if project.owner_id:
        participants.append({"type": "human", "user_id": str(project.owner_id), "weight": 1.0})
    db.add(
        CollabGate(
            project_id=project_id,
            task_id=task_id,
            scope="task",
            state="pending",
            mode="all_must_approve",
            participants=participants,
        )
    )
    await db.flush()
    await log_activity(db, project_id, "task_assigned", actor_id=str(actor), target=str(task.id), detail={"assignee_type": assignee_type})
    return task


async def list_tasks(db: AsyncSession, project_id: UUID) -> list[CollabTask]:
    result = await db.execute(select(CollabTask).where(CollabTask.project_id == project_id).order_by(CollabTask.updated_at.desc()))
    return list(result.scalars().all())


async def update_task(db: AsyncSession, project_id: UUID, task_id: UUID, **kwargs) -> CollabTask:
    task = await db.get(CollabTask, task_id)
    if not task or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    for k, v in kwargs.items():
        if v is not None:
            setattr(task, k, v)
    await db.flush()
    await db.refresh(task)
    return task


async def record_handoff(db: AsyncSession, project_id: UUID, task_id: UUID, *, state: str, payload: dict, actor: str | None = None) -> CollabTask:
    """记录结构化交接（agent .handoff.json 由桥解析后调用；或协调者手动覆盖）。"""
    task = await db.get(CollabTask, task_id)
    if not task or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    task.handoff_state = state
    task.handoff_payload = payload
    if state == "done":
        task.status = "done"
    elif state == "blocked":
        task.status = "blocked"
    elif state == "progress":
        task.status = "in_progress"
    elif state == "acked":
        task.status = "in_progress"
    await db.flush()
    await db.refresh(task)
    await log_activity(db, project_id, "handoff_received", actor_id=actor or "system", target=str(task_id), detail={"state": state})
    return task


# ── Gates ──


async def list_gates(db: AsyncSession, project_id: UUID) -> list[CollabGate]:
    result = await db.execute(select(CollabGate).where(CollabGate.project_id == project_id).order_by(CollabGate.created_at))
    gates = list(result.scalars().all())
    # 惰性 deadline 检查
    for g in gates:
        await apply_deadline_inline(g)
    return gates


async def apply_deadline_inline(gate: CollabGate) -> None:
    from .gate import apply_deadline

    await apply_deadline(gate)


async def judge_gate(
    db: AsyncSession,
    project_id: UUID,
    gate_id: UUID,
    *,
    action: str,
    comment: str | None,
    user_id: UUID,
) -> CollabGate:
    gate = await db.get(CollabGate, gate_id)
    if not gate or gate.project_id != project_id:
        raise HTTPException(status_code=404, detail="闸门不存在")
    await apply_deadline_inline(gate)
    if gate.state != "pending":
        raise HTTPException(status_code=400, detail="此闸门已处理")

    # 校验判定者是人类参与者
    human_ids = {p.get("user_id") for p in (gate.participants or []) if p.get("type") == "human" and p.get("user_id")}
    if str(user_id) not in human_ids:
        raise HTTPException(status_code=403, detail="您不是此闸门的指定判定人")

    human_judgments = [{"reviewer_id": str(user_id), "status": action, "comment": comment}]
    from .gate import evaluate

    result = evaluate(gate, human_judgments)
    if action == "reject":
        gate.state = "rejected"
        gate.resolved_by = user_id
        gate.resolved_at = _now()
    elif action == "approve":
        gate.state = "approved"
        gate.resolved_by = user_id
        gate.resolved_at = _now()
    gate.audit = list(gate.audit or []) + [
        {
            "at": _now().isoformat(),
            "by": str(user_id),
            "action": action,
            "comment": comment,
            "gate_result": result.value,
        }
    ]
    await db.flush()

    # 结果耦合：PASS → task done；REJECT → task blocked
    if gate.task_id:
        task = await db.get(CollabTask, gate.task_id)
        if task:
            if gate.state == "approved":
                task.status = "done"
            elif gate.state == "rejected":
                task.status = "blocked"
            await db.flush()
    await log_activity(db, project_id, "gate_judged", actor_id=str(user_id), target=str(gate_id), detail={"action": action})
    return gate


async def reopen_gate(db: AsyncSession, project_id: UUID, gate_id: UUID, *, user_id: UUID) -> CollabGate:
    gate = await db.get(CollabGate, gate_id)
    if not gate or gate.project_id != project_id:
        raise HTTPException(status_code=404, detail="闸门不存在")
    gate.state = "pending"
    gate.revision += 1
    gate.resolved_by = None
    gate.resolved_at = None
    gate.audit = list(gate.audit or []) + [{"at": _now().isoformat(), "by": str(user_id), "action": "reopen"}]
    if gate.task_id:
        task = await db.get(CollabTask, gate.task_id)
        if task:
            task.status = "in_progress"
    await db.flush()
    await log_activity(db, project_id, "gate_reopened", actor_id=str(user_id), target=str(gate_id))
    return gate


# ── Agent runs ──


async def create_agent_run(
    db: AsyncSession,
    project_id: UUID,
    task_id: UUID,
    *,
    agent_name: str,
    thread_id: str,
    run_id: str,
    prompt_snapshot: str,
) -> CollabAgentRun:
    run = CollabAgentRun(
        task_id=task_id,
        project_id=project_id,
        thread_id=thread_id,
        run_id=run_id,
        agent_name=agent_name,
        prompt_snapshot=prompt_snapshot,
        status="running",
        started_at=_now(),
    )
    db.add(run)
    await db.flush()
    return run


async def list_agent_runs(db: AsyncSession, project_id: UUID, task_id: UUID | None = None) -> list[CollabAgentRun]:
    stmt = select(CollabAgentRun).where(CollabAgentRun.project_id == project_id)
    if task_id:
        stmt = stmt.where(CollabAgentRun.task_id == task_id)
    result = await db.execute(stmt.order_by(CollabAgentRun.started_at.desc()))
    return list(result.scalars().all())


# ── publish-doc ──


async def publish_doc(db: AsyncSession, project_id: UUID, *, user_id: UUID) -> dict:
    """flush 协编文档 → ai_documents.content（report 再 → collab_sections.content）。

    - 遍历每个有 doc_id 的 section（quickdoc=项目 doc_id，report=各 section doc_id）
    - 取该 collab doc 最新 collab_versions.snapshot_text
    - snapshot 为 NULL 时跳过不覆盖（Python 不解码 Yjs），记 skip
    - revision CAS：写前比 section.revision，冲突 409
    """
    project = await _get_project_or_404(db, project_id)
    synced: list[str] = []
    skipped: list[str] = []

    if project.kind == "quickdoc" and project.doc_id:
        snapshot = await _latest_snapshot_text(db, project.doc_id)
        if snapshot:
            doc = await db.get(AIDocument, project.doc_id)
            if doc:
                doc.content = snapshot
                synced.append(str(project.doc_id))
        else:
            skipped.append(str(project.doc_id))
    else:
        sections = await list_sections(db, project_id)
        for sec in sections:
            if not sec.doc_id:
                continue
            snapshot = await _latest_snapshot_text(db, sec.doc_id)
            if snapshot:
                doc = await db.get(AIDocument, sec.doc_id)
                if doc:
                    doc.content = snapshot
                sec.content = snapshot
                sec.word_count_current = len(snapshot)
                sec.revision += 1
                synced.append(str(sec.id))
            else:
                skipped.append(str(sec.id))

    await db.flush()
    await log_activity(db, project_id, "doc_published", actor_id=str(user_id), detail={"synced": len(synced), "skipped": len(skipped)})
    return {"synced": synced, "skipped": skipped}


async def _latest_snapshot_text(db: AsyncSession, doc_id: UUID) -> str | None:
    """取 collab_versions 最新 snapshot_text。"""
    from sqlalchemy import text

    row = await db.execute(
        text("SELECT snapshot_text FROM collab_versions WHERE doc_id = :doc_id ORDER BY version DESC LIMIT 1"),
        {"doc_id": str(doc_id)},
    )
    result = row.first()
    return result[0] if result else None


# ── Activities ──


async def list_activities(db: AsyncSession, project_id: UUID, *, limit: int = 50) -> list[CollabActivity]:
    result = await db.execute(select(CollabActivity).where(CollabActivity.project_id == project_id).order_by(CollabActivity.created_at.desc()).limit(limit))
    return list(result.scalars().all())
