"""Collab Workspace — agent 执行桥。

EAI-CUSTOM: 完全独立，不经 project MCP / enter_project / Temporal。

关键机制（评审已验证）：
- agent 在 **run 时**绑定：`POST /api/threads/{tid}/runs` 顶层 `context.agent_name`
  （`_CONTEXT_CONFIGURABLE_KEYS` 白名单，经 merge_run_context_overrides 转发进 configurable+context）。
  ⚠ 不放 config.configurable（build_run_config 遇 context 会丢弃 caller configurable）。
- CSRF：桥的 HTTP 调用非 CSRF 豁免，须镜像 ChannelManager._get_client：
  `X-CSRF-Token` header + `Cookie: csrf_token=...`，再叠加 internal auth + owner header。
- run 完成检测：轮询 `GET /api/threads/{tid}/runs/{run_id}` 至终态（无 POST /runs/{run_id}/wait）。
- 交接：agent 在沙箱 outputs/ 写 .handoff.json（4 态 schema），桥解析后回写 task。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.csrf_middleware import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, generate_csrf_token
from app.gateway.internal_auth import create_internal_auth_headers
from deerflow.config.paths import Paths as DeerFlowPaths

from .models import CollabAgentRun, CollabProject, CollabTask

logger = logging.getLogger(__name__)

# 网关地址（与现有 channel 模式一致：进程内 localhost）
GATEWAY_BASE = os.environ.get("GATEWAY_BASE_URL", "http://localhost:8001")

# .handoff.json 位置（thread 沙箱 outputs/）
HANDOFF_FILE = ".handoff.json"


def _internal_headers(owner_user_id: str) -> dict[str, str]:
    """internal auth + owner + CSRF（镜像 ChannelManager._get_client）。"""
    csrf = generate_csrf_token()
    headers = create_internal_auth_headers(owner_user_id=owner_user_id)
    headers[CSRF_HEADER_NAME] = csrf
    headers["Cookie"] = f"{CSRF_COOKIE_NAME}={csrf}"
    return headers


async def _create_thread(owner_user_id: str, project_id: UUID) -> str:
    """POST /api/threads（ThreadCreateRequest 只有 thread_id/assistant_id/metadata，无 agent_name）。"""
    import uuid

    thread_id = str(uuid.uuid4())
    async with httpx.AsyncClient(base_url=GATEWAY_BASE, headers=_internal_headers(owner_user_id)) as client:
        resp = await client.post(
            "/api/threads",
            json={
                "thread_id": thread_id,
                "metadata": {"workspace_project_id": str(project_id), "type": "collab_workspace"},
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        return thread_id


async def _spawn_run(owner_user_id: str, thread_id: str, agent_name: str, prompt: str) -> str:
    """POST /api/threads/{tid}/runs。agent 在顶层 context 绑定。"""
    async with httpx.AsyncClient(base_url=GATEWAY_BASE, headers=_internal_headers(owner_user_id)) as client:
        resp = await client.post(
            f"/api/threads/{thread_id}/runs",
            json={
                "input": {"messages": [{"role": "user", "content": prompt}]},
                # EAI-CUSTOM: agent_name 必须在顶层 context（白名单转发进 configurable+context）
                "context": {"agent_name": agent_name, "user_id": owner_user_id},
                "config": {},
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["run_id"]


async def _wait_run_terminal(owner_user_id: str, thread_id: str, run_id: str, max_duration: int) -> dict:
    """轮询 GET /api/threads/{tid}/runs/{run_id} 至终态。GET 无需 CSRF。"""
    async with httpx.AsyncClient(base_url=GATEWAY_BASE, headers=_internal_headers(owner_user_id)) as client:
        deadline = asyncio.get_event_loop().time() + max_duration
        while True:
            resp = await client.get(f"/api/threads/{thread_id}/runs/{run_id}", timeout=10.0)
            if resp.status_code == 404:
                return {"status": "missing"}  # rehydrate 遇死 run → 走失败路径
            if resp.status_code != 200:
                return {"status": "error", "detail": f"http {resp.status_code}"}
            data = resp.json()
            status = data.get("status", "running")
            if status in ("success", "completed", "done", "failed", "error", "cancelled"):
                return {"status": "success" if status in ("success", "completed", "done") else status}
            if asyncio.get_event_loop().time() > deadline:
                return {"status": "timed_out"}
            await asyncio.sleep(2.0)


def _build_prompt(project: CollabProject, task: CollabTask) -> str:
    """从 section/doc context 拼装 prompt，指示 agent 产出 markdown + .handoff.json。"""
    ctx = task.context or {}
    section_hint = ""
    if task.section_ref:
        section_hint = f"目标章节: {task.title}（section_id={task.section_ref}）"
    compliance = ctx.get("compliance_rules") or ""
    instructions = ctx.get("instructions") or task.title
    return (
        f"你是协作工作台中的一个 agent（项目：{project.name}，kind={project.kind}）。\n"
        f"{section_hint}\n"
        f"任务：{instructions}\n"
        f"合规要求（若有）：{compliance}\n\n"
        f"请完成以下工作：\n"
        f"1. 用 write_file 把结果写成 markdown 到 /mnt/user-data/outputs/report.md\n"
        f"2. 用 write_file 写 /mnt/user-data/outputs/{HANDOFF_FILE}，内容为 JSON：\n"
        f'   {{"state": "done", "progress_pct": 1.0, "content_delta": "完成", "notes": "..."}}\n'
        f"   state 可取 acked|progress|done|blocked。\n"
        f"3. 完成后 present_files 展示 report.md。\n"
        f"只做上述任务，不要调用无关工具。"
    )


async def spawn_run_for_task(
    db: AsyncSession,
    project_id: UUID,
    task_id: UUID,
    *,
    owner_id: UUID,
    agent_name: str | None = None,
    prompt_override: str | None = None,
) -> CollabAgentRun:
    """为 task 创建 thread + spawn run，登记 collab_agent_runs，后台轮询。"""
    task = await db.get(CollabTask, task_id)
    if not task or task.project_id != project_id:
        raise ValueError("Task not found")
    project = await db.get(CollabProject, project_id)

    resolved_agent = agent_name or task.assignee_agent_name
    if not resolved_agent:
        raise ValueError("未指定 agent（task 未指派给 agent 或未传 agent_name）")

    # 校验 agent 对 owner 存在（users/{uid}/agents/{name}）
    from deerflow.persistence.agents import get_agent_store

    store = get_agent_store()
    exists = await asyncio.to_thread(lambda: store.exists(resolved_agent, user_id=str(owner_id))) if hasattr(store, "exists") else True
    if not exists:
        raise ValueError(f"agent '{resolved_agent}' 对 owner 不存在")

    owner_user_id = str(owner_id)
    thread_id = await _create_thread(owner_user_id, project_id)

    prompt = prompt_override or _build_prompt(project, task)
    run_id = await _spawn_run(owner_user_id, thread_id, resolved_agent, prompt)

    run = CollabAgentRun(
        task_id=task.id,
        project_id=project_id,
        thread_id=thread_id,
        run_id=run_id,
        agent_name=resolved_agent,
        prompt_snapshot=prompt[:2000],
        status="running",
        started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).replace(tzinfo=None),
    )
    db.add(run)
    await db.flush()

    # 后台轮询（不阻塞请求；网关重启后由 rehydrate 兜底）
    asyncio.create_task(_poll_run_and_finish(db.bind, run.id, owner_user_id))
    return run


async def _poll_run_and_finish(bind, run_id: UUID, owner_user_id: str) -> None:
    """后台等 run 终态 → sandbox_sync → 解析 handoff → 更新 task → 触发闸门。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from .sandbox_sync import sync_sandbox_outputs

    session_factory = async_sessionmaker(bind, expire_on_commit=False)
    async with session_factory() as db:
        run = await db.get(CollabAgentRun, run_id)
        if not run:
            return
        task = await db.get(CollabTask, run.task_id) if run.task_id else None
        result = await _wait_run_terminal(owner_user_id, run.thread_id, run.run_id, run.max_duration)
        run.status = result["status"]
        run.finished_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).replace(tzinfo=None)

        if result["status"] in ("success", "timed_out"):
            # sandbox 同步（本地实现，不调 docmgr service）
            await sync_sandbox_outputs(db, run.project_id, run.thread_id, owner_user_id, run.agent_name)
            # 解析 .handoff.json
            handoff = await _read_handoff(db, run.project_id, run.thread_id, owner_user_id)
            if handoff:
                state = handoff.get("state", "done")
                if task:
                    from .service import record_handoff

                    await record_handoff(db, run.project_id, task.id, state=state, payload=handoff, actor=f"agent:{run.agent_name}")
                    await _trigger_gate_for_task(db, run.project_id, task.id, owner_user_id)
            elif result["status"] == "timed_out":
                if task:
                    task.status = "blocked"
                    task.last_error = "run timed out"
            else:
                # 有输出无 handoff → 视 done
                if task:
                    task.status = "done"
                    task.last_error = "no .handoff.json (treated as done)"
        elif result["status"] == "failed":
            if task:
                task.attempt_count += 1
                task.last_error = result.get("detail", "run failed")
                task.status = "pending"
        elif result["status"] == "missing":
            if task:
                task.attempt_count += 1
                task.last_error = "run missing after restart"
                task.status = "pending"
        else:
            if task:
                task.last_error = result.get("detail", "unknown run status")
        await db.commit()


