"""Translation MCP server (EAI-CUSTOM, T5) — agent-side task tools.

Exposes translation task management to the chat agent via function-calling:
  translate_document(kb_id, file_path, quality_tier) — 入队（KB 须已开翻译开关）
  translation_status(task_id)                        — 状态/机检明细/不确定段

R7 鉴权边界：stdio 子进程无用户身份，owner 语义由 knowledge_scope 准入承担
（agent 只能引用已准入 KB 的 id）；工具侧加 translation_enabled 守卫 +
task 存在性校验。人工流转/复核走管理 API（/api/extensions/translation/*），
不经 MCP——与 contract_price「流水线不暴露给 agent」同一原则。

DB: extensions DB；env ``TLT_QUERY_DB_URL`` 覆盖（同 CPA_QUERY_DB_URL 惯例）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from sqlalchemy import select

from app.extensions.translation.models import TranslationTask

server = Server("translation")


async def _resolve_db_url() -> str:
    if os.environ.get("TLT_QUERY_DB_URL"):
        return os.environ["TLT_QUERY_DB_URL"]
    from app.extensions.config import get_extensions_config

    return get_extensions_config().database.url


async def _run_in_db(func):
    """Run func(session) against the extensions DB with a short-lived engine."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(await _resolve_db_url(), pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            return await func(session)
    finally:
        await engine.dispose()


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


def _err(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": message}, ensure_ascii=False))]


def _task_out(t: TranslationTask) -> dict[str, Any]:
    return {
        "task_id": str(t.id),
        "kb_id": str(t.kb_id),
        "doc_sha": t.doc_sha[:12],
        "state": t.state,
        "source_lang": t.source_lang,
        "content_tag": t.content_tag,
        "quality_tier": t.quality_tier,
        "progress": t.progress,
        "gate_failures": t.gate_failures,
        "uncertain_blocks": [u.get("block") for u in (t.uncertainty or [])],
        "error_detail": t.error_detail,
        "superseded_by": str(t.superseded_by) if t.superseded_by else None,
    }


async def _handle_translate(arguments: dict) -> list[TextContent]:
    kb_id = str(arguments.get("kb_id", "")).strip()
    file_path = str(arguments.get("file_path", "")).strip()
    quality_tier = str(arguments.get("quality_tier", "draft")).strip().lower()
    if not kb_id or not file_path:
        return _err("kb_id and file_path are required")
    if quality_tier not in {"draft", "reviewed"}:
        return _err("quality_tier must be 'draft' or 'reviewed'")
    try:
        kb_uuid = UUID(kb_id)
    except ValueError:
        return _err(f"invalid kb_id: {kb_id}")

    resolved = str(Path(file_path).resolve())

    try:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.extensions.models import KnowledgeBase
        from app.extensions.translation.enqueue import enqueue_translation_task

        engine = create_async_engine(await _resolve_db_url(), pool_size=2, max_overflow=0)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                kb = await session.get(KnowledgeBase, kb_uuid)
                if kb is None:
                    return _err(f"kb not found: {kb_id}")
                if not bool(getattr(kb, "translation_enabled", False)):
                    return _err("kb translation is not enabled (translation_enabled=false)")

            sha = hashlib.sha256(Path(resolved).read_bytes()).hexdigest()
            # enqueue 自带幂等（同 KB 同 sha 活动任务复用）；同一 factory 落库
            task_id = await enqueue_translation_task(
                kb_id=kb_uuid,
                document_id=None,
                doc_sha=sha,
                source_uri=resolved,
                file_path=resolved,
                quality_tier=quality_tier,
                factory=factory,
            )
            if task_id is None:
                return _err("enqueue failed (see gateway logs)")
            async with factory() as session:
                task = await session.get(TranslationTask, UUID(task_id))
                await session.refresh(task)
                return _ok({"reused": task.state != "pending" or task.progress > 0, **_task_out(task)})
        finally:
            await engine.dispose()
    except Exception as exc:  # noqa: BLE001 — MCP 边界统一转 JSON 错误
        return _err(f"translate_document failed: {exc!r}")


async def _handle_status(arguments: dict) -> list[TextContent]:
    task_id = str(arguments.get("task_id", "")).strip()
    kb_id = str(arguments.get("kb_id", "")).strip()
    try:
        async def _q(session):
            if task_id:
                t = await session.get(TranslationTask, UUID(task_id))
                if t is None:
                    return _err(f"task not found: {task_id}")
                return _ok(_task_out(t))
            if kb_id:
                rows = (
                    await session.execute(
                        select(TranslationTask)
                        .where(TranslationTask.kb_id == UUID(kb_id))
                        .order_by(TranslationTask.created_at.desc())
                        .limit(20)
                    )
                ).scalars()
                return _ok({"items": [_task_out(t) for t in rows]})
            return _err("task_id or kb_id required")

        return await _run_in_db(_q)
    except Exception as exc:  # noqa: BLE001
        return _err(f"translation_status failed: {exc!r}")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="translate_document",
            description=(
                "把一份已上传的文档（docx/xlsx/pptx/pdf/txt/md；相对路径基于当前线程工作区）"
                "提交到指定知识库的翻译队列。KB 必须已开启 translation_enabled。"
                "quality_tier: draft=机检即交付（默认）/ reviewed=走人工后编辑定稿。"
                "返回任务状态（state=pending 即已入队）。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "kb_id": {"type": "string", "description": "目标知识库 id"},
                    "file_path": {"type": "string", "description": "文档路径（相对当前工作区或绝对路径）"},
                    "quality_tier": {"type": "string", "enum": ["draft", "reviewed"], "description": "质量档，默认 draft"},
                },
                "required": ["kb_id", "file_path"],
            },
        ),
        Tool(
            name="translation_status",
            description=(
                "查翻译任务状态：机检失败会给逐轴明细（numeric/structure/terminology），"
                "exceeded=待人工复核，failed=基础设施错误（含 phase）。传 task_id 查单条，传 kb_id 列最近 20 条。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务 id（与 kb_id 二选一）"},
                    "kb_id": {"type": "string", "description": "知识库 id（列最近任务）"},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "translate_document":
        return await _handle_translate(arguments)
    if name == "translation_status":
        return await _handle_status(arguments)
    return _err(f"unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
