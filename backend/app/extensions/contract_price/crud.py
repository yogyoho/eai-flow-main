"""CRUD operations over the cpa_ tables for the management API.

Each function takes an ``AsyncSession`` (provided by the shared ``get_db``
dependency) and returns ORM objects or primitives. Query construction is
separated from the routers so it can be unit-tested with a mocked session.
"""

import json
import os
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.contract_price.models import (
    CpaCluster,
    CpaDocument,
    CpaItem,
    CpaRunHistory,
)
from app.extensions.contract_price.schemas import ConfigOut

_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "config.json"
)


# --- Documents (functional area 1) -----------------------------------------


async def list_documents(
    session: AsyncSession,
    keyword: Optional[str] = None,
    parse_status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[CpaDocument], int]:
    stmt = select(CpaDocument)
    if keyword:
        stmt = stmt.where(
            (CpaDocument.contract_no.ilike(f"%{keyword}%"))
            | (CpaDocument.supplier.ilike(f"%{keyword}%"))
        )
    if parse_status:
        stmt = stmt.where(CpaDocument.parse_status == parse_status)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CpaDocument.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all()), int(total)


async def delete_document(session: AsyncSession, doc_id: UUID) -> bool:
    await session.execute(delete(CpaItem).where(CpaItem.document_id == doc_id))
    result = await session.execute(delete(CpaDocument).where(CpaDocument.id == doc_id))
    await session.commit()
    return (result.rowcount or 0) > 0


async def update_document(
    session: AsyncSession, doc_id: UUID, fields: dict[str, Any]
) -> Optional[CpaDocument]:
    """Patch editable document fields (manual补 for project name/location + metadata)."""
    doc = await session.get(CpaDocument, doc_id)
    if doc is None:
        return None
    for key in ("project_name", "project_location", "contract_no", "supplier", "sign_date"):
        if fields.get(key) is not None:
            setattr(doc, key, fields[key])
    await session.commit()
    return doc


async def confirm_document(
    session: AsyncSession, doc_id: UUID, confirm_status: str
) -> Optional[CpaDocument]:
    """Set a document's confirm_status (confirmed/skipped) — the cluster gate."""
    if confirm_status not in ("confirmed", "skipped"):
        return None
    doc = await session.get(CpaDocument, doc_id)
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
    result = await session.execute(
        update(CpaDocument)
        .where(CpaDocument.confirm_status == "pending")
        .values(confirm_status=confirm_status)
    )
    await session.commit()
    return result.rowcount or 0


# --- Clusters (functional area 2) ------------------------------------------


async def list_clusters(
    session: AsyncSession,
    status: Optional[str] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[CpaCluster], int]:
    stmt = select(CpaCluster)
    if status:
        stmt = stmt.where(CpaCluster.status == status)
    if category:
        stmt = stmt.where(CpaCluster.category == category)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CpaCluster.item_count.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all()), int(total)


async def get_cluster_with_items(session: AsyncSession, cluster_id: UUID) -> Optional[CpaCluster]:
    cluster = await session.get(CpaCluster, cluster_id)
    if cluster is None:
        return None
    items = await session.execute(
        select(CpaItem).where(CpaItem.cluster_id == cluster_id).order_by(CpaItem.unit_price)
    )
    cluster.items = list(items.scalars().all())  # type: ignore[attr-defined]
    return cluster


