"""Translation worker (EAI-CUSTOM, T4).

设计构件 3（完整状态机）+ eng-review 决议：
  D16 = 2 个独立 claimer 循环（每槽一次一任务）+ 同步段 asyncio.to_thread +
        全局 LLM 信号量 ≤2
  D18 = gateway 内嵌（lifespan 启动）；boot recovery：启动时 running→pending
  R3-1 = 重传取消：任务在起点与块边界检查 superseded/cancelled 后中止
  R7/A-1 = 基础设施失败（LLM/OCR/block树/MinIO/RAGFlow）→ 指数退避 ≤3 → failed
  R2-7 = 数值轴：占位符回注对账 + 全文多重集归一化比对并行
  R2-1 = 机检失败 → check_failed → retrying(≤2 重生成数值违例块) → exceeded

translator / index_fn 可注入（测试 fake；index_fn 默认=ragflow_bridge，T6 落地）。
"""

import asyncio
import difflib
import logging
import os
import uuid as _uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text, update

from app.extensions.database import get_session_factory
from app.extensions.translation import checks
from app.extensions.translation.langdetect import detect_language
from app.extensions.translation.models import TltBackfillJob, TranslationTask
from app.extensions.translation.parsers import (
    OcrRequired,
    blocks_text,
    classify_tag,
    ocr_pdf,
    parse_document,
)
from app.extensions.translation.settings import (
    SETTINGS_KEY,
    read_translation_settings,
    resolve_effective_model_name,
)

logger = logging.getLogger(__name__)

POLL_SECONDS = float(os.environ.get("EAI_TRANSLATION_POLL_SECONDS", "5"))
SLOTS = int(os.environ.get("EAI_TRANSLATION_SLOTS", "2"))  # D16
MAX_INFRA_RETRIES = int(os.environ.get("EAI_TRANSLATION_INFRA_RETRIES", "3"))  # R7 失败链
BACKFILL_POLL_SECONDS = float(os.environ.get("EAI_TLT_BACKFILL_POLL_SECONDS", "5"))
MAX_CHECK_RETRIES = 2  # R2-1: retrying ≤2 后 exceeded
LLM_SEMAPHORE = asyncio.Semaphore(SLOTS)  # 全局信号量 ≤2（D16）

TranslateFn = Callable[[str, str, str], Awaitable[dict]]
IndexFn = Callable[[TranslationTask, list, list], Awaitable[None]]


def _default_index_fn() -> IndexFn:
    """T6 落地前的显式缺口：索引未接 → 抛错落 failed（绝不静默假交付）。"""
    from app.extensions.translation import ragflow_bridge

    return ragflow_bridge.index_translation


# ── boot recovery（D18/R7）────────────────────────────────────────────


async def boot_recovery() -> int:
    """启动时把遗留 running 任务重置为 pending 续跑（幂等键=doc sha+task_version）。"""
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(update(TranslationTask).where(TranslationTask.state == "running").values(state="pending"))
        await db.commit()
        n = result.rowcount or 0
        if n:
            logger.info("tlt boot recovery: %d running task(s) reset to pending", n)
        return n


# ── 状态辅助 ──────────────────────────────────────────────────────────


async def _set_state(task_id: str, allowed_from: set[str], target: str) -> str | None:
    """守卫式流转：仅当当前状态 ∈ allowed_from 时置 target；否则返回 None（状态已被并发移动）。"""
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(update(TranslationTask).where(TranslationTask.id == _uuid.UUID(str(task_id)), TranslationTask.state.in_(allowed_from)).values(state=target))
        await db.commit()
        if (result.rowcount or 0) == 0:
            logger.warning("tlt task %s: transition %s->%s skipped (state moved)", task_id, sorted(allowed_from), target)
            return None
        return target


async def _current_state(task_id: str) -> str | None:
    factory = get_session_factory()
    async with factory() as db:
        task = await db.get(TranslationTask, _uuid.UUID(str(task_id)))
        return task.state if task else None


async def _record_gates(task_id: str, gate_failures: dict | None, uncertain: list) -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(update(TranslationTask).where(TranslationTask.id == _uuid.UUID(str(task_id))).values(gate_failures=gate_failures or None, uncertainty=uncertain))
        await db.commit()


