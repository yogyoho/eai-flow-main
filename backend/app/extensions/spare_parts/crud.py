# EAI-CUSTOM: forked from contract_price/crud.py; 差异=客户维度(csp_customers + customer_id)
# + 备件域(part_name/spec);csp_run_history 无 excel_path、有 customers_resolved。
"""CRUD operations over the csp_ tables for the management API.

Each function takes an ``AsyncSession`` (provided by the shared ``get_db``
dependency) and returns ORM objects or primitives. Query construction is
separated from the routers so it can be unit-tested with a mocked session.
"""

import json
import os
from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy import delete, exists, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.spare_parts.models import (
    CspCluster,
    CspCustomer,
    CspDocument,
    CspItem,
    CspRunHistory,
)
from app.extensions.spare_parts.schemas import ConfigOut

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


# --- Documents (functional area 1) -----------------------------------------


async def list_documents(
    session: AsyncSession,
    keyword: str | None = None,
    parse_status: str | None = None,
    customer_id: UUID | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[CspDocument], int]:
    stmt = select(CspDocument)
    if keyword:
        # EAI-CUSTOM: keyword 也匹配 customer_name(④ 客户维度),便于按客户筛选文档。
        stmt = stmt.where((CspDocument.contract_no.ilike(f"%{keyword}%")) | (CspDocument.supplier.ilike(f"%{keyword}%")) | (CspDocument.customer_name.ilike(f"%{keyword}%")))
    if parse_status:
        stmt = stmt.where(CspDocument.parse_status == parse_status)
    if customer_id:
        stmt = stmt.where(CspDocument.customer_id == customer_id)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CspDocument.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all()), int(total)


async def delete_document(session: AsyncSession, doc_id: UUID) -> bool:
    # If this doc's items are part of the current cluster snapshot, that snapshot
    # is now stale (it still counts the items we're about to delete) → clear it.
    # Clusters are a full-rebuild snapshot (re-run「开始分组」to regenerate), so
    # wiping avoids 分组审核 showing groups that no longer match the data.
    in_snapshot = await session.scalar(select(func.count()).select_from(select(CspItem).where(CspItem.document_id == doc_id, CspItem.cluster_id.is_not(None)).subquery()))
    await session.execute(delete(CspItem).where(CspItem.document_id == doc_id))
    if in_snapshot:
        # null remaining items' cluster_id/is_outlier, drop all clusters, and
        # revert 'clustered' docs to 'confirmed' (their groups are gone).
        await session.execute(update(CspItem).values(cluster_id=None, is_outlier=False))
        await session.execute(delete(CspCluster))
        await session.execute(update(CspDocument).where(CspDocument.confirm_status == "clustered").values(confirm_status="confirmed"))
    result = await session.execute(delete(CspDocument).where(CspDocument.id == doc_id))
    await session.commit()
    return (result.rowcount or 0) > 0


async def find_duplicate_document(session: AsyncSession, file_hash: str, exclude_uri: str) -> CspDocument | None:
    """A document with the SAME content hash under a DIFFERENT storage_uri — i.e.
    the same contract already uploaded under another filename. Used to reject
    cross-filename duplicate uploads (dedup by content, not filename). Returns
    None when the content is new or only exists under ``exclude_uri`` (re-upload
    of the same filename, which is allowed and overwrites in place)."""
    result = await session.execute(select(CspDocument).where(CspDocument.file_hash == file_hash).where(CspDocument.storage_uri != exclude_uri).limit(1))
    return result.scalar_one_or_none()


async def create_pending_document(
    session: AsyncSession,
    *,
    storage_uri: str,
    file_name: str,
    file_hash: str,
    file_type: str,
    size: int,
) -> None:
    """Create a 'pending' document row at upload time so the doc shows in the
    list (status 解析中) BEFORE the parse run finishes. Upsert by storage_uri:
    re-uploading the same filename resets the existing row to pending (re-parse).
    The parse run's _persist_parse later fills parse_status + items by upserting
    on the same storage_uri."""
    existing = (await session.execute(select(CspDocument).where(CspDocument.storage_uri == storage_uri))).scalar_one_or_none()
    if existing is None:
        session.add(
            CspDocument(
                storage_uri=storage_uri,
                file_name=file_name,
                file_hash=file_hash,
                file_type=file_type,
                quick_fp=f"{file_name}|{size}",
                parse_mode="ocr",
                parse_status="pending",
                confirm_status="pending",
            )
        )
    else:
        existing.file_hash = file_hash
        existing.file_type = file_type
        existing.quick_fp = f"{file_name}|{size}"
        existing.parse_status = "pending"
        existing.confirm_status = "pending"
        existing.parse_meta = None
        existing.error = None
    await session.commit()


