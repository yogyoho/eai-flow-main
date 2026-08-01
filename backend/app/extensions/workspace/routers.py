"""Collab Workspace — FastAPI 路由。

EAI-CUSTOM: 全新模块，前缀 /api/extensions/workspace。
cookie-JWT + system:access + 写操作成员校验。资源一律嵌套 /projects/{id}/...
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

from . import service
from .schemas import (
    CollabGateJudge,
    CollabMemberCreate,
    CollabMemberOut,
    CollabMemberUpdate,
    CollabProjectCreate,
    CollabProjectOut,
    CollabProjectTierOut,
    CollabProjectUpdate,
    CollabRunSpawn,
    CollabSectionCreate,
    CollabSectionOut,
    CollabSectionUpdate,
    CollabTaskAssign,
    CollabTaskCreate,
    CollabTaskOut,
    CollabTaskUpdate,
)

router = APIRouter(prefix="/api/extensions/workspace", tags=["workspace"])

CurrentUserWithAccess = Annotated[CurrentUser, Depends(require_permission("system:access"))]


async def _project_out(db: AsyncSession, project) -> CollabProjectOut:
    section_count = await db.scalar(
        select(func.count()).select_from(service.CollabSection).where(service.CollabSection.project_id == project.id)
    ) or 0
    member_count = await db.scalar(
        select(func.count()).select_from(service.CollabMember).where(service.CollabMember.project_id == project.id)
    ) or 0
    task_count = await db.scalar(
        select(func.count()).select_from(service.CollabTask).where(service.CollabTask.project_id == project.id)
    ) or 0
    return CollabProjectOut(
        id=project.id, name=project.name, kind=project.kind, doc_id=project.doc_id,
        owner_id=project.owner_id, tier_state=project.tier_state, tier_signals=project.tier_signals,
        escalated_at=project.escalated_at, status=project.status, compliance_pin=project.compliance_pin,
        created_at=project.created_at, updated_at=project.updated_at,
        section_count=section_count, member_count=member_count, task_count=task_count,
    )


# ── Projects ──


@router.get("/projects", response_model=list[CollabProjectOut])
async def list_projects(
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    projects = await service.list_projects(db, user_id=user.id)
    return [await _project_out(db, p) for p in projects]


@router.post("/projects", response_model=CollabProjectOut, status_code=201)
async def create_project(
    body: CollabProjectCreate,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    # quickdoc 需要 doc：若无 doc_id，先建一个空 AIDocument
    doc_id = None
    if body.kind == "quickdoc":
        from uuid import uuid4
        doc = service.AIDocument(
            id=uuid4(), user_id=user.id, title=body.name, content="", folder="workspace", doc_type="document", status="active",
        )
        db.add(doc)
        await db.flush()
        doc_id = doc.id
    project = await service.create_project(db, name=body.name, kind=body.kind, user_id=user.id, doc_id=doc_id)
    await db.commit()
    return await _project_out(db, project)


@router.get("/projects/{project_id}", response_model=CollabProjectOut)
async def get_project(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    project = await service.get_project(db, project_id)
    return await _project_out(db, project)


@router.patch("/projects/{project_id}", response_model=CollabProjectOut)
async def update_project(
    project_id: UUID,
    body: CollabProjectUpdate,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    project = await service.update_project(db, project_id, **body.model_dump(exclude_unset=True))
    await db.commit()
    return await _project_out(db, project)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    project = await service.get_project(db, project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="仅 owner 可归档项目")
    await service.delete_project(db, project_id)
    await db.commit()


@router.get("/projects/{project_id}/tier", response_model=CollabProjectTierOut)
async def get_tier(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    project = await service.get_project(db, project_id)
    return CollabProjectTierOut(
        project_id=project.id, tier_state=project.tier_state, escalated_at=project.escalated_at, signals=project.tier_signals,
    )


@router.post("/projects/{project_id}/release", response_model=CollabProjectOut)
async def release_project(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    project = await service.release_project(db, project_id, user_id=user.id)
    await db.commit()
    return await _project_out(db, project)


@router.post("/projects/{project_id}/promote-to-report", response_model=list[CollabSectionOut])
async def promote_to_report(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    project = await service.get_project(db, project_id)
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="仅 owner 可升级为 report")
    sections = await service.materialize_sections_from_doc(db, project, user_id=user.id)
    await db.commit()
    return [CollabSectionOut.model_validate(s) for s in sections]


# ── Members ──


@router.get("/projects/{project_id}/members", response_model=list[CollabMemberOut])
async def list_members(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    members = await service.list_members(db, project_id)
    return [CollabMemberOut.model_validate(m) for m in members]


@router.post("/projects/{project_id}/members", response_model=CollabMemberOut, status_code=201)
async def add_member(
    project_id: UUID,
    body: CollabMemberCreate,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    if body.member_type == "agent" and not body.agent_name:
        raise HTTPException(status_code=422, detail="agent 成员必须提供 agent_name")
    if body.member_type == "human" and not body.user_id:
        raise HTTPException(status_code=422, detail="human 成员必须提供 user_id")
    member = await service.add_member(
        db, project_id, member_type=body.member_type, user_id=body.user_id,
        agent_name=body.agent_name, role=body.role, actor=user.id,
    )
    await db.commit()
    return CollabMemberOut.model_validate(member)


@router.patch("/projects/{project_id}/members/{member_id}", response_model=CollabMemberOut)
async def update_member_role(
    project_id: UUID,
    member_id: UUID,
    body: CollabMemberUpdate,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    member = await service.update_member_role(db, project_id, member_id, role=body.role or "editor", actor=user.id)
    await db.commit()
    return CollabMemberOut.model_validate(member)


@router.delete("/projects/{project_id}/members/{member_id}", status_code=204)
async def remove_member(
    project_id: UUID,
    member_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    ok = await service.remove_member(db, project_id, member_id, actor=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="成员不存在")
    await db.commit()


# ── Sections ──


@router.get("/projects/{project_id}/sections", response_model=list[CollabSectionOut])
async def list_sections(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    sections = await service.list_sections(db, project_id)
    return [CollabSectionOut.model_validate(s) for s in sections]


@router.post("/projects/{project_id}/sections", response_model=CollabSectionOut, status_code=201)
async def create_section(
    project_id: UUID,
    body: CollabSectionCreate,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    sec = await service.create_section(
        db, project_id, title=body.title, parent_id=body.parent_id,
        word_count_target=body.word_count_target, user_id=user.id,
    )
    await db.commit()
    return CollabSectionOut.model_validate(sec)


@router.patch("/projects/{project_id}/sections/{section_id}", response_model=CollabSectionOut)
async def update_section(
    project_id: UUID,
    section_id: UUID,
    body: CollabSectionUpdate,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    sec = await service.update_section(db, section_id, **body.model_dump(exclude_unset=True))
    await db.commit()
    return CollabSectionOut.model_validate(sec)


# ── Tasks ──


@router.get("/projects/{project_id}/tasks", response_model=list[CollabTaskOut])
async def list_tasks(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    tasks = await service.list_tasks(db, project_id)
    return [CollabTaskOut.model_validate(t) for t in tasks]


@router.post("/projects/{project_id}/tasks", response_model=CollabTaskOut, status_code=201)
async def create_task(
    project_id: UUID,
    body: CollabTaskCreate,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    task = await service.create_task(
        db, project_id, title=body.title, kind=body.kind, user_id=user.id,
        section_ref=body.section_ref, doc_id=body.doc_id, context=body.context, due_at=body.due_at,
    )
    await db.commit()
    return CollabTaskOut.model_validate(task)


@router.post("/projects/{project_id}/tasks/{task_id}/assign", response_model=CollabTaskOut)
async def assign_task(
    project_id: UUID,
    task_id: UUID,
    body: CollabTaskAssign,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    task = await service.assign_task(
        db, project_id, task_id, assignee_type=body.assignee_type,
        user_id=body.user_id, agent_name=body.agent_name, actor=user.id,
    )
    await db.commit()
    return CollabTaskOut.model_validate(task)


@router.post("/projects/{project_id}/tasks/{task_id}/handoff", response_model=CollabTaskOut)
async def record_handoff(
    project_id: UUID,
    task_id: UUID,
    body: CollabTaskUpdate,  # 复用：state via status? 用专用 body
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    # 协调者手动记录交接：body 传 status 作为 handoff_state
    await service._require_member(db, project_id, user.id)
    state = body.status or "done"
    task = await service.record_handoff(
        db, project_id, task_id, state=state, payload={"notes": "manual", "by": str(user.id)}, actor=str(user.id),
    )
    await db.commit()
    return CollabTaskOut.model_validate(task)


@router.get("/projects/{project_id}/tasks/{task_id}", response_model=CollabTaskOut)
async def get_task(
    project_id: UUID,
    task_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    task = await db.get(service.CollabTask, task_id)
    if not task or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return CollabTaskOut.model_validate(task)


@router.patch("/projects/{project_id}/tasks/{task_id}", response_model=CollabTaskOut)
async def update_task(
    project_id: UUID,
    task_id: UUID,
    body: CollabTaskUpdate,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    task = await service.update_task(db, project_id, task_id, **body.model_dump(exclude_unset=True))
    await db.commit()
    return CollabTaskOut.model_validate(task)


@router.delete("/projects/{project_id}/tasks/{task_id}", status_code=204)
async def delete_task(
    project_id: UUID,
    task_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    task = await db.get(service.CollabTask, task_id)
    if not task or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    await db.delete(task)
    await db.commit()


# ── Agent runs ──


@router.post("/projects/{project_id}/tasks/{task_id}/runs", status_code=202)
async def spawn_agent_run(
    project_id: UUID,
    task_id: UUID,
    body: CollabRunSpawn,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    from .agent_bridge import spawn_run_for_task
    await service._require_member(db, project_id, user.id)
    try:
        run = await spawn_run_for_task(db, project_id, task_id, owner_id=user.id, agent_name=body.agent_name, prompt_override=body.prompt_override)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"run_id": str(run.id), "status": run.status}


@router.get("/projects/{project_id}/tasks/{task_id}/runs", response_model=list)
async def list_agent_runs(
    project_id: UUID,
    task_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    runs = await service.list_agent_runs(db, project_id, task_id=task_id)
    return [
        {
            "id": str(r.id), "thread_id": r.thread_id, "run_id": r.run_id, "agent_name": r.agent_name,
            "status": r.status, "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in runs
    ]


# ── Gates ──


@router.get("/projects/{project_id}/gates")
async def list_gates(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    gates = await service.list_gates(db, project_id)
    return [
        {
            "id": str(g.id), "task_id": str(g.task_id) if g.task_id else None, "scope": g.scope,
            "state": g.state, "mode": g.mode, "participants": g.participants,
            "deadline_at": g.deadline_at.isoformat() if g.deadline_at else None,
            "resolved_at": g.resolved_at.isoformat() if g.resolved_at else None,
            "revision": g.revision,
        }
        for g in gates
    ]


@router.post("/projects/{project_id}/gates/{gate_id}/judge")
async def judge_gate(
    project_id: UUID,
    gate_id: UUID,
    body: CollabGateJudge,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    gate = await service.judge_gate(
        db, project_id, gate_id, action=body.action, comment=body.comment, user_id=user.id,
    )
    await db.commit()
    return {"id": str(gate.id), "state": gate.state, "revision": gate.revision}


@router.post("/projects/{project_id}/gates/{gate_id}/reopen")
async def reopen_gate(
    project_id: UUID,
    gate_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    gate = await service.reopen_gate(db, project_id, gate_id, user_id=user.id)
    await db.commit()
    return {"id": str(gate.id), "state": gate.state, "revision": gate.revision}


# ── Publish / Activities ──


@router.post("/projects/{project_id}/publish-doc")
async def publish_doc(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    await service._require_member(db, project_id, user.id)
    result = await service.publish_doc(db, project_id, user_id=user.id)
    await db.commit()
    return result


@router.get("/projects/{project_id}/activities")
async def list_activities(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
):
    await service._require_member(db, project_id, user.id)
    acts = await service.list_activities(db, project_id, limit=limit)
    return [
        {
            "id": str(a.id), "actor_type": a.actor_type, "actor_id": a.actor_id,
            "action": a.action, "target": a.target, "detail": a.detail,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in acts
    ]