async def _persist_detection(task_id: str, lang: str, tag: str | None) -> None:
    """把 worker 检测出的语言/tag 回写任务行（P0-3：资产上传时未能判定的在 OCR 后补）。"""
    values: dict[str, object] = {"source_lang": lang}
    if tag:
        values["content_tag"] = tag
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(update(TranslationTask).where(TranslationTask.id == _uuid.UUID(str(task_id))).values(**values))
        await db.commit()


async def _record_draft(task_id: str, zh_blocks: list[dict], source_blocks: list) -> None:
    """exceeded 前保存逐块草稿 + 源文快照，供复核对照/通过后索引（P0-1/P1-8）。"""
    source_snapshot = [{"id": b.id, "type": b.type, "text": b.text} for b in source_blocks]
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(update(TranslationTask).where(TranslationTask.id == _uuid.UUID(str(task_id))).values(draft_blocks=zh_blocks, draft_source_blocks=source_snapshot))
        await db.commit()


async def _record_backtranslation(task_id: str, items: list[dict]) -> None:
    """回译诊断写入 error_detail（P2-12；不改变 payload，只供复核定位）。"""
    if not items:
        return
    factory = get_session_factory()
    async with factory() as db:
        task = await db.get(TranslationTask, _uuid.UUID(str(task_id)))
        if task is None:
            return
        detail = dict(task.error_detail or {})
        detail["backtranslation"] = items
        task.error_detail = detail
        await db.commit()


async def _diagnose_backtranslation(translator, blocks, zh_blocks, block_ids: set[str], lang: str) -> list[dict]:
    """exceeded 前定向回译诊断：只对失败/不确定块（最多 5 个）做回译比对。

    注入 translator 无 back_translate 时跳过（测试/自定义 translator 兼容）。
    """
    back_translate = getattr(translator, "back_translate", None)
    if back_translate is None:
        return []
    src = {b.id: b.text for b in blocks}
    zh = {z["id"]: z["text"] for z in zh_blocks}
    items: list[dict] = []
    for block_id in list(block_ids)[:5]:
        if block_id not in src or block_id not in zh:
            continue
        try:
            async with LLM_SEMAPHORE:
                back = await back_translate(block_id, zh[block_id], lang)
        except Exception:
            logger.warning("tlt back-translate failed for block %s", block_id, exc_info=True)
            continue
        ratio = difflib.SequenceMatcher(None, src[block_id].casefold(), str(back).casefold()).ratio()
        items.append({"block": block_id, "source": src[block_id], "back": str(back), "ratio": round(ratio, 3), "drift": ratio < 0.6})
    return items


async def _is_aborted(task_id: str) -> bool:
    state = await _current_state(task_id)
    return state in {"superseded", "cancelled", None}


# ── 单任务管线 ────────────────────────────────────────────────────────