async def mark_documents_parsing(session: AsyncSession, *, storage_uri: str | None = None) -> int:
    """将待解析文档由「已上传」(pending) 置为「解析中」(parsing)。

    在点击「开始解析」时立即调用 —— 让前端在按钮点下的瞬间就显示 解析中,
    而非等到 OCR 子进程真正启动(可能滞后数秒)。pipeline 子进程随后会按
    storage_uri 覆写为 parsed/failed/needs_review(见 cli._persist_parse)。

    - 不传 storage_uri:批量置全部 pending 文档(「开始解析」按钮)。
    - 传 storage_uri:仅置该单文档(单文档触发场景)。
    返回受影响行数。
    """
    stmt = update(CspDocument).where(CspDocument.parse_status == "pending")
    if storage_uri:
        stmt = stmt.where(CspDocument.storage_uri == storage_uri)
    result = await session.execute(stmt.values(parse_status="parsing"))
    await session.commit()
    return result.rowcount or 0


async def set_document_parse_status(session: AsyncSession, doc_id: UUID, parse_status: str) -> CspDocument | None:
    """强制将单个文档置为指定解析状态(忽略当前状态)。

    用于「重新解析」:被重解析的文档当前可能是 parsed/needs_review/failed
    (不一定是 pending),``mark_documents_parsing`` 的 pending 过滤会漏掉它们,
    故这里按 id 直接覆写为 parsing。子进程用 force_key 重跑后同样覆写终态。
    """
    doc = await session.get(CspDocument, doc_id)
    if doc is None:
        return None
    doc.parse_status = parse_status
    await session.commit()
    return doc


async def mark_stale_parsing_failed(session: AsyncSession, error: str) -> int:
    """解析子进程整体失败后兜底:把仍卡在「解析中」的文档置为「解析失败」。

    正常完成的文档已被子进程逐个覆写为 parsed/failed/needs_review;只有子进程
    崩溃/非零退出时,从未到达终态的 parsing 文档会永远停在 解析中。这里置为
    failed,避免状态卡死(用户要求:失败就是解析失败)。
    """
    result = await session.execute(update(CspDocument).where(CspDocument.parse_status == "parsing").values(parse_status="failed", error=error))
    await session.commit()
    return result.rowcount or 0


async def update_document(session: AsyncSession, doc_id: UUID, fields: dict[str, Any]) -> CspDocument | None:
    """Patch editable document fields (manual补 for project name/location + metadata)."""
    doc = await session.get(CspDocument, doc_id)
    if doc is None:
        return None
    # EAI-CUSTOM: 加 customer_id/customer_name —— 手工修正 OCR 解析错的需方(D3)。
    for key in (
        "project_name",
        "project_location",
        "contract_no",
        "supplier",
        "customer_id",
        "customer_name",
        "sign_date",
    ):
        if fields.get(key) is not None:
            setattr(doc, key, fields[key])
    await session.commit()
    return doc


async def confirm_document(session: AsyncSession, doc_id: UUID, confirm_status: str) -> CspDocument | None:
    """Set a document's confirm_status (confirmed/skipped) — the cluster gate."""
    if confirm_status not in ("confirmed", "skipped"):
        return None
    doc = await session.get(CspDocument, doc_id)
    if doc is None:
        return None
    doc.confirm_status = confirm_status
    await session.commit()
    return doc


async def confirm_all_documents(session: AsyncSession, confirm_status: str) -> int:
    """Batch confirm-gate: set every parsed (non-clustered) document to the given
    confirm_status. Returns the number of documents updated."""
    if confirm_status not in ("confirmed", "skipped"):
        return 0
    result = await session.execute(update(CspDocument).where(CspDocument.confirm_status == "pending").values(confirm_status=confirm_status))
    await session.commit()
    return result.rowcount or 0


# --- Clusters (functional area 2) ------------------------------------------


async def list_clusters(
    session: AsyncSession,
    status: str | None = None,
    category: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[CspCluster], int]:
    stmt = select(CspCluster)
    if status:
        stmt = stmt.where(CspCluster.status == status)
    if category:
        stmt = stmt.where(CspCluster.category == category)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CspCluster.item_count.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all()), int(total)