async def confirm_cluster(
    session: AsyncSession,
    cluster_id: UUID,
    confirmed_by: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> Optional[CpaCluster]:
    cluster = await session.get(CpaCluster, cluster_id)
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
    expected_version: Optional[int] = None,
) -> Optional[CpaCluster]:
    """Mark a cluster rejected (manual curation — drop it from confirmed stats)."""
    cluster = await session.get(CpaCluster, cluster_id)
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
) -> Optional[CpaCluster]:
    """Patch a cluster's display fields (category / representative_name)."""
    cluster = await session.get(CpaCluster, cluster_id)
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
) -> Optional[CpaCluster]:
    if len(cluster_ids) < 2:
        raise ValueError("merge requires at least 2 clusters")
    new_cluster = CpaCluster(
        category=category, representative_name=representative_name, status="pending", item_count=0
    )
    session.add(new_cluster)
    await session.flush()
    await session.execute(
        update(CpaItem)
        .where(CpaItem.cluster_id.in_(cluster_ids))
        .values(cluster_id=new_cluster.id)
    )
    new_cluster.item_count = await session.scalar(
        select(func.count()).select_from(
            select(CpaItem).where(CpaItem.cluster_id == new_cluster.id).subquery()
        )
    ) or 0
    await session.execute(delete(CpaCluster).where(CpaCluster.id.in_(cluster_ids)))
    await session.commit()
    return new_cluster


async def move_item(session: AsyncSession, item_id: UUID, target_cluster_id: UUID) -> Optional[CpaItem]:
    item = await session.get(CpaItem, item_id)
    if item is None:
        return None
    item.cluster_id = target_cluster_id
    await session.commit()
    return item


# --- Items (functional area 3) ---------------------------------------------


async def list_items(
    session: AsyncSession,
    goods_name: Optional[str] = None,
    source_contract_no: Optional[str] = None,
    cluster_id: Optional[UUID] = None,
    run_id: Optional[UUID] = None,
    only_outliers: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[CpaItem], int]:
    stmt = select(CpaItem)
    if goods_name:
        stmt = stmt.where(CpaItem.goods_name.ilike(f"%{goods_name}%"))
    if source_contract_no:
        stmt = stmt.where(CpaItem.source_contract_no == source_contract_no)
    if cluster_id:
        stmt = stmt.where(CpaItem.cluster_id == cluster_id)
    if run_id:
        stmt = stmt.where(CpaItem.run_id == run_id)
    if only_outliers:
        stmt = stmt.where(CpaItem.is_outlier.is_(True))
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CpaItem.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all()), int(total)


async def update_item(
    session: AsyncSession, item_id: UUID, fields: dict[str, Any]
) -> Optional[CpaItem]:
    item = await session.get(CpaItem, item_id)
    if item is None:
        return None
    for key in ("unit_price", "tech_params", "goods_name", "spec_model", "validation_status"):
        if fields.get(key) is not None:
            setattr(item, key, fields[key])
    if fields.get("note"):
        item.edit_note = fields["note"]
    if fields.get("run_id") is not None:
        item.run_id = fields["run_id"]
    await session.commit()
    return item


async def delete_item(session: AsyncSession, item_id: UUID) -> bool:
    result = await session.execute(delete(CpaItem).where(CpaItem.id == item_id))
    await session.commit()
    return (result.rowcount or 0) > 0


async def list_item_contracts(session: AsyncSession) -> list[dict]:
    """Distinct source_contract_no with item counts (for the items-page filter).

    Only non-null contracts. Ordered by count desc so the most-represented
    contracts appear first in the dropdown.
    """
    rows = await session.execute(
        select(CpaItem.source_contract_no, func.count())
        .where(CpaItem.source_contract_no.is_not(None))
        .group_by(CpaItem.source_contract_no)
        .order_by(func.count().desc())
    )
    return [{"source_contract_no": no, "count": int(cnt)} for no, cnt in rows.all()]


async def delete_items_batch(session: AsyncSession, item_ids: list[UUID]) -> int:
    result = await session.execute(delete(CpaItem).where(CpaItem.id.in_(item_ids)))
    await session.commit()
    return result.rowcount or 0


async def delete_items_by_run(session: AsyncSession, run_id: UUID) -> int:
    result = await session.execute(delete(CpaItem).where(CpaItem.run_id == run_id))
    await session.commit()
    return result.rowcount or 0


# --- Runs (functional area 4) ----------------------------------------------


