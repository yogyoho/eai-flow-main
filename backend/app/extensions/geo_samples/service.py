# EAI-CUSTOM: forked from app.extensions.contract_price.service (geo-sample-bank Phase 1).
# Phase 1 无 skill 依赖——解析/脱敏全部 in-process async；compile 子进程模式留 Phase 2。
# ⚡ 调整 1：storage 的阻塞 MinIO 调用一律 asyncio.to_thread（本仓库有 blocking-IO 门，
#   T3 质量审查指定；parsers 的 CPU 重活已在 parsers.parse_document 内部 to_thread）。
# ⚡ 调整 3（质量审查 Important）：except 路径先 rollback 再守护式 commit——原异常可能
#   本身就是 DB 故障（PendingRollbackError/InterfaceError），裸 commit 会二次抛并丢失失败落账。
from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from . import crud, parsers, storage
from .redactor import redact_text

log = logging.getLogger("geo_samples.service")


# ⚡ 调整 2：finish_run 走 best-effort 包装（Task 7 实测落定）。plan 原文在 try 内裸调
# crud.finish_run，run-history 记账失败会把已 commit 成功的 parsed/redacted 状态改写成
# failed（状态机被记账层污染），且 except 分支里的二次 finish_run 抛异常会击穿「后台任务
# 不抛出」契约。记账是可观测性元数据：失败只 log.exception，run 行停留在 running，
# 绝不回滚管线结论。（也使 plan 测试里未 patch finish_run 的两条用例可用 MagicMock db 通过。）
async def _finish_run(db: AsyncSession, run_id: str, status: str, detail: str | None) -> None:
    try:
        await crud.finish_run(db, run_id, status, detail)
    except Exception:  # noqa: BLE001 —— 记账 best-effort，绝不掩盖管线结论
        log.exception("finish_run accounting failed for %s (status=%s)", run_id, status)


async def run_parse(db: AsyncSession, document_id: str, run_id: str) -> None:
    """后台任务：raw → md（work/）。任何异常 → status=failed + run 落账，除 db 会话彻底不可用外不向调用方抛出。
    R2 三段式：get → commit 释放连接 → 重活（OCR 最长 1800s）→ 重取文档校验漂移再落 parsed。
    重取用 populate_existing 绕过 identity map（expire_on_commit=False 下普通 get 看不到他方
    会话已提交的改判）；守卫丢弃非 uploaded/failed/parsed 的漂移态（今日可达路径已被端点级
    has_running_run 闸门封闭，本守卫防护 Phase 2 新增状态写入者（compiled 等））；doc 消失
    （理论删除路径）→ failed run。"""
    doc = await crud.get_document(db, document_id)
    if doc is None:
        await _finish_run(db, run_id, "failed", "document not found")
        return
    raw_uri, file_name, report_id = doc.raw_uri, doc.file_name, doc.report_id
    await db.commit()  # R2：释放连接再进重活（OCR 最长 1800s，占池会楔死无关请求）
    try:
        raw = await asyncio.to_thread(storage.get_object, raw_uri)
        md, mode = await parsers.parse_document(file_name, raw)  # 重活（内含 to_thread/OCR）
        doc = await crud.get_document_fresh(db, document_id)  # 重活后重取——populate_existing 绕过 identity map 才见 DB 真值
        if doc is None or doc.status not in ("uploaded", "failed", "parsed"):
            await _finish_run(db, run_id, "failed", f"document state changed during parse: {doc.status if doc else 'gone'}")
            return
        doc.work_uri = await asyncio.to_thread(storage.put_work, doc.report_id, md.encode("utf-8"))
        doc.parse_mode = mode
        doc.status = "parsed"
        await db.commit()
        await _finish_run(db, run_id, "done", f"mode={mode}")
    except Exception as exc:  # noqa: BLE001 —— 后台任务必须吞异常落账
        log.exception("parse failed for %s (%s)", report_id, document_id)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            log.exception("rollback failed after parse failure (%s)", document_id)
        doc.status = "failed"
        doc.parse_mode = "failed"
        try:
            await db.commit()
        except Exception:  # noqa: BLE001
            log.exception("failure-status commit failed (%s) — doc keeps prior status", document_id)
        await _finish_run(db, run_id, "failed", f"{type(exc).__name__}: {exc}")


async def run_redact(db: AsyncSession, document_id: str, run_id: str) -> None:
    """后台任务：work/parsed.md → 规则脱敏 → clean/source.md + 事件流水。
    事件与 doc 状态在同一 commit 原子落库（crud.add_redactions 不自行 commit）；
    异常 → status=failed + run 落账，除 db 会话彻底不可用外不向调用方抛出。"""
    doc = await crud.get_document(db, document_id)
    if doc is None:
        await _finish_run(db, run_id, "failed", "document not found")
        return
    try:
        text_bytes = await asyncio.to_thread(storage.get_object, doc.work_uri)
        clean, events = redact_text(text_bytes.decode("utf-8"))
        doc.clean_uri = await asyncio.to_thread(storage.put_clean, doc.report_id, clean.encode("utf-8"))
        await crud.add_redactions(db, doc.id, events)
        summary: dict[str, int] = {}
        for e in events:
            summary[e["rule"]] = summary.get(e["rule"], 0) + 1
        doc.redaction_summary = json.dumps(summary, ensure_ascii=False)
        doc.status = "redacted"
        await db.commit()
        await _finish_run(db, run_id, "done", json.dumps(summary, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        log.exception("redact failed for %s (%s)", getattr(doc, "report_id", "?"), document_id)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            log.exception("rollback failed after redact failure (%s)", document_id)
        doc.status = "failed"
        try:
            await db.commit()
        except Exception:  # noqa: BLE001
            log.exception("failure-status commit failed (%s) — doc keeps prior status", document_id)
        await _finish_run(db, run_id, "failed", f"{type(exc).__name__}: {exc}")


async def apply_review(db: AsyncSession, document_id: str, decision: str, note: str | None) -> None:
    """人工抽审闸门：approve → reviewed；reject → 退回 redacted 并留 note。"""
    doc = await crud.get_document(db, document_id)
    if doc is None:
        raise ValueError("document not found")
    if doc.status != "redacted":
        raise ValueError(f"仅 redacted 状态可审（当前 {doc.status}）")
    if decision not in ("approve", "reject"):
        raise ValueError("decision 必须是 approve/reject")
    doc.status = "reviewed" if decision == "approve" else "redacted"
    doc.review_note = note
    await db.commit()