async def get_cluster_with_items(session: AsyncSession, cluster_id: UUID) -> CspCluster | None:
    cluster = await session.get(CspCluster, cluster_id)
    if cluster is None:
        return None
    items = await session.execute(select(CspItem).where(CspItem.cluster_id == cluster_id).order_by(CspItem.unit_price))
    cluster.items = list(items.scalars().all())  # type: ignore[attr-defined]
    return cluster


async def confirm_cluster(
    session: AsyncSession,
    cluster_id: UUID,
    confirmed_by: str | None = None,
    expected_version: int | None = None,
) -> CspCluster | None:
    cluster = await session.get(CspCluster, cluster_id)
    if cluster is None:
        return None
    if expected_version is not None and cluster.version != expected_version:
        raise ValueError(f"version mismatch: expected {expected_version}, got {cluster.version}")
    cluster.status = "confirmed"
    cluster.confirmed_by = confirmed_by
    cluster.version += 1
    await session.commit()
    return cluster


async def reject_cluster(
    session: AsyncSession,
    cluster_id: UUID,
    expected_version: int | None = None,
) -> CspCluster | None:
    """Mark a cluster rejected (manual curation — drop it from confirmed stats)."""
    cluster = await session.get(CspCluster, cluster_id)
    if cluster is None:
        return None
    if expected_version is not None and cluster.version != expected_version:
        raise ValueError(f"version mismatch: expected {expected_version}, got {cluster.version}")
    cluster.status = "rejected"
    cluster.version += 1
    await session.commit()
    return cluster


async def update_cluster(
    session: AsyncSession,
    cluster_id: UUID,
    fields: dict[str, Any],
) -> CspCluster | None:
    """Patch a cluster's display fields (category / representative_name)."""
    cluster = await session.get(CspCluster, cluster_id)
    if cluster is None:
        return None
    for key in ("category", "representative_name"):
        if fields.get(key) is not None:
            setattr(cluster, key, fields[key])
    await session.commit()
    return cluster


async def merge_clusters(
    session: AsyncSession,
    cluster_ids: list[UUID],
    representative_name: str,
    category: str = "未分类",
) -> CspCluster | None:
    if len(cluster_ids) < 2:
        raise ValueError("merge requires at least 2 clusters")
    new_cluster = CspCluster(category=category, representative_name=representative_name, status="pending", item_count=0)
    session.add(new_cluster)
    await session.flush()
    await session.execute(update(CspItem).where(CspItem.cluster_id.in_(cluster_ids)).values(cluster_id=new_cluster.id))
    new_cluster.item_count = await session.scalar(select(func.count()).select_from(select(CspItem).where(CspItem.cluster_id == new_cluster.id).subquery())) or 0
    await session.execute(delete(CspCluster).where(CspCluster.id.in_(cluster_ids)))
    await session.commit()
    return new_cluster


async def move_item(session: AsyncSession, item_id: UUID, target_cluster_id: UUID) -> CspItem | None:
    item = await session.get(CspItem, item_id)
    if item is None:
        return None
    item.cluster_id = target_cluster_id
    await session.commit()
    return item


# --- Items (functional area 3) ---------------------------------------------


async def list_items(
    session: AsyncSession,
    part_name: str | None = None,
    source_contract_no: str | None = None,
    cluster_id: UUID | None = None,
    run_id: UUID | None = None,
    customer_id: UUID | None = None,
    only_outliers: bool = False,
    validation_status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[CspItem], int]:
    stmt = select(CspItem)
    if part_name:
        stmt = stmt.where(CspItem.part_name.ilike(f"%{part_name}%"))
    if customer_id:
        # EAI-CUSTOM: 按客户筛选明细(④ 客户维度)。
        stmt = stmt.where(CspItem.customer_id == customer_id)
    if source_contract_no:
        stmt = stmt.where(CspItem.source_contract_no == source_contract_no)
    if cluster_id:
        stmt = stmt.where(CspItem.cluster_id == cluster_id)
    if run_id:
        stmt = stmt.where(CspItem.run_id == run_id)
    if only_outliers:
        stmt = stmt.where(CspItem.is_outlier.is_(True))
    if validation_status:
        stmt = stmt.where(CspItem.validation_status == validation_status)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CspItem.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all()), int(total)