async def list_runs(
    session: AsyncSession,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[CpaRunHistory], int]:
    stmt = select(CpaRunHistory)
    if status:
        stmt = stmt.where(CpaRunHistory.status == status)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CpaRunHistory.started_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all()), int(total)


async def get_run(session: AsyncSession, run_id: UUID) -> Optional[CpaRunHistory]:
    return await session.get(CpaRunHistory, run_id)


async def has_running_run(session: AsyncSession, phase: str) -> bool:
    """True if a run for the given phase (parse/cluster) is already in progress.

    Guards against concurrent OCR runs colliding on the same MinIO objects.
    NOTE: a gateway restart mid-run orphans the row at status='running' and
    would block re-trigger; clear manually (`UPDATE cpa_run_history SET
    status='failed' WHERE status='running'`) if that happens.
    """
    row = await session.scalar(
        select(func.count()).select_from(
            select(CpaRunHistory)
            .where(CpaRunHistory.status == "running")
            .where(CpaRunHistory.scope["phase"].astext == phase)
            .subquery()
        )
    )
    return bool(row)


async def cleanup_stale_runs(session: AsyncSession, max_age_seconds: int = 3600) -> int:
    """Mark orphaned 'running' runs (older than max_age_seconds) as 'failed'.

    A gateway restart mid-run leaves the row at status='running' forever,
    which blocks re-trigger via has_running_run. This self-heal is called at
    the top of each trigger endpoint so orphans are cleared automatically.
    Returns the number of runs marked failed.
    """
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    result = await session.execute(
        update(CpaRunHistory)
        .where(CpaRunHistory.status == "running")
        .where(CpaRunHistory.started_at < cutoff)
        .values(status="failed", error="orphaned by restart (auto-cleaned)", finished_at=func.now())
    )
    await session.commit()
    return result.rowcount or 0


async def create_run(session: AsyncSession, **fields) -> CpaRunHistory:
    run = CpaRunHistory(**fields)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def finish_run(
    session: AsyncSession, run_id: UUID, **fields
) -> Optional[CpaRunHistory]:
    run = await session.get(CpaRunHistory, run_id)
    if run is None:
        return None
    for key, value in fields.items():
        if hasattr(run, key):
            setattr(run, key, value)
    await session.commit()
    return run


# --- Dashboard (functional area 6) -----------------------------------------


async def dashboard_counts(session: AsyncSession) -> dict:
    contract_count = await session.scalar(select(func.count()).select_from(CpaDocument)) or 0
    item_count = await session.scalar(select(func.count()).select_from(CpaItem)) or 0
    cluster_count = await session.scalar(select(func.count()).select_from(CpaCluster)) or 0
    pending = await session.scalar(
        select(func.count()).select_from(
            select(CpaCluster).where(CpaCluster.status == "pending").subquery()
        )
    ) or 0
    confirmed = await session.scalar(
        select(func.count()).select_from(
            select(CpaCluster).where(CpaCluster.status == "confirmed").subquery()
        )
    ) or 0
    return {
        "contract_count": int(contract_count),
        "item_count": int(item_count),
        "cluster_count": int(cluster_count),
        "pending_cluster_count": int(pending),
        "confirmed_cluster_count": int(confirmed),
    }