async def run_task(
    task_id: str,
    *,
    translator: Any = None,
    index_fn: IndexFn | None = None,
    glossary: Any = None,
) -> str:
    """执行一个任务到终态/中途态；返回最终 state。

    translator: 可注入（默认 BlockTranslator+glossary）；index_fn: 可注入（默认 ragflow_bridge）；
    glossary: 可注入（默认 load_glossary()）。基础设施失败 → 退避重试 ≤3 → failed；
    机检不过 → check_failed/retrying/exceeded。
    """
    from app.extensions.translation.glossary import load_glossary
    from app.extensions.translation.translator import BlockTranslator

    index_fn = index_fn or _default_index_fn()

    # 起点：pending（直调）或 running（claimer 已置）——两者都可进入管线
    state = await _current_state(task_id)
    if state in {"superseded", "cancelled"}:
        return state or "missing"
    if state == "pending":
        if await _set_state(task_id, {"pending"}, "running") is None:
            return "claimed_elsewhere"
    elif state != "running":
        return state or "missing"

    async with get_session_factory()() as db:
        task = await db.get(TranslationTask, _uuid.UUID(str(task_id)))
        if task is None:
            return "missing"
        file_path, lang, quality_tier = task.source_uri or "", task.source_lang, task.quality_tier

    # 块边界/起点 superseded 检查（R3-1）
    if await _is_aborted(task_id):
        return "superseded"

    # 解析（同步段 to_thread）；扫描件走 OCR；OCR 故障=基础设施失败（R7/SC-3）
    try:
        try:
            blocks = await asyncio.to_thread(parse_document, file_path)
        except OcrRequired:
            blocks = await ocr_pdf(file_path)
    except Exception as exc:
        return await _infra_fail(task_id, exc, phase="parse")
    if await _is_aborted(task_id):
        return "superseded"

    # 语言兜底（enqueue 阶段 deferred 的扫描件：OCR 文本再判），并回写任务行
    if lang in {"mixed", "", None}:
        lang = detect_language(blocks_text(blocks)) or "mixed"
    await _persist_detection(task_id, lang, classify_tag(blocks))

    # P2-14: 中文文档只索引不翻译（原文由上传链入库；任务标记为 skipped 终态）。
    if lang == "zh":
        cur = await _current_state(task_id)
        if cur in {"stored", "pending", "running", "retrying"}:
            await _set_state(task_id, {cur}, "skipped")
        return "skipped"

    glossary = glossary or load_glossary()
    if translator is None:
        # 模型选择：UI 设置 > EAI_TRANSLATION_MODEL > config.yaml 首项。
        # 每个任务读取一次，设置变更对下一次翻译/重跑生效。
        setting = (await asyncio.to_thread(read_translation_settings)).get(SETTINGS_KEY)
        model_name = resolve_effective_model_name(setting if isinstance(setting, str) else None)
        model = None
        if model_name:
            from deerflow.models.factory import create_chat_model

            model = create_chat_model(model_name)
            logger.info("tlt task %s using translation model %s", task_id, model_name)
        translator = BlockTranslator(model=model)

    # 翻译 + 三轴机检 + 重试循环（R2-1: retrying ≤2 重生成数值违例块）
    attempt = 0
    regenerate_ids: set[str] = set()
    prev_good: dict[str, str] = {}
    src_types = [b.type for b in blocks]
    uncertain: list[dict] = []
    zh_blocks: list[dict] = []

    while True:
        placeholder_registry = checks.Registry()
        zh_blocks = []
        uncertain = []

        for block in blocks:
            if await _is_aborted(task_id):
                return "superseded"
            if block.id in regenerate_ids or not regenerate_ids:
                placeholder_text = checks.extract_placeholders(block.text, placeholder_registry)
                try:
                    async with LLM_SEMAPHORE:
                        # 只注入命中本 block 的术语，控制大术语表的 token 开销。
                        result = await translator.translate_block(
                            block.id,
                            placeholder_text,
                            lang,
                            glossary_prompt=glossary.prompt_fragment(block.text, lang),
                        )
                except Exception as exc:
                    return await _infra_fail(task_id, exc, phase="llm")
                zh_text = checks.reinject_placeholders(str(result.get("translation", "")), placeholder_registry)
                if result.get("uncertain"):
                    uncertain.append({"block": block.id, "spans": result.get("low_confidence_spans", [])})
            else:
                zh_text = prev_good.get(block.id, block.text)
            zh_blocks.append({"id": block.id, "type": block.type, "text": zh_text, "meta": dict(block.meta)})

        # 三轴机检（前提 5）
        source_text = blocks_text(blocks)
        translated_text = "\n".join(z["text"] for z in zh_blocks)
        numeric_v = checks.run_numeric_axis(source_text, translated_text, lang)
        structure_v = checks.structure_parity_violations(src_types, [z["type"] for z in zh_blocks])
        force_terms, dont_translate = glossary.for_language(lang)
        term_v = checks.terminology_violations(source_text, translated_text, force_terms, dont_translate)
        gate_failures: dict[str, list[str]] = {}
        if numeric_v:
            gate_failures["numeric"] = numeric_v
        if structure_v:
            gate_failures["structure"] = structure_v
        if term_v:
            gate_failures["terminology"] = term_v

        if not gate_failures:
            # P1-6 reviewed 档：机检全绿也进人工复核队列（MTPE 编辑仍为二期）；
            # draft 档维持机检绿即交付。
            if quality_tier == "reviewed":
                await _record_draft(task_id, zh_blocks, blocks)
                await _record_gates(task_id, None, uncertain)
                cur = await _current_state(task_id)
                if cur not in {"running", "retrying"}:
                    return cur or "missing"
                final = await _set_state(task_id, {cur}, "exceeded")
                return final or "exceeded"
            break

        attempt += 1
        cur = await _current_state(task_id)
        if cur not in {"running", "retrying"}:
            return cur or "missing"
        if await _set_state(task_id, {cur}, "check_failed") is None:
            return cur
        await _record_gates(task_id, gate_failures, uncertain)
        # P2-13 逐轴定位失败块：数值/术语/结构 + LLM 不确定段，重生成并集（≤2 次）。
        zh_by_id = {z["id"]: z["text"] for z in zh_blocks}
        src_types_by_id = {b.id: b.type for b in blocks}
        zh_types_by_id = {z["id"]: z["type"] for z in zh_blocks}
        numeric_bad = {z["id"] for z in zh_blocks if checks.numeric_multiset_violations(next((b.text for b in blocks if b.id == z["id"]), ""), z["text"], lang)}
        term_bad = {b.id for b in blocks if checks.terminology_violations(b.text, zh_by_id.get(b.id, ""), force_terms, dont_translate)} if term_v else set()
        structure_bad = {bid for bid, btype in src_types_by_id.items() if zh_types_by_id.get(bid) != btype}
        uncertain_bad = {item["block"] for item in uncertain}
        bad_ids = numeric_bad | term_bad | structure_bad | uncertain_bad
        if attempt > MAX_CHECK_RETRIES or not bad_ids:
            # P2-12 回译自检：exceeded 前定向诊断失败/不确定块（最多 5 个），不常开。
            diagnostics = await _diagnose_backtranslation(translator, blocks, zh_blocks, bad_ids or {b.id for b in blocks[:3]}, lang)
            await _record_backtranslation(task_id, diagnostics)
            await _record_draft(task_id, zh_blocks, blocks)
            final = await _set_state(task_id, {"check_failed"}, "exceeded")
            return final or "exceeded"
        if await _set_state(task_id, {"check_failed"}, "retrying") is None:
            return "check_failed"
        regenerate_ids = set(bad_ids)
        prev_good = {z["id"]: z["text"] for z in zh_blocks if z["id"] not in regenerate_ids}

    # 机检全绿：running/retrying → indexed（RAGFlow 双份索引在 index_fn 内，T6 落地）
    cur = await _current_state(task_id)
    if await _set_state(task_id, {"running", "retrying"}, "indexed") is None:
        return cur or "indexed_blocked"
    task_row = await _reload_task(task_id)
    try:
        await index_fn(task_row, zh_blocks, blocks)
    except Exception as exc:
        # indexed → 交付阶段基础设施失败（幂等重跑，R7/A-1）
        return await _infra_fail(task_id, exc, phase="index")
    final = await _set_state(task_id, {"indexed"}, "delivered")
    return final or "delivered"