async def update_item(session: AsyncSession, item_id: UUID, fields: dict[str, Any]) -> CspItem | None:
    item = await session.get(CspItem, item_id)
    if item is None:
        return None
    for key in ("unit_price", "tech_params", "part_name", "spec", "validation_status"):
        if fields.get(key) is not None:
            setattr(item, key, fields[key])
    if fields.get("note"):
        item.edit_note = fields["note"]
    if fields.get("run_id") is not None:
        item.run_id = fields["run_id"]
    await session.commit()
    return item


async def delete_item(session: AsyncSession, item_id: UUID) -> bool:
    result = await session.execute(delete(CspItem).where(CspItem.id == item_id))
    await session.commit()
    return (result.rowcount or 0) > 0


async def list_item_contracts(session: AsyncSession) -> list[dict]:
    """Distinct source_contract_no with item counts (for the items-page filter).

    Only non-null contracts. Ordered by count desc so the most-represented
    contracts appear first in the dropdown.
    """
    rows = await session.execute(select(CspItem.source_contract_no, func.count()).where(CspItem.source_contract_no.is_not(None)).group_by(CspItem.source_contract_no).order_by(func.count().desc()))
    return [{"source_contract_no": no, "count": int(cnt)} for no, cnt in rows.all()]


async def list_item_customers(session: AsyncSession) -> list[dict]:
    """EAI-CUSTOM (D3): distinct customer_id/customer_name with item counts.

    Feeds the items-page 客户筛选下拉。Only non-null customers, ordered by count desc
    so the most-represented customers appear first.
    """
    rows = await session.execute(select(CspItem.customer_id, CspItem.customer_name, func.count()).where(CspItem.customer_id.is_not(None)).group_by(CspItem.customer_id, CspItem.customer_name).order_by(func.count().desc()))
    return [{"customer_id": str(cid), "customer_name": name, "count": int(cnt)} for cid, name, cnt in rows.all()]


async def delete_items_batch(session: AsyncSession, item_ids: list[UUID]) -> int:
    result = await session.execute(delete(CspItem).where(CspItem.id.in_(item_ids)))
    await session.commit()
    return result.rowcount or 0


async def batch_validate_items(session: AsyncSession, item_ids: list[UUID], validation_status: str = "ok") -> int:
    """Batch update validation_status (ok/corrected) for selected items."""
    result = await session.execute(update(CspItem).where(CspItem.id.in_(item_ids)).values(validation_status=validation_status))
    await session.commit()
    return result.rowcount or 0


async def delete_items_by_run(session: AsyncSession, run_id: UUID) -> int:
    result = await session.execute(delete(CspItem).where(CspItem.run_id == run_id))
    await session.commit()
    return result.rowcount or 0


# --- Runs (functional area 4) ----------------------------------------------


async def list_runs(
    session: AsyncSession,
    status: str | None = None,
    has_items: bool = False,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[CspRunHistory], int]:
    stmt = select(CspRunHistory)
    if status:
        stmt = stmt.where(CspRunHistory.status == status)
    # EAI-CUSTOM: has_items — 只列当前真有明细(csp_items)的任务,排除聚类/空任务,
    # 供分项校验页「来源任务」下拉使用;任务总览页(TasksView)不传此参,不受影响。
    if has_items:
        stmt = stmt.where(exists().where(CspItem.run_id == CspRunHistory.id))
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CspRunHistory.started_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all()), int(total)


async def get_run(session: AsyncSession, run_id: UUID) -> CspRunHistory | None:
    return await session.get(CspRunHistory, run_id)


async def delete_run(session: AsyncSession, run_id: UUID) -> bool:
    """Delete a run history record (does NOT cascade to items/docs)."""
    run = await session.get(CspRunHistory, run_id)
    if run is None:
        return False
    await session.delete(run)
    await session.commit()
    return True


async def has_running_run(session: AsyncSession, phase: str) -> bool:
    """True if a run for the given phase (parse/cluster) is already in progress.

    Guards against concurrent OCR runs colliding on the same MinIO objects.
    NOTE: a gateway restart mid-run orphans the row at status='running' and
    would block re-trigger; clear manually (`UPDATE csp_run_history SET
    status='failed' WHERE status='running'`) if that happens.
    """
    row = await session.scalar(select(func.count()).select_from(select(CspRunHistory).where(CspRunHistory.status == "running").where(CspRunHistory.scope["phase"].astext == phase).subquery()))
    return bool(row)


