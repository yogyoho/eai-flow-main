"""Translation task enqueue (EAI-CUSTOM, T1).

knowledge 上传链钩子的后台入口：KB 翻译开关开启时，响应返回后在本任务里
解析→定语言/tag→建 pending 任务行。解析失败不阻塞入队（lang=mixed 兜底，
worker 阶段 T4 用全文再判/OCR）。开关关闭时上游根本不调用本函数——
这是 D17 回归契约的「关=零新行为」实现面。
"""

import asyncio
import logging

from sqlalchemy import select

from app.extensions.database import get_session_factory
from app.extensions.translation.langdetect import detect_language
from app.extensions.translation.models import TranslationTask
from app.extensions.translation.parsers import OcrRequired, blocks_text, classify_tag, parse_document

logger = logging.getLogger(__name__)


def should_enqueue(kb) -> bool:
    """D17 守卫：仅 KB 翻译开关显式开启才入队（缺列/None/False 一律零新行为）。"""
    return bool(getattr(kb, "translation_enabled", False))


async def enqueue_translation_task(
    *,
    kb_id,
    document_id,
    doc_sha: str,
    source_uri: str,
    file_path: str,
    quality_tier: str = "draft",
    factory=None,
) -> str | None:
    """解析文件定 lang/tag 并创建 pending 任务行；返回任务 id（失败记日志返回 None）。

    factory 可注入（MCP 子进程传入自己的 async_sessionmaker；gateway 内默认
    get_session_factory()）。幂等：同 KB 同 sha 已有非终态任务 → 复用返回其 id。
    """
    lang, tag = "mixed", None
    try:
        blocks = await asyncio.to_thread(parse_document, file_path)
        lang = detect_language(blocks_text(blocks))
        tag = classify_tag(blocks)
    except OcrRequired:
        logger.info("tlt enqueue %s: scanned file, lang/tag deferred to worker OCR", doc_sha[:8])
    except Exception:
        logger.exception("tlt enqueue %s: parse failed, deferring lang/tag to worker", doc_sha[:8])

    factory = factory or get_session_factory()
    # P2-14: 中文文档只索引不翻译（knowledge 上传链本身已入库/索引）。
    if lang == "zh":
        logger.info("tlt enqueue %s: zh document, skip translation task", doc_sha[:8])
        return None
    async with factory() as db:
        # 幂等：同 KB 同 sha 已有非终态任务 → 复用，不重复建（SHA-256 去重原则，构件1）
        existing = (
            await db.execute(
                select(TranslationTask)
                .where(
                    TranslationTask.kb_id == kb_id,
                    TranslationTask.doc_sha == doc_sha,
                    TranslationTask.state.notin_(["archived", "cancelled", "superseded"]),
                )
                .limit(1)
            )
        ).scalar()
        if existing is not None:
            logger.info("tlt enqueue %s: active task %s already exists, reuse", doc_sha[:8], existing.id)
            return str(existing.id)
        task = TranslationTask(
            kb_id=kb_id,
            document_id=document_id,
            doc_sha=doc_sha,
            source_uri=source_uri,
            source_lang=lang,
            content_tag=tag,
            state="pending",
            quality_tier=quality_tier,
        )
        db.add(task)
        await db.commit()
        logger.info("tlt task created %s (kb=%s lang=%s tag=%s)", task.id, kb_id, lang, tag)
        return str(task.id)