async def _reload_task(task_id: str) -> TranslationTask:
    factory = get_session_factory()
    async with factory() as db:
        task = await db.get(TranslationTask, _uuid.UUID(str(task_id)))
        await db.refresh(task)
        return task


async def _infra_fail(task_id: str, exc: Exception, phase: str) -> str:
    """基础设施失败：重试计数 ≤3 → 回 pending（poll 间隔即天然退避）；超限 → failed 终态（R7 失败链）。"""
    factory = get_session_factory()
    async with factory() as db:
        task = await db.get(TranslationTask, _uuid.UUID(str(task_id)))
        if task is None:
            return "missing"
        if task.state in {"archived", "cancelled", "superseded"}:
            return task.state  # 库删除/取消后不复活（R3-3 语义优先于重试链）
        task.retry_count = (task.retry_count or 0) + 1
        task.error_detail = {
            "phase": phase,
            "error": repr(exc)[:500],
            "attempts": task.retry_count,
            "at": datetime.now(UTC).isoformat(),
        }
        if task.retry_count >= MAX_INFRA_RETRIES:
            task.state = "failed"
            logger.error("tlt task %s infra failure terminal (%s): %s", task_id, phase, repr(exc)[:200])
        else:
            logger.warning("tlt task %s infra failure attempt %d/%d (%s): %s", task_id, task.retry_count, MAX_INFRA_RETRIES, phase, repr(exc)[:200])
            task.state = "pending"
        await db.commit()
        return task.state


# ── 槽位循环（D16）────────────────────────────────────────────────────


async def _claim_next_task() -> str | None:
    """FOR UPDATE SKIP LOCKED 领取一个 pending 任务（两槽互不争抢）。"""
    factory = get_session_factory()
    async with factory() as db:
        row = (await db.execute(text("SELECT id FROM tlt_translation_tasks WHERE state = 'pending' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"))).scalar()
        if row is None:
            return None
        await db.execute(text("UPDATE tlt_translation_tasks SET state='running' WHERE id = :id"), {"id": str(row)})
        await db.commit()
        return str(row)