async def cleanup_stale_runs(session: AsyncSession, max_age_seconds: int = 21600) -> int:
    """Mark orphaned 'running' runs (older than max_age_seconds) as 'failed'.

    Default 6h: a 100-doc parse run can take 2-4h, so the old 1h threshold
    would mark still-running long batches as 'failed' if a new trigger arrived
    mid-run. 6h covers the worst case without leaving true orphans too long.

    A gateway restart mid-run leaves the row at status='running' forever,
    which blocks re-trigger via has_running_run. This self-heal is called at
    the top of each trigger endpoint so orphans are cleared automatically.
    Returns the number of runs marked failed.
    """
    from datetime import datetime, timedelta

    cutoff = datetime.now(UTC) - timedelta(seconds=max_age_seconds)
    result = await session.execute(update(CspRunHistory).where(CspRunHistory.status == "running").where(CspRunHistory.started_at < cutoff).values(status="failed", error="orphaned by restart (auto-cleaned)", finished_at=func.now()))
    await session.commit()
    return result.rowcount or 0


async def create_run(session: AsyncSession, **fields) -> CspRunHistory:
    run = CspRunHistory(**fields)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def finish_run(session: AsyncSession, run_id: UUID, **fields) -> CspRunHistory | None:
    run = await session.get(CspRunHistory, run_id)
    if run is None:
        return None
    for key, value in fields.items():
        if hasattr(run, key):
            setattr(run, key, value)
    await session.commit()
    return run


# --- Dashboard (functional area 6) -----------------------------------------


async def dashboard_counts(session: AsyncSession) -> dict:
    contract_count = await session.scalar(select(func.count()).select_from(CspDocument)) or 0
    item_count = await session.scalar(select(func.count()).select_from(CspItem)) or 0
    cluster_count = await session.scalar(select(func.count()).select_from(CspCluster)) or 0
    pending = await session.scalar(select(func.count()).select_from(select(CspCluster).where(CspCluster.status == "pending").subquery())) or 0
    confirmed = await session.scalar(select(func.count()).select_from(select(CspCluster).where(CspCluster.status == "confirmed").subquery())) or 0
    outlier_count = await session.scalar(select(func.count()).select_from(CspItem).where(CspItem.is_outlier.is_(True))) or 0
    # EAI-CUSTOM (D3): distinct 需方客户数(④ 核心维度)。
    customer_count = await session.scalar(select(func.count(func.distinct(CspDocument.customer_id))).where(CspDocument.customer_id.is_not(None))) or 0
    return {
        "contract_count": int(contract_count),
        "item_count": int(item_count),
        "customer_count": int(customer_count),
        "cluster_count": int(cluster_count),
        "pending_cluster_count": int(pending),
        "confirmed_cluster_count": int(confirmed),
        "outlier_count": int(outlier_count),
    }


async def price_range(session: AsyncSession) -> dict | None:
    row = await session.execute(
        select(
            func.min(CspItem.unit_price),
            func.max(CspItem.unit_price),
            func.avg(CspItem.unit_price),
        )
    )
    lo, hi, avg = row.one()
    if lo is None:
        return None
    return {"min": float(lo), "max": float(hi), "avg": round(float(avg), 2)}


async def dashboard_charts(session: AsyncSession) -> dict:
    """Four aggregations for the dashboard charts.

    Adapted to what the current data supports (1 contract, supplier/sign_date
    mostly null, category all '未分类'): top goods clusters by price, price-range
    histogram, validation-status split, cluster-size distribution. When
    supplier/sign_date/category are populated (more contracts + field
    extraction), swap in category/supplier/time charts.
    """
    # 1. top goods clusters (by item count) with avg priced unit_price
    rows = await session.execute(
        select(
            CspCluster.representative_name,
            func.count(CspItem.id).label("item_count"),
            func.round(func.avg(CspItem.unit_price), 2).label("avg_price"),
        )
        .join(CspItem, CspItem.cluster_id == CspCluster.id)
        .where(CspItem.unit_price.isnot(None))
        .group_by(CspCluster.id, CspCluster.representative_name)
        .order_by(func.count(CspItem.id).desc())
        .limit(10)
    )
    top_goods = [{"name": n, "item_count": int(c), "avg_price": float(a) if a is not None else 0.0} for n, c, a in rows.all()]

    # 2. unit_price histogram by magnitude bucket
    rows = await session.execute(
        text(
            "SELECT CASE WHEN unit_price < 10 THEN '0-10' "
            "WHEN unit_price < 50 THEN '10-50' "
            "WHEN unit_price < 200 THEN '50-200' "
            "WHEN unit_price < 1000 THEN '200-1000' "
            "ELSE '1000+' END AS rng, count(*) AS cnt "
            "FROM csp_items WHERE unit_price IS NOT NULL GROUP BY rng"
        )
    )
    price_ranges = [{"range": r, "count": int(c)} for r, c in rows.all()]

    # 3. validation-status distribution (ok / needs_review / corrected)
    rows = await session.execute(select(CspItem.validation_status, func.count()).group_by(CspItem.validation_status))
    validation = [{"status": s, "count": int(c)} for s, c in rows.all()]

    # 4. cluster-size distribution
    rows = await session.execute(text("SELECT CASE WHEN item_count = 1 THEN '1' WHEN item_count <= 5 THEN '2-5' WHEN item_count <= 10 THEN '6-10' ELSE '10+' END AS sz, count(*) AS cnt FROM csp_clusters GROUP BY sz"))
    cluster_sizes = [{"range": r, "count": int(c)} for r, c in rows.all()]

    return {
        "top_goods": top_goods,
        "price_ranges": price_ranges,
        "validation": validation,
        "cluster_sizes": cluster_sizes,
    }