async def _read_handoff(db: AsyncSession, project_id: UUID, thread_id: str, owner_user_id: str) -> dict | None:
    """读 thread 沙箱 outputs/.handoff.json。"""
    try:
        paths = DeerFlowPaths()
        sandbox_dir = paths.sandbox_user_data_dir(thread_id, user_id=owner_user_id)
        handoff_path = sandbox_dir / "outputs" / HANDOFF_FILE
        if not handoff_path.exists():
            # 兜底：扫其他 user 桶（gateway/extensions UUID split）
            users_dir = paths.base_dir / "users"
            if users_dir.is_dir():
                for bucket in sorted(users_dir.iterdir()):
                    if bucket.is_dir():
                        cand = bucket / "threads" / thread_id / "user-data" / "outputs" / HANDOFF_FILE
                        if cand.exists():
                            handoff_path = cand
                            break
        if handoff_path.exists():
            text = handoff_path.read_text(encoding="utf-8")
            return json.loads(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("read handoff failed: %r", exc)
    return None


async def _trigger_gate_for_task(db: AsyncSession, project_id: UUID, task_id: UUID, owner_user_id: str) -> None:
    """task 完成后触发关联闸门：agent 参与者自动批准，人类 quorum 评估。"""
    from sqlalchemy import select as _select

    from .gate import evaluate
    from .models import CollabGate

    gate = await db.scalar(
        _select(CollabGate).where(
            CollabGate.project_id == project_id,
            CollabGate.task_id == task_id,
            CollabGate.scope == "task",
            CollabGate.state == "pending",
        )
    )
    if not gate:
        return
    result = evaluate(gate, [])  # agent 自动批准由 resolve_judgments 处理
    if result.value == "pass":
        gate.state = "approved"
        gate.resolved_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).replace(tzinfo=None)
        gate.audit = list(gate.audit or []) + [{"at": gate.resolved_at.isoformat(), "by": "system", "action": "agent_task_complete"}]
        await db.flush()
