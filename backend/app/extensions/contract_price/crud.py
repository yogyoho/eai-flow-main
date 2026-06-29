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
    for key in ("unit_price", "tech_params", "goods_name", "spec_model"):
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