# --- Cross-contract goods analysis (functional area 7) --------------------


async def goods_analysis(
    session: AsyncSession,
    name: str | None = None,
    cluster_id: UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> dict:
    """Cross-contract price analysis for a single goods (by name fuzzy match)
    or a cluster. Returns box-plot stats, supplier/date breakdowns, price
    histogram, and a paginated detail table — all in one payload for the
    dashboard analysis view.

    Price stats use ONLY ok/corrected items (needs_review excluded, same rule
    as cluster stats).
    """
    import statistics as _stats

    base = select(CspItem, CspDocument).join(CspDocument, CspItem.document_id == CspDocument.id)
    if name:
        base = base.where(CspItem.part_name.ilike(f"%{name}%"))
    elif cluster_id:
        base = base.where(CspItem.cluster_id == cluster_id)
    else:
        return {"error": "provide name or cluster_id"}

    result = await session.execute(base.order_by(CspItem.created_at))
    rows = result.all()

    if not rows:
        return {"part_name": name or "", "total": 0}

    items = [r[0] for r in rows]  # CspItem objects
    docs = [r[1] for r in rows]  # CspDocument objects

    # price stats: only ok/corrected
    priced = [float(it.unit_price) for it in items if it.unit_price is not None and it.validation_status in ("ok", "corrected")]
    ok_count = sum(1 for it in items if it.validation_status == "ok")
    nr_count = sum(1 for it in items if it.validation_status == "needs_review")

    boxplot: dict | None = None
    if priced:
        ps = sorted(priced)
        n = len(ps)
        q1 = ps[n // 4] if n >= 4 else ps[0]
        q3 = ps[(3 * n) // 4] if n >= 4 else ps[-1]
        iqr = q3 - q1
        lo_fence = q1 - 1.5 * iqr
        hi_fence = q3 + 1.5 * iqr
        outliers = [
            {"contract_no": it.source_contract_no or "—", "unit_price": float(it.unit_price)}
            for it in items
            if it.unit_price is not None and it.validation_status in ("ok", "corrected") and (float(it.unit_price) < lo_fence or float(it.unit_price) > hi_fence)
        ]
        boxplot = {
            "count": n,
            "min": round(ps[0], 2),
            "q1": round(q1, 2),
            "median": round(_stats.median(ps), 2),
            "q3": round(q3, 2),
            "max": round(ps[-1], 2),
            "mean": round(_stats.mean(ps), 2),
            "std": round(_stats.stdev(ps), 2) if n > 1 else 0,
            "iqr": round(iqr, 2),
            "outliers": outliers,
        }

    # supplier breakdown
    by_supplier_map: dict[str, list[float]] = {}
    for it, doc in zip(items, docs):
        sup = doc.supplier or "未知供应商"
        by_supplier_map.setdefault(sup, [])
        if it.unit_price is not None and it.validation_status in ("ok", "corrected"):
            by_supplier_map[sup].append(float(it.unit_price))
    by_supplier = sorted(
        [
            {
                "name": sup,
                "count": len(vals),
                "avg_price": round(_stats.mean(vals), 2) if vals else 0,
                "min": round(min(vals), 2) if vals else 0,
                "max": round(max(vals), 2) if vals else 0,
            }
            for sup, vals in by_supplier_map.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    # EAI-CUSTOM (D3): 客户维度价格拆分 —— ④ 跨客户比价的核心 breakdown。
    by_customer_map: dict[str, list[float]] = {}
    for it in items:
        cust = it.customer_name or "未知客户"
        by_customer_map.setdefault(cust, [])
        if it.unit_price is not None and it.validation_status in ("ok", "corrected"):
            by_customer_map[cust].append(float(it.unit_price))
    by_customer = sorted(
        [
            {
                "name": cust,
                "count": len(vals),
                "avg_price": round(_stats.mean(vals), 2) if vals else 0,
                "min": round(min(vals), 2) if vals else 0,
                "max": round(max(vals), 2) if vals else 0,
            }
            for cust, vals in by_customer_map.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    # date breakdown (monthly avg)
    by_date_map: dict[str, list[float]] = {}
    for it, doc in zip(items, docs):
        if doc.sign_date and it.unit_price and it.validation_status in ("ok", "corrected"):
            month_key = doc.sign_date.strftime("%Y-%m")
            by_date_map.setdefault(month_key, []).append(float(it.unit_price))
    by_date = sorted(
        [{"month": m, "count": len(vals), "avg_price": round(_stats.mean(vals), 2)} for m, vals in by_date_map.items()],
        key=lambda x: x["month"],
    )

    # price histogram buckets
    if priced:
        ps = priced
        buckets = [(0, 10), (10, 50), (50, 200), (200, 1000), (1000, float("inf"))]
        ranges = []
        for lo, hi in buckets:
            cnt = sum(1 for p in ps if lo <= p < hi)
            if cnt > 0 or lo < max(ps):
                lbl = f"{int(lo)}-{int(hi)}" if hi != float("inf") else f"{int(lo)}+"
                ranges.append({"range": lbl, "count": cnt})
    else:
        ranges = []

    # detail table (paginated)
    total = len(items)
    page_items = items[skip : skip + limit]
    detail = [
        {
            "id": str(it.id),
            "document_id": str(it.document_id),
            "part_name": it.part_name,
            "contract_no": it.source_contract_no or "—",
            "supplier": next((d.supplier for d in docs if d.id == it.document_id), None) or "—",
            "customer_name": it.customer_name or "—",  # EAI-CUSTOM (D3)
            "unit_price": float(it.unit_price) if it.unit_price is not None else None,
            "price_untaxed": float(it.price_untaxed) if it.price_untaxed is not None else None,
            "quantity": float(it.quantity) if it.quantity is not None else None,
            "unit": it.unit or "—",
            "validation_status": it.validation_status,
            "is_outlier": it.is_outlier,
            "source_page": it.source_page,
            "source_bbox": it.source_bbox,
        }
        for it in page_items
    ]

    # Display name: prefer the explicit name; for cluster queries, use the
    # cluster's representative_name (not items[0].part_name, which may differ
    # in mixed clusters — a known char-ngram limitation).
    display_name = name
    if not display_name and cluster_id:
        cluster_obj = await session.get(CspCluster, cluster_id)
        if cluster_obj:
            display_name = cluster_obj.representative_name
    if not display_name:
        display_name = items[0].part_name if items else ""

    return {
        "part_name": display_name,
        "total": total,
        "ok_count": ok_count,
        "needs_review_count": nr_count,
        "boxplot": boxplot,
        "by_supplier": by_supplier,
        "by_customer": by_customer,  # EAI-CUSTOM (D3)
        "by_date": by_date,
        "price_ranges": ranges,
        "items": detail,
    }


# --- Customers (functional area 8: D3 客户主数据) --------------------------
# EAI-CUSTOM: ④ 特色 —— 客户主数据(canonical_name + aliases)是跨客户比价的前提。
# OCR 脏客户名 → 别名/canonical 命中 → customer_id;未命中 → pending 占位(绝不丢弃)。


async def _fill_doc_count(session: AsyncSession, customer: CspCustomer) -> CspCustomer:
    """读时聚合 doc_count(关联文档数,非列);写回实例属性供 CustomerOut(from_attributes)序列化。"""
    customer.doc_count = await session.scalar(select(func.count()).select_from(select(CspDocument).where(CspDocument.customer_id == customer.id).subquery())) or 0
    return customer


async def list_customers(
    session: AsyncSession,
    keyword: str | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[CspCustomer], int]:
    """客户主数据列表 + doc_count(读时聚合)。keyword 命中 canonical_name(模糊)。"""
    stmt = select(CspCustomer)
    if keyword:
        stmt = stmt.where(CspCustomer.canonical_name.ilike(f"%{keyword}%"))
    if status:
        stmt = stmt.where(CspCustomer.status == status)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CspCustomer.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    customers = list(result.scalars().all())
    for c in customers:
        await _fill_doc_count(session, c)
    return customers, int(total)


async def get_customer(session: AsyncSession, customer_id: UUID) -> CspCustomer | None:
    c = await session.get(CspCustomer, customer_id)
    if c is not None:
        await _fill_doc_count(session, c)
    return c


async def create_customer(
    session: AsyncSession,
    *,
    canonical_name: str,
    aliases: list[str],
    source: str = "master",
) -> CspCustomer:
    c = CspCustomer(canonical_name=canonical_name, aliases=aliases, source=source, status="active")
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return c


async def update_customer(session: AsyncSession, customer_id: UUID, fields: dict[str, Any]) -> CspCustomer | None:
    """Patch canonical_name / aliases(手工维护客户主数据)。"""
    c = await session.get(CspCustomer, customer_id)
    if c is None:
        return None
    for key in ("canonical_name", "aliases"):
        if fields.get(key) is not None:
            setattr(c, key, fields[key])
    await session.commit()
    return c


async def claim_customer(session: AsyncSession, customer_id: UUID, raw_name: str) -> CspCustomer | None:
    """把一个 OCR 脏客户名认领到指定规范客户:并入 aliases(去重,不覆盖 canonical)。"""
    c = await session.get(CspCustomer, customer_id)
    if c is None:
        return None
    aliases = list(c.aliases or [])
    if raw_name and raw_name not in aliases and raw_name != c.canonical_name:
        aliases.append(raw_name)
        c.aliases = aliases
    await session.commit()
    return c


async def merge_customers(session: AsyncSession, source_ids: list[UUID], target_id: UUID) -> CspCustomer | None:
    """合并 N 个客户到 target:source 的 canonical/aliases 并入 target.aliases,
    所有 csp_documents/csp_items.customer_id 回填到 target,source 置 status=merged。"""
    if not source_ids or target_id in source_ids:
        raise ValueError("merge requires >=1 source distinct from target")
    target = await session.get(CspCustomer, target_id)
    if target is None:
        return None
    sources = (await session.execute(select(CspCustomer).where(CspCustomer.id.in_(source_ids)))).scalars().all()
    merged_aliases = list(target.aliases or [])
    for s in sources:
        if s.canonical_name and s.canonical_name not in merged_aliases and s.canonical_name != target.canonical_name:
            merged_aliases.append(s.canonical_name)
        for a in s.aliases or []:
            if a not in merged_aliases and a != target.canonical_name:
                merged_aliases.append(a)
    target.aliases = merged_aliases
    await session.execute(update(CspDocument).where(CspDocument.customer_id.in_(source_ids)).values(customer_id=target_id))
    await session.execute(update(CspItem).where(CspItem.customer_id.in_(source_ids)).values(customer_id=target_id))
    await session.execute(update(CspCustomer).where(CspCustomer.id.in_(source_ids)).values(status="merged", merged_into=target_id))
    await session.commit()
    await session.refresh(target)
    await _fill_doc_count(session, target)
    return target


async def resolve_customers(session: AsyncSession, raw_names: list[str]) -> list[dict]:
    """批量预览解析:每个脏客户名 → customer_id(canonical_name 或 aliases 命中,大小写不敏感)。
    未命中 → customer_id=None(调用方据此创建 pending 占位)。只读,不写库。

    匹配规则:normalize(raw) == normalize(canonical) 或 raw ∈ aliases(normalize = strip+lower)。
    """
    if not raw_names:
        return []
    all_customers = (await session.execute(select(CspCustomer).where(CspCustomer.status != "merged"))).scalars().all()
    index: dict[str, UUID] = {}
    for c in all_customers:
        index[(c.canonical_name or "").strip().lower()] = c.id
        for a in c.aliases or []:
            index[(a or "").strip().lower()] = c.id
    return [{"raw_name": raw, "customer_id": str(index[(raw or "").strip().lower()]) if (raw or "").strip().lower() in index else None} for raw in raw_names]


# --- Config (functional area 5) --------------------------------------------


def load_config() -> ConfigOut:
    path = _config_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return ConfigOut(**json.load(f))
    return ConfigOut()


def save_config(cfg: ConfigOut) -> ConfigOut:
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg.model_dump(), f, ensure_ascii=False, indent=2)
    return cfg


def _config_path() -> str:
    return os.path.abspath(_CONFIG_PATH)