async def price_range(session: AsyncSession) -> Optional[dict]:
    row = await session.execute(
        select(
            func.min(CpaItem.unit_price),
            func.max(CpaItem.unit_price),
            func.avg(CpaItem.unit_price),
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
            CpaCluster.representative_name,
            func.count(CpaItem.id).label("item_count"),
            func.round(func.avg(CpaItem.unit_price), 2).label("avg_price"),
        )
        .join(CpaItem, CpaItem.cluster_id == CpaCluster.id)
        .where(CpaItem.unit_price.isnot(None))
        .group_by(CpaCluster.id, CpaCluster.representative_name)
        .order_by(func.count(CpaItem.id).desc())
        .limit(10)
    )
    top_goods = [
        {"name": n, "item_count": int(c), "avg_price": float(a) if a is not None else 0.0}
        for n, c, a in rows.all()
    ]

    # 2. unit_price histogram by magnitude bucket
    rows = await session.execute(
        text(
            "SELECT CASE WHEN unit_price < 10 THEN '0-10' "
            "WHEN unit_price < 50 THEN '10-50' "
            "WHEN unit_price < 200 THEN '50-200' "
            "WHEN unit_price < 1000 THEN '200-1000' "
            "ELSE '1000+' END AS rng, count(*) AS cnt "
            "FROM cpa_items WHERE unit_price IS NOT NULL GROUP BY rng"
        )
    )
    price_ranges = [{"range": r, "count": int(c)} for r, c in rows.all()]

    # 3. validation-status distribution (ok / needs_review / corrected)
    rows = await session.execute(
        select(CpaItem.validation_status, func.count()).group_by(CpaItem.validation_status)
    )
    validation = [{"status": s, "count": int(c)} for s, c in rows.all()]

    # 4. cluster-size distribution
    rows = await session.execute(
        text(
            "SELECT CASE WHEN item_count = 1 THEN '1' "
            "WHEN item_count <= 5 THEN '2-5' "
            "WHEN item_count <= 10 THEN '6-10' "
            "ELSE '10+' END AS sz, count(*) AS cnt "
            "FROM cpa_clusters GROUP BY sz"
        )
    )
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
    name: Optional[str] = None,
    cluster_id: Optional[UUID] = None,
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

    base = (
        select(CpaItem, CpaDocument)
        .join(CpaDocument, CpaItem.document_id == CpaDocument.id)
    )
    if name:
        base = base.where(CpaItem.goods_name.ilike(f"%{name}%"))
    elif cluster_id:
        base = base.where(CpaItem.cluster_id == cluster_id)
    else:
        return {"error": "provide name or cluster_id"}

    result = await session.execute(base.order_by(CpaItem.created_at))
    rows = result.all()

    if not rows:
        return {"goods_name": name or "", "total": 0}

    items = [r[0] for r in rows]  # CpaItem objects
    docs = [r[1] for r in rows]  # CpaDocument objects

    # price stats: only ok/corrected
    priced = [
        float(it.unit_price)
        for it in items
        if it.unit_price is not None and it.validation_status in ("ok", "corrected")
    ]
    ok_count = sum(1 for it in items if it.validation_status == "ok")
    nr_count = sum(1 for it in items if it.validation_status == "needs_review")

    boxplot: Optional[dict] = None
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
            if it.unit_price is not None
            and it.validation_status in ("ok", "corrected")
            and (float(it.unit_price) < lo_fence or float(it.unit_price) > hi_fence)
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

    # date breakdown (monthly avg)
    by_date_map: dict[str, list[float]] = {}
    for it, doc in zip(items, docs):
        if doc.sign_date and it.unit_price and it.validation_status in ("ok", "corrected"):
            month_key = doc.sign_date.strftime("%Y-%m")
            by_date_map.setdefault(month_key, []).append(float(it.unit_price))
    by_date = sorted(
        [
            {"month": m, "count": len(vals), "avg_price": round(_stats.mean(vals), 2)}
            for m, vals in by_date_map.items()
        ],
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
            "goods_name": it.goods_name,
            "contract_no": it.source_contract_no or "—",
            "supplier": next((d.supplier for d in docs if d.id == it.document_id), None) or "—",
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

    return {
        "goods_name": name or (items[0].goods_name if items else ""),
        "total": total,
        "ok_count": ok_count,
        "needs_review_count": nr_count,
        "boxplot": boxplot,
        "by_supplier": by_supplier,
        "by_date": by_date,
        "price_ranges": ranges,
        "items": detail,
    }


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
