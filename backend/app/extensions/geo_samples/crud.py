# EAI-CUSTOM: forked from app.extensions.contract_price.crud (geo-sample-bank Phase 1).
"""Async CRUD helpers for the gsb_ tables (dedup, listing filters, run history)."""

from __future__ import annotations

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
