# EAI-CUSTOM: forked from app.extensions.contract_price.crud (geo-sample-bank Phase 1).
"""Async CRUD helpers for the gsb_ tables (dedup, listing filters, run history)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
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


async def get_document_fresh(db: AsyncSession, document_id: str) -> GsbDocument | None:
    """绕过 identity map 重取（populate_existing）——重活后校验漂移必须看到 DB 真值。

    expire_on_commit=False（database.py 会话工厂配置）下，普通 get 命中 identity map
    时 ORM 不会用行数据覆盖已加载属性——他方会话已提交的改判对本会话不可见（P2-T2
    quality review 实测复现）。任何「重活后校验最新状态」的读取必须走本函数。
    """
    stmt = select(GsbDocument).where(GsbDocument.id == document_id).execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one_or_none()


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


async def count_documents(db: AsyncSession, stage: str | None = None, mineral: str | None = None, status: str | None = None) -> int:
    """list_documents 同三过滤的行计数——列表端点响应 total，前端分页控件消费（batch-cli T4）。"""
    stmt = select(func.count(GsbDocument.id))
    if stage:
        stmt = stmt.where(GsbDocument.stage == stage)
    if mineral:
        stmt = stmt.where(GsbDocument.mineral == mineral)
    if status:
        stmt = stmt.where(GsbDocument.status == status)
    return (await db.execute(stmt)).scalar_one()


async def list_reviewed(db: AsyncSession, stage: str | None = None, mineral: str | None = None) -> list[GsbDocument]:
    """reviewed 清单——模块级编译（run_compile）的输入集。

    created_at asc 保证 bank_compile 的 manifest 顺序与编译分组稳定（重编译幂等的排序基础）；
    stage/mineral 均可空（空=全库 reviewed）。
    """
    stmt = select(GsbDocument).where(GsbDocument.status == "reviewed")
    if stage:
        stmt = stmt.where(GsbDocument.stage == stage)
    if mineral:
        stmt = stmt.where(GsbDocument.mineral == mineral)
    stmt = stmt.order_by(GsbDocument.created_at.asc(), GsbDocument.id.asc())
    return list((await db.execute(stmt)).scalars().all())


async def has_running_compile_run(db: AsyncSession) -> bool:
    """模块级编译互斥：任意 run_type=compile 且 status=running 的行存在即拒绝新编译。

    limit(1) + scalar_one_or_none 同 has_running_run——陈旧 running 行堆积时不炸 MultipleResultsFound
    （超龄自愈走 sweep_stale_runs，router 在调用本函数前先 sweep）。
    """
    stmt = select(GsbRunHistory).where(GsbRunHistory.run_type == "compile", GsbRunHistory.status == "running").limit(1)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


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


async def next_report_id(db: AsyncSession, prefix: str) -> str:
    """同前缀最大序号 +1（4 位零填充）。prefix 形如 gsb-kc-cu / gsb-auto（batch-cli T2 suggest-id）。

    非数字尾段（理论上不应出现）跳过不计入 max，避免一条脏行把整组序号打到 NaN/异常。
    注意：与 upload 的 get_document_by_report_id 409 闸门之间无事务锁——并发上传同组时
    仍可能撞 unique 约束（Phase 1 同款接受窗口）。
    """
    # prefix 仅含连字符（内部常量表）——LIKE 通配符隐患的 `_` 不会出现在 prefix 里，无需转义。
    stmt = select(GsbDocument.report_id).where(GsbDocument.report_id.like(prefix + "-%"))
    rows = (await db.execute(stmt)).scalars().all()
    max_seq = 0
    for rid in rows:
        tail = rid[len(prefix) + 1 :]
        if tail.isdecimal():  # isdecimal 严格十进制（isdigit 会放过上标数字等 Unicode 陷阱）
            max_seq = max(max_seq, int(tail))
    return f"{prefix}-{max_seq + 1:04d}"


async def delete_document(db: AsyncSession, document_id: str) -> None:
    """删文档行（batch-cli T3）。行不存在静默返回（同 finish_run 风格）。

    审计语义：gsb_redactions / gsb_run_history 故意不建 FK——文档删除后流水保留
    （document_id 悬空），跑批审计链不随行消失。
    """
    doc = await get_document(db, document_id)
    if doc:
        await db.delete(doc)
        await db.commit()