async def _worker_loop(slot: int, stop: asyncio.Event, index_fn: IndexFn | None = None) -> None:
    logger.info("tlt worker slot %d started (poll=%.1fs)", slot, POLL_SECONDS)
    while not stop.is_set():
        try:
            task_id = await _claim_next_task()
        except Exception:
            logger.exception("tlt worker slot %d: claim failed", slot)
            task_id = None
        if task_id is None:
            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
            except TimeoutError:
                pass
            continue
        try:
            final = await run_task(task_id, index_fn=index_fn)
            logger.info("tlt worker slot %d: task %s -> %s", slot, task_id, final)
        except Exception:
            logger.exception("tlt worker slot %d: task %s crashed", slot, task_id)
            await _infra_fail(task_id, Exception("worker crash"), phase="worker")


async def start_translation_worker(index_fn: IndexFn | None = None) -> asyncio.Task:
    """lifespan 入口：boot recovery + SLOTS 槽循环（D18/D16）。"""
    await boot_recovery()
    stop = asyncio.Event()

    async def _runner() -> None:
        await asyncio.gather(*(_worker_loop(i, stop, index_fn) for i in range(SLOTS)))

    runner = asyncio.create_task(_runner())
    runner.stop_event = stop  # type: ignore[attr-defined]
    return runner


async def stop_translation_worker(runner: asyncio.Task) -> None:
    stop = getattr(runner, "stop_event", None)
    if stop is not None:
        stop.set()
    try:
        await asyncio.wait_for(asyncio.shield(runner), timeout=10)
    except (TimeoutError, asyncio.CancelledError):
        runner.cancel()


# ── 超大回填调度（P2：tlt_backfill_jobs 每 tick 放一批进 pending）─────────


async def run_backfill_tick(job_id: str | None = None) -> dict:
    """推进一个 active 回填任务：chunk_size 个 stored/failed → pending。"""
    factory = get_session_factory()
    async with factory() as db:
        if job_id:
            row = (await db.execute(text("SELECT id FROM tlt_backfill_jobs WHERE id = :jid AND state='active' FOR UPDATE SKIP LOCKED"), {"jid": job_id})).scalar()
        else:
            row = (await db.execute(text("SELECT id FROM tlt_backfill_jobs WHERE state='active' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"))).scalar()
        if row is None:
            return {"advanced": 0}
        job = await db.get(TltBackfillJob, _uuid.UUID(str(row)))
        if job is None:
            return {"advanced": 0}
        ids = list(job.task_ids or [])
        start = job.cursor
        chunk = ids[start : start + max(1, job.chunk_size)]
        queued = 0
        for raw in chunk:
            try:
                task_id = _uuid.UUID(str(raw))
            except (TypeError, ValueError):
                continue
            task = await db.get(TranslationTask, task_id)
            if task is not None and task.state in {"stored", "failed"}:
                task.state = "pending"
                queued += 1
        job.cursor = min(start + len(chunk), len(ids))
        if job.cursor >= len(ids):
            job.state = "done"
        await db.commit()
        stats = {"job": str(job.id), "queued": queued, "cursor": job.cursor, "total": len(ids), "done": job.state == "done"}
        logger.info("tlt backfill tick: %s", stats)
        return stats


async def _backfill_loop(stop: asyncio.Event) -> None:
    logger.info("tlt backfill scheduler started (poll=%.1fs)", BACKFILL_POLL_SECONDS)
    while not stop.is_set():
        try:
            await run_backfill_tick()
        except Exception:
            logger.exception("tlt backfill tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=BACKFILL_POLL_SECONDS)
        except TimeoutError:
            pass


async def start_translation_backfill() -> asyncio.Task:
    """lifespan 入口：回填任务调度循环。"""
    stop = asyncio.Event()
    runner = asyncio.create_task(_backfill_loop(stop))
    runner.stop_event = stop  # type: ignore[attr-defined]
    return runner


async def stop_translation_backfill(runner: asyncio.Task) -> None:
    stop = getattr(runner, "stop_event", None)
    if stop is not None:
        stop.set()
    try:
        await asyncio.wait_for(asyncio.shield(runner), timeout=10)
    except (TimeoutError, asyncio.CancelledError):
        runner.cancel()
