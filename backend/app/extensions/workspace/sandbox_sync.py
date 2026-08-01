"""Collab Workspace — 沙箱→文档同步（workspace 本地实现）。

EAI-CUSTOM: 不调 docmgr/service.py::sync_thread_files（其内部 import ProjectMember，会传递耦合
到写作项目模块）。只经 SQLAlchemy 直接写共享数据表。

collab_versions 有 UniqueConstraint(doc_id, version) 且版本号由 collab server 拥有，
workspace 不直接 INSERT 猜版本；改调协编 REST POST /api/extensions/docmgr/documents/{doc_id}/versions
（本地调试路径；生产可换 internal-auth 变体）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.config.paths import Paths as DeerFlowPaths

from app.extensions.models import AIDocument

from .models import CollabProject, CollabSection

logger = logging.getLogger(__name__)

GATEWAY_BASE = "http://localhost:8001"


async def _resolve_outputs_dir(thread_id: str, owner_user_id: str) -> Path | None:
    """定位 thread 沙箱 outputs/ 目录（含 gateway/extensions UUID split 兜底）。"""
    paths = DeerFlowPaths()
    sandbox_dir = paths.sandbox_user_data_dir(thread_id, user_id=owner_user_id)
    outputs_dir = sandbox_dir / "outputs"
    if outputs_dir.exists():
        return outputs_dir
    users_dir = paths.base_dir / "users"
    if users_dir.is_dir():
        for bucket in sorted(users_dir.iterdir()):
            if bucket.is_dir():
                cand = bucket / "threads" / thread_id / "user-data" / "outputs"
                if cand.exists():
                    return cand
    return None


async def _resolve_target_doc(db: AsyncSession, project: CollabProject) -> UUID | None:
    """quickdoc → project.doc_id；report → 首个有 doc_id 的 section。"""
    if project.kind == "quickdoc":
        return project.doc_id
    sec = await db.scalar(
        select(CollabSection.doc_id)
        .where(CollabSection.project_id == project.id, CollabSection.doc_id.isnot(None))
        .order_by(CollabSection.sort_order)
        .limit(1)
    )
    return sec


async def _push_version(db: AsyncSession, doc_id: UUID, content: str) -> None:
    """调协编 REST 建版本（collab server 拥有版本号，避免 UniqueConstraint 冲突）。"""
    row = await db.execute(
        text("SELECT snapshot_text FROM collab_versions WHERE doc_id = :doc_id ORDER BY version DESC LIMIT 1"),
        {"doc_id": str(doc_id)},
    )
    existing = row.first()
    if existing and existing[0] == content:
        return
    try:
        async with httpx.AsyncClient(base_url=GATEWAY_BASE, timeout=15.0) as client:
            resp = await client.post(
                f"/api/extensions/docmgr/documents/{doc_id}/versions",
                json={"content": content, "summary": "agent sandbox sync"},
            )
            if resp.status_code >= 400:
                logger.warning("push_version http %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:  # noqa: BLE001
        logger.warning("push_version failed: %r", exc)


async def sync_sandbox_outputs(
    db: AsyncSession,
    project_id: UUID,
    thread_id: str,
    owner_user_id: str,
    agent_name: str,
) -> dict:
    """读 thread 沙箱 outputs/*.md → 写 ai_documents.content + collab_sections.content。"""
    outputs_dir = await _resolve_outputs_dir(thread_id, owner_user_id)
    if not outputs_dir:
        return {"synced": 0, "skipped": 0}

    project = await db.get(CollabProject, project_id)
    if not project:
        return {"synced": 0, "skipped": 0}

    target_doc_id = await _resolve_target_doc(db, project)
    if not target_doc_id:
        return {"synced": 0, "skipped": 0}

    synced = 0
    skipped = 0
    for md in sorted(outputs_dir.glob("*.md")):
        if md.name == "report.md":
            content = md.read_text(encoding="utf-8")
            doc = await db.get(AIDocument, target_doc_id)
            if doc:
                doc.content = content
                await _push_version(db, target_doc_id, content)
                synced += 1
            else:
                skipped += 1

    # report：同步首 section 的 content 快照
    if project.kind == "report" and synced:
        sec = await db.scalar(
            select(CollabSection)
            .where(CollabSection.project_id == project.id, CollabSection.doc_id == target_doc_id)
            .order_by(CollabSection.sort_order)
            .limit(1)
        )
        if sec:
            sec.content = (await db.get(AIDocument, target_doc_id)).content
            sec.word_count_current = len(sec.content or "")
            sec.revision += 1

    await db.flush()
    logger.info("sandbox_sync project=%s synced=%s skipped=%s", project_id, synced, skipped)
    return {"synced": synced, "skipped": skipped}
