# EAI-CUSTOM: forked from app.extensions.contract_price.crud (geo-sample-bank Phase 1).
"""Async CRUD helpers for the gsb_ tables (dedup, listing filters, run history)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import GsbDocument, GsbRedaction, GsbRunHistory, utc_now


async def find_duplicate_document(db: AsyncSession, file_hash: str, exclude_uri: str | None = None) -> GsbDocument | None:
    """同 hash 不同 storage_uri → 重复（同 uri=原地重传不算）。

    Exclusion pushed into SQL so ``limit(1)`` is applied after filtering —
    correct even if one hash ever lands on two rows (e.g. newest row is the
    in-place re-upload, older row is the true duplicate). Deviation from plan
    literal: single ``scalar_one_or_none`` instead of a fetch-all Python loop.
    """
    stmt = select(GsbDocument).where(GsbDocument.file_hash == file_hash, GsbDocument.raw_uri.is_not(None))
    if exclude_uri is not None:
        stmt = stmt.where(GsbDocument.raw_uri != exclude_uri)
    return (await db.execute(stmt.limit(1))).scalar_one_or_none()


async def get_document(db: AsyncSession, document_id: str) -> GsbDocument | None:
    return (await db.execute(select(GsbDocument).where(GsbDocument.id == document_id))).scalar_one_or_none()


async def get_document_by_report_id(db: AsyncSession, report_id: str) -> GsbDocument | None:
    return (await db.execute(select(GsbDocument).where(GsbDocument.report_id == report_id))).scalar_one_or_none()


async def list_documents(db: AsyncSession, stage: str | None = None, mineral: str | None = None, status: str | None = None, skip: int = 0, limit: int = 50) -> list[GsbDocument]:
    stmt = select(GsbDocument).order_by(GsbDocument.created_at.desc(), GsbDocument.id.desc())
    if stage:
        stmt = stmt.where(GsbDocument.stage == stage)
    if mineral:
        stmt = stmt.where(GsbDocument.mineral == mineral)
    if status:
        stmt = stmt.where(GsbDocument.status == status)
    stmt = stmt.offset(skip).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def list_redactions(db: AsyncSession, document_id: str) -> list[GsbRedaction]:
    stmt = select(GsbRedaction).where(GsbRedaction.document_id == document_id).order_by(GsbRedaction.start)
    return list((await db.execute(stmt)).scalars().all())


async def add_redactions(db: AsyncSession, document_id: str, events: list[dict]) -> None:
    for e in events:
        db.add(GsbRedaction(document_id=document_id, rule=e["rule"], mode=e["mode"], start=e["start"], end=e["end"], original_hash=e["original_hash"]))


async def create_run(db: AsyncSession, document_id: str | None, run_type: str) -> GsbRunHistory:
    run = GsbRunHistory(document_id=document_id, run_type=run_type)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def finish_run(db: AsyncSession, run_id: str, status: str, detail: str | None = None) -> None:
    run = (await db.execute(select(GsbRunHistory).where(GsbRunHistory.id == run_id))).scalar_one_or_none()
    if run:
        run.status = status
        run.detail = detail
        # utc_now() from .models (datetime.now(UTC)) — plan literal said datetime.utcnow(),
        # but the gsb_ models use DateTime(timezone=True) + datetime.now(UTC); stay consistent.
        run.finished_at = utc_now()
        await db.commit()


async def has_running_run(db: AsyncSession, document_id: str, run_type: str) -> bool:
    # limit(1) + scalar_one_or_none: existence check must not blow up on MultipleResultsFound
    # when stale "running" rows accumulate across gateway restarts mid-run.
    stmt = select(GsbRunHistory).where(GsbRunHistory.document_id == document_id, GsbRunHistory.run_type == run_type, GsbRunHistory.status == "running").limit(1)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def sweep_stale_runs(db: AsyncSession, max_age_minutes: int = 60) -> int:
    """网关重启会把 running 行永久留在库（finish_run 未达）——超龄 running 行改判 failed。
    返回改判数。在每次 has_running_run 检查前调用，防陈旧行永久锁死文档。
    （与 contract_price.crud.cleanup_stale_runs 同款自愈；T6 质量审查 carry-over。）"""
    cutoff = utc_now() - timedelta(minutes=max_age_minutes)
    stmt = select(GsbRunHistory).where(GsbRunHistory.status == "running", GsbRunHistory.created_at < cutoff)
    stale = list((await db.execute(stmt)).scalars())
    for run in stale:
        run.status = "failed"
        run.detail = "stale (gateway restart?)"
        run.finished_at = utc_now()
    if stale:
        await db.commit()
    return len(stale)


async def create_document(db: AsyncSession, report_id: str, file_name: str, file_hash: str, file_type: str, stage: str, mineral: str, year: int | None, region: str | None, raw_uri: str) -> GsbDocument:
    """Insert a gsb_documents row (status=uploaded) and commit.

    Commit is required before the background parse task starts: run_parse re-fetches
    the doc by id, and the /upload response needs id/created_at populated (server defaults).
    (Replaces the plan-literal inline ``_create_document`` whose sync ``db.commit()``/
    ``db.refresh()`` on an AsyncSession would never persist — coroutines must be awaited.)
    """
    doc = GsbDocument(report_id=report_id, file_name=file_name, file_hash=file_hash, file_type=file_type, stage=stage, mineral=mineral, year=year, region=region, status="uploaded", raw_uri=raw_uri)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def list_recent_runs(db: AsyncSession, limit: int = 50) -> list[GsbRunHistory]:
    stmt = select(GsbRunHistory).order_by(GsbRunHistory.created_at.desc(), GsbRunHistory.id.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())
