"""CRUD operations over the cpa_ tables for the management API.

Each function takes an ``AsyncSession`` (provided by the shared ``get_db``
dependency) and returns ORM objects or primitives. Query construction is
separated from the routers so it can be unit-tested with a mocked session.
"""

import asyncio
import copy
import json
import logging
import os
from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy import case, delete, exists, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.contract_price import storage
from app.extensions.contract_price.models import (
    CpaCluster,
    CpaDocument,
    CpaItem,
    CpaRunHistory,
)
from app.extensions.contract_price.schemas import LLM_KEY_MASK, ConfigOut

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


# --- Documents (functional area 1) -----------------------------------------


async def list_documents(
    session: AsyncSession,
    keyword: str | None = None,
    parse_status: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[CpaDocument], int]:
    stmt = select(CpaDocument)
    if keyword:
        stmt = stmt.where((CpaDocument.contract_no.ilike(f"%{keyword}%")) | (CpaDocument.supplier.ilike(f"%{keyword}%")))
    if parse_status:
        stmt = stmt.where(CpaDocument.parse_status == parse_status)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CpaDocument.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    docs = list(result.scalars().all())
    # v3 规则生态 KPI(设计 2026-09-19-cpa-table-recognition-three-layer §4):
    # 每文档分项总数/待核验数——只对本页文档做一条 GROUP BY 聚合(零 N+1),
    # 以非映射属性挂在 ORM 实例上,由 DocumentOut(from_attributes) 序列化。
    if docs:
        stats_rows = await session.execute(
            select(
                CpaItem.document_id,
                func.count(),
                func.sum(case((CpaItem.validation_status == "needs_review", 1), else_=0)),
            )
            .where(CpaItem.document_id.in_([d.id for d in docs]))
            .group_by(CpaItem.document_id)
        )
        stats = {row[0]: (int(row[1]), int(row[2] or 0)) for row in stats_rows.all()}
        for d in docs:
            d.items_total, d.items_needs_review = stats.get(d.id, (0, 0))
    return docs, int(total)


async def delete_document(session: AsyncSession, doc_id: UUID) -> bool:
    # If this doc's items are part of the current cluster snapshot, that snapshot
    # is now stale (it still counts the items we're about to delete) → clear it.
    # Clusters are a full-rebuild snapshot (re-run「开始分组」to regenerate), so
    # wiping avoids 分组审核 showing groups that no longer match the data.
    in_snapshot = await session.scalar(select(func.count()).select_from(select(CpaItem).where(CpaItem.document_id == doc_id, CpaItem.cluster_id.is_not(None)).subquery()))
    await session.execute(delete(CpaItem).where(CpaItem.document_id == doc_id))
    if in_snapshot:
        # null remaining items' cluster_id/is_outlier, drop all clusters, and
        # revert 'clustered' docs to 'confirmed' (their groups are gone).
        await session.execute(update(CpaItem).values(cluster_id=None, is_outlier=False))
        await session.execute(delete(CpaCluster))
        await session.execute(update(CpaDocument).where(CpaDocument.confirm_status == "clustered").values(confirm_status="confirmed"))
    result = await session.execute(delete(CpaDocument).where(CpaDocument.id == doc_id))
    await session.commit()
    return (result.rowcount or 0) > 0


async def find_duplicate_document(session: AsyncSession, file_hash: str, exclude_uri: str) -> CpaDocument | None:
    """A document with the SAME content hash under a DIFFERENT storage_uri — i.e.
    the same contract already uploaded under another filename. Used to reject
    cross-filename duplicate uploads (dedup by content, not filename). Returns
    None when the content is new or only exists under ``exclude_uri`` (re-upload
    of the same filename, which is allowed and overwrites in place)."""
    result = await session.execute(select(CpaDocument).where(CpaDocument.file_hash == file_hash).where(CpaDocument.storage_uri != exclude_uri).limit(1))
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
    existing = (await session.execute(select(CpaDocument).where(CpaDocument.storage_uri == storage_uri))).scalar_one_or_none()
    if existing is None:
        session.add(
            CpaDocument(
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
    stmt = update(CpaDocument).where(CpaDocument.parse_status == "pending")
    if storage_uri:
        stmt = stmt.where(CpaDocument.storage_uri == storage_uri)
    result = await session.execute(stmt.values(parse_status="parsing"))
    await session.commit()
    return result.rowcount or 0


async def set_document_parse_status(session: AsyncSession, doc_id: UUID, parse_status: str) -> CpaDocument | None:
    """强制将单个文档置为指定解析状态(忽略当前状态)。

    用于「重新解析」:被重解析的文档当前可能是 parsed/needs_review/failed
    (不一定是 pending),``mark_documents_parsing`` 的 pending 过滤会漏掉它们,
    故这里按 id 直接覆写为 parsing。子进程用 force_key 重跑后同样覆写终态。
    """
    doc = await session.get(CpaDocument, doc_id)
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
    result = await session.execute(update(CpaDocument).where(CpaDocument.parse_status == "parsing").values(parse_status="failed", error=error))
    await session.commit()
    return result.rowcount or 0


async def update_document(session: AsyncSession, doc_id: UUID, fields: dict[str, Any]) -> CpaDocument | None:
    """Patch editable document fields (manual补 for project name/location + metadata)."""
    doc = await session.get(CpaDocument, doc_id)
    if doc is None:
        return None
    for key in ("project_name", "project_location", "contract_no", "supplier", "sign_date"):
        if fields.get(key) is not None:
            setattr(doc, key, fields[key])
    await session.commit()
    return doc


async def confirm_document(session: AsyncSession, doc_id: UUID, confirm_status: str) -> CpaDocument | None:
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
    result = await session.execute(update(CpaDocument).where(CpaDocument.confirm_status == "pending").values(confirm_status=confirm_status))
    await session.commit()
    return result.rowcount or 0


# --- Clusters (functional area 2) ------------------------------------------


async def list_clusters(
    session: AsyncSession,
    status: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[CpaCluster], int]:
    stmt = select(CpaCluster)
    if status:
        stmt = stmt.where(CpaCluster.status == status)
    if category:
        stmt = stmt.where(CpaCluster.category == category)
    if keyword:
        # 手动合并辅助: 按代表名/类目模糊搜,跨页找出同类候选组。
        stmt = stmt.where(
            CpaCluster.representative_name.ilike(f"%{keyword}%")
            | CpaCluster.category.ilike(f"%{keyword}%")
        )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CpaCluster.item_count.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all()), int(total)


async def get_cluster_with_items(session: AsyncSession, cluster_id: UUID) -> CpaCluster | None:
    cluster = await session.get(CpaCluster, cluster_id)
    if cluster is None:
        return None
    items = await session.execute(select(CpaItem).where(CpaItem.cluster_id == cluster_id).order_by(CpaItem.unit_price))
    cluster.items = list(items.scalars().all())  # type: ignore[attr-defined]
    await _attach_cluster_stats(session, cluster.items)  # type: ignore[attr-defined]  # EAI-CUSTOM F3a: 簇明细行同样附带簇统计
    return cluster


async def confirm_cluster(
    session: AsyncSession,
    cluster_id: UUID,
    confirmed_by: str | None = None,
    expected_version: int | None = None,
) -> CpaCluster | None:
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
    expected_version: int | None = None,
) -> CpaCluster | None:
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
) -> CpaCluster | None:
    """Patch a cluster's display fields (category / representative_name)."""
    cluster = await session.get(CpaCluster, cluster_id)
    if cluster is None:
        return None
    for key in ("category", "representative_name"):
        if fields.get(key) is not None:
            setattr(cluster, key, fields[key])
    await session.commit()
    return cluster


def _merge_time_cluster_stats(prices: list[float]) -> dict:
    """EAI-CUSTOM (2026-09-24 bug: 合并后统计卡不重算): 镜像技能侧
    compute_stats(scripts/stats.py)的产物形状,供合并/移动后人工重算——
    管线侧仍以技能实现为唯一真相源。价格只取 ok/corrected(与管线同口径)。
    注意: 只保证聚合统计自洽;行级 is_outlier 沿用旧簇判定,重聚类时重新推导。
    """
    import statistics as _stats

    if not prices:
        return {
            "count": 0, "mean": None, "min": None, "max": None,
            "median": None, "std": None, "outlier_count": 0,
            "outlier_threshold": None,
        }

    def _percentile(sorted_vals: list[float], p: float) -> float:
        if len(sorted_vals) == 1:
            return sorted_vals[0]
        k = (len(sorted_vals) - 1) * p
        f = int(k)
        c = k - f
        if f + 1 < len(sorted_vals):
            return sorted_vals[f] + c * (sorted_vals[f + 1] - sorted_vals[f])
        return sorted_vals[f]

    sp = sorted(prices)
    q1, q3 = _percentile(sp, 0.25), _percentile(sp, 0.75)
    upper_fence = q3 + 1.5 * (q3 - q1)
    lower_fence = q1 - 1.5 * (q3 - q1)
    return {
        "count": len(prices),
        "mean": round(_stats.mean(prices), 2),
        "min": round(min(prices), 2),
        "max": round(max(prices), 2),
        "median": round(_stats.median(prices), 2),
        "std": round(_stats.pstdev(prices) if len(prices) > 1 else 0.0, 2),
        "outlier_count": sum(1 for p in prices if p < lower_fence or p > upper_fence),
        "outlier_threshold": round(upper_fence, 2),
    }


async def refresh_cluster_stats(session: AsyncSession, cluster_id: UUID) -> None:
    """按成员重算指定簇的派生字段:item_count + ok/corrected 单价 stats
    (合并/移动/删除货物后的增量刷新)。"""
    cluster = await session.get(CpaCluster, cluster_id)
    if cluster is None:
        return
    cluster.item_count = await session.scalar(
        select(func.count()).select_from(
            select(CpaItem).where(CpaItem.cluster_id == cluster_id).subquery()
        )
    ) or 0
    prices = (
        await session.execute(
            select(CpaItem.unit_price).where(
                CpaItem.cluster_id == cluster_id,
                CpaItem.validation_status.in_(("ok", "corrected")),
                CpaItem.unit_price.is_not(None),
            )
        )
    ).scalars().all()
    cluster.stats = _merge_time_cluster_stats([float(p) for p in prices])


async def merge_clusters(
    session: AsyncSession,
    cluster_ids: list[UUID],
    representative_name: str,
    category: str = "未分类",
) -> CpaCluster | None:
    if len(cluster_ids) < 2:
        raise ValueError("merge requires at least 2 clusters")
    new_cluster = CpaCluster(category=category, representative_name=representative_name, status="pending", item_count=0)
    session.add(new_cluster)
    await session.flush()
    await session.execute(update(CpaItem).where(CpaItem.cluster_id.in_(cluster_ids)).values(cluster_id=new_cluster.id))
    new_cluster.item_count = await session.scalar(select(func.count()).select_from(select(CpaItem).where(CpaItem.cluster_id == new_cluster.id).subquery())) or 0
    # EAI-CUSTOM (2026-09-24): 合并后按成员 ok/corrected 单价重算统计——此前
    # stats 列留空,右侧统计卡(均值/最值/中位数)不更新。
    await refresh_cluster_stats(session, new_cluster.id)
    await session.execute(delete(CpaCluster).where(CpaCluster.id.in_(cluster_ids)))
    await session.commit()
    return new_cluster


async def move_item(session: AsyncSession, item_id: UUID, target_cluster_id: UUID) -> CpaItem | None:
    item = await session.get(CpaItem, item_id)
    if item is None:
        return None
    source_cluster_id = item.cluster_id
    item.cluster_id = target_cluster_id
    await session.commit()
    # 移出/移入两侧簇的统计都随成员变化失效,一并重算。
    await refresh_cluster_stats(session, target_cluster_id)
    if source_cluster_id is not None:
        await refresh_cluster_stats(session, source_cluster_id)
    await session.commit()
    return item


# --- Items (functional area 3) ---------------------------------------------


async def _attach_cluster_stats(session: AsyncSession, items: list[CpaItem]) -> None:
    """EAI-CUSTOM F3a 离群语义分层: 为一页 items 一次性预取簇统计并挂为非映射属性。

    一条 JOIN 聚合取 {cluster_id: (stats, doc_count)},零 N+1(与 list_documents
    的 items_total KPI 同型手法);无簇行跳过、空列表直接返回。填充三个 ItemOut
    非列属性(由 from_attributes 序列化):
      - cluster_median: 簇 stats.median(管线 compute_stats 落库的 ok/corrected 单价中位)
      - deviation_pct:  本行单价相对簇中位的有符号比率 (price-median)/median,正=高于;
                        median 缺失/为 0 或行无价时置 None
      - cluster_doc_count: 簇内 distinct document_id 数(簇横跨几份合同)
    任何一条统计缺失只让对应字段为 None,绝不让查询本身失败。
    """
    ids = sorted({it.cluster_id for it in items if it.cluster_id is not None}, key=str)
    if not items or not ids:
        return
    rows = await session.execute(
        select(CpaCluster.id, CpaCluster.stats, func.count(func.distinct(CpaItem.document_id)))
        .join(CpaItem, CpaItem.cluster_id == CpaCluster.id)
        .where(CpaCluster.id.in_(ids))
        .group_by(CpaCluster.id, CpaCluster.stats)
    )
    info = {row[0]: (row[1] if isinstance(row[1], dict) else {}, int(row[2] or 0)) for row in rows.all()}
    for it in items:
        # 先统一置 None,保证任何行(含无簇行)上三属性都存在,消费方无需 hasattr 探测
        it.cluster_median = None
        it.deviation_pct = None
        it.cluster_doc_count = None
        if it.cluster_id is None:
            continue
        stats, doc_count = info.get(it.cluster_id, ({}, 0))
        it.cluster_doc_count = doc_count
        median = stats.get("median")
        it.cluster_median = float(median) if median is not None else None
        if it.cluster_median and float(it.cluster_median) != 0 and it.unit_price is not None:
            it.deviation_pct = (float(it.unit_price) - float(it.cluster_median)) / float(it.cluster_median)
        else:
            it.deviation_pct = None


async def list_items(
    session: AsyncSession,
    goods_name: str | None = None,
    source_contract_no: str | None = None,
    cluster_id: UUID | None = None,
    run_id: UUID | None = None,
    only_outliers: bool = False,
    validation_status: str | None = None,
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
    if validation_status:
        stmt = stmt.where(CpaItem.validation_status == validation_status)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CpaItem.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    items = list(result.scalars().all())
    await _attach_cluster_stats(session, items)  # EAI-CUSTOM F3a: 一条聚合预取簇统计
    return items, int(total)


async def update_item(session: AsyncSession, item_id: UUID, fields: dict[str, Any]) -> CpaItem | None:
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
    # v3 规则生态 L4 锚词暂存(设计 2026-09-19-cpa-table-recognition-three-layer §4):
    # 人工修正(改价)/采纳(validation_status=ok)都是对该行价格的人工确认,反推
    # 价格列当前表头词追加进 parse_meta.suggested_anchors。仅暂存不自动生效。
    if fields.get("unit_price") is not None or fields.get("validation_status") in ("ok", "corrected"):
        confirmed = fields["unit_price"] if fields.get("unit_price") is not None else item.unit_price
        try:
            doc = await session.get(CpaDocument, item.document_id)
            if doc is not None:
                await _harvest_price_anchor(doc, [(item, confirmed)])
        except Exception:
            logger.warning("suggested_anchors harvest failed for item %s", item_id, exc_info=True)
    await session.commit()
    return item


async def delete_item(session: AsyncSession, item_id: UUID) -> bool:
    item = await session.get(CpaItem, item_id)
    affected = item.cluster_id if item is not None else None
    result = await session.execute(delete(CpaItem).where(CpaItem.id == item_id))
    await session.commit()
    # EAI-CUSTOM (2026-09-24): 被删货物所属簇的 item_count/stats 随之失效,重算。
    if affected is not None:
        await refresh_cluster_stats(session, affected)
        await session.commit()
    return (result.rowcount or 0) > 0


async def list_item_contracts(session: AsyncSession) -> list[dict]:
    """Distinct source_contract_no with item counts (for the items-page filter).

    Only non-null contracts. Ordered by count desc so the most-represented
    contracts appear first in the dropdown.
    """
    rows = await session.execute(select(CpaItem.source_contract_no, func.count()).where(CpaItem.source_contract_no.is_not(None)).group_by(CpaItem.source_contract_no).order_by(func.count().desc()))
    return [{"source_contract_no": no, "count": int(cnt)} for no, cnt in rows.all()]


async def delete_items_batch(session: AsyncSession, item_ids: list[UUID]) -> int:
    affected = (
        await session.execute(
            select(CpaItem.cluster_id).where(CpaItem.id.in_(item_ids)).distinct()
        )
    ).scalars().all()
    result = await session.execute(delete(CpaItem).where(CpaItem.id.in_(item_ids)))
    await session.commit()
    for cid in affected:
        if cid is not None:  # EAI-CUSTOM (2026-09-24): 受影响簇统计重算
            await refresh_cluster_stats(session, cid)
    await session.commit()
    return result.rowcount or 0


async def batch_validate_items(session: AsyncSession, item_ids: list[UUID], validation_status: str = "ok") -> int:
    """Batch update validation_status (ok/corrected) for selected items."""
    result = await session.execute(update(CpaItem).where(CpaItem.id.in_(item_ids)).values(validation_status=validation_status))
    if validation_status in ("ok", "corrected"):
        # v3 规则生态 L4 锚词暂存(设计 §4): 批量采纳同样是人工确认,按文档分组
        # 收割表头词(每文档只读一次 OCR 缓存);单文档失败不影响其余/落库本身。
        try:
            rows = await session.execute(select(CpaItem).where(CpaItem.id.in_(item_ids), CpaItem.unit_price.is_not(None), CpaItem.source_page.is_not(None)))
            by_doc: dict[UUID, list[CpaItem]] = {}
            for it in rows.scalars().all():
                by_doc.setdefault(it.document_id, []).append(it)
            for doc_id, items in by_doc.items():
                doc = await session.get(CpaDocument, doc_id)
                if doc is not None:
                    await _harvest_price_anchor(doc, [(it, it.unit_price) for it in items])
        except Exception:
            logger.warning("suggested_anchors batch harvest failed", exc_info=True)
    await session.commit()
    return result.rowcount or 0


# --- L4 锚词暂存(suggested_anchors, 设计 2026-09-19 three-layer §4) ---------
# 人工修正/采纳落库时,反推该列当前表头词追加进 cpa_documents.parse_meta.
# suggested_anchors(dict: role → [words],去重)。"核一次强一次"——仅暂存,
# 绝不自动生效: seed 管线只读 config.table_seeds,这里的词须经人工审查后
# 才能手工并入规则库。


def merge_suggested_anchors(parse_meta: dict | None, additions: dict[str, Any]) -> dict:
    """把人工核验反推的 role→表头词 追加进 parse_meta.suggested_anchors(去重保序)。

    返回新 dict(原入参不被原地改)——重新赋值才能让 SQLAlchemy JSONB 列判脏。
    additions: {role: str | [str, ...]};空串/空白词丢弃。"""
    meta = dict(parse_meta) if isinstance(parse_meta, dict) else {}
    stored = meta.get("suggested_anchors")
    anchors: dict[str, list[str]] = {str(k): list(v) if isinstance(v, list) else [] for k, v in stored.items()} if isinstance(stored, dict) else {}
    for role, words in (additions or {}).items():
        if not role:
            continue
        bucket = anchors.setdefault(str(role), [])
        word_list = [words] if isinstance(words, str) else list(words or [])
        for w in word_list:
            w = str(w).strip()
            if w and w not in bucket:
                bucket.append(w)
    meta["suggested_anchors"] = anchors
    return meta


def _cell_to_float(txt: Any) -> float | None:
    """宽松数值解析(千分位逗号/空白/¥/元 后缀);非数值返回 None。"""
    t = str(txt or "").strip()
    for ch in (",", "，", " ", "¥", "￥", "元"):
        t = t.replace(ch, "")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _header_word_for_price(rows: list, row_idx: int | None, price: float) -> str | None:
    """反推价格列的当前表头词(设计 §4 L4): 数据行 rows[row_idx] 中找数值≈price
    的列,再自该行向上找该列第一个非空且非数值的单元格文本(内层表头)。
    人工手填的价格不在源行内(无法反推)/缺溯源 → None(不暂存)。"""
    if row_idx is None or not rows or not (0 <= row_idx < len(rows)) or price is None:
        return None
    row = rows[row_idx]
    for ci, cell in enumerate(row):
        v = _cell_to_float(cell)
        if v is None or abs(v - float(price)) > max(0.005, abs(float(price)) * 0.001):
            continue
        for r in range(row_idx - 1, -1, -1):
            above = rows[r] if r < len(rows) else []
            txt = str(above[ci]).strip() if ci < len(above) else ""
            if txt and _cell_to_float(txt) is None:
                return txt
        return None
    return None


def _load_ocr_tables(file_hash: str) -> list:
    """读单文档 OCR 缓存并解析出 tables(阻塞段,仅供 _harvest_price_anchor 使用)。

    EAI-CUSTOM (review fix 2026-09-20): storage.get_object 是阻塞的 MinIO 网络
    read,json.loads 整份缓存(v2 含 tokens,百页文档达数 MB)同为重 CPU——
    两者都不得跑在 gateway 事件循环上:本函数只被 async _harvest_price_anchor
    经 ``asyncio.to_thread`` 调用(与 bug-1917/#3084 的 blocking-io 纪律同型),
    否则每次人工修正/采纳点击(PATCH /items、批量采纳)都可能卡 loop 数百 ms,
    连带阻塞同 loop 上的流式 agent run。"""
    raw = storage.get_object(f"ocr/{file_hash}.json")
    return (json.loads(raw) or {}).get("tables") or []


async def _harvest_price_anchor(doc: CpaDocument, items_prices: list[tuple[CpaItem, Any]]) -> bool:
    """对单文档收割价格列锚词: 一次读该文档 OCR 缓存(ocr/{file_hash}.json),
    逐 (item, 人工确认价) 反推表头词并合并进 doc.parse_meta.suggested_anchors。
    缓存读取(阻塞 MinIO read + 大 JSON 解析)经 asyncio.to_thread 卸载出事件
    循环;缓存缺失/损坏/溯源缺失/价格不在行内 → 跳过该项;任何异常由调用方兜底
    (锚词暂存绝不让核验请求失败)。返回是否改写了 parse_meta。"""
    if not items_prices:
        return False
    try:
        tables = await asyncio.to_thread(_load_ocr_tables, doc.file_hash)
    except Exception:
        return False
    merged: dict | None = None
    changed = False
    for item, price in items_prices:
        if price is None or item.source_page is None:
            continue
        table = next(
            (t for t in tables if t.get("page_no") == item.source_page and (item.source_table_idx or 0) == (t.get("table_idx") or 0)),
            None,
        )
        if not table:
            continue
        try:
            word = _header_word_for_price(table.get("rows") or [], item.source_row_idx, float(price))
        except Exception:
            continue
        if not word:
            continue
        if merged is None:
            merged = merge_suggested_anchors(doc.parse_meta, {})
        bucket = merged["suggested_anchors"].setdefault("price_unit", [])
        if word not in bucket:
            bucket.append(word)
            changed = True
    if changed and merged is not None:
        doc.parse_meta = merged  # 整体重赋值 → JSONB 判脏
    return changed


async def delete_items_by_run(session: AsyncSession, run_id: UUID) -> int:
    affected = (
        await session.execute(
            select(CpaItem.cluster_id).where(CpaItem.run_id == run_id).distinct()
        )
    ).scalars().all()
    result = await session.execute(delete(CpaItem).where(CpaItem.run_id == run_id))
    await session.commit()
    for cid in affected:
        if cid is not None:  # EAI-CUSTOM (2026-09-24): 受影响簇统计重算
            await refresh_cluster_stats(session, cid)
    await session.commit()
    return result.rowcount or 0


# --- Runs (functional area 4) ----------------------------------------------


async def list_runs(
    session: AsyncSession,
    status: str | None = None,
    has_items: bool = False,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[CpaRunHistory], int]:
    stmt = select(CpaRunHistory)
    if status:
        stmt = stmt.where(CpaRunHistory.status == status)
    # EAI-CUSTOM: has_items — 只列当前真有明细(cpa_items)的任务,排除聚类/空任务,
    # 供分项校验页「来源任务」下拉使用;任务总览页(TasksView)不传此参,不受影响。
    if has_items:
        stmt = stmt.where(exists().where(CpaItem.run_id == CpaRunHistory.id))
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(CpaRunHistory.started_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all()), int(total)


async def get_run(session: AsyncSession, run_id: UUID) -> CpaRunHistory | None:
    return await session.get(CpaRunHistory, run_id)


async def delete_run(session: AsyncSession, run_id: UUID) -> bool:
    """Delete a run history record (does NOT cascade to items/docs)."""
    run = await session.get(CpaRunHistory, run_id)
    if run is None:
        return False
    await session.delete(run)
    await session.commit()
    return True


async def has_running_run(session: AsyncSession, phase: str) -> bool:
    """True if a run for the given phase (parse/cluster) is already in progress.

    Guards against concurrent OCR runs colliding on the same MinIO objects.
    NOTE: a gateway restart mid-run orphans the row at status='running' and
    would block re-trigger; clear manually (`UPDATE cpa_run_history SET
    status='failed' WHERE status='running'`) if that happens.
    """
    row = await session.scalar(select(func.count()).select_from(select(CpaRunHistory).where(CpaRunHistory.status == "running").where(CpaRunHistory.scope["phase"].astext == phase).subquery()))
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
    result = await session.execute(update(CpaRunHistory).where(CpaRunHistory.status == "running").where(CpaRunHistory.started_at < cutoff).values(status="failed", error="orphaned by restart (auto-cleaned)", finished_at=func.now()))
    await session.commit()
    return result.rowcount or 0


async def create_run(session: AsyncSession, **fields) -> CpaRunHistory:
    run = CpaRunHistory(**fields)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def finish_run(session: AsyncSession, run_id: UUID, **fields) -> CpaRunHistory | None:
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
    pending = await session.scalar(select(func.count()).select_from(select(CpaCluster).where(CpaCluster.status == "pending").subquery())) or 0
    confirmed = await session.scalar(select(func.count()).select_from(select(CpaCluster).where(CpaCluster.status == "confirmed").subquery())) or 0
    outlier_count = await session.scalar(select(func.count()).select_from(CpaItem).where(CpaItem.is_outlier.is_(True))) or 0
    return {
        "contract_count": int(contract_count),
        "item_count": int(item_count),
        "cluster_count": int(cluster_count),
        "pending_cluster_count": int(pending),
        "confirmed_cluster_count": int(confirmed),
        "outlier_count": int(outlier_count),
    }


async def price_range(session: AsyncSession) -> dict | None:
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
    top_goods = [{"name": n, "item_count": int(c), "avg_price": float(a) if a is not None else 0.0} for n, c, a in rows.all()]

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
    rows = await session.execute(select(CpaItem.validation_status, func.count()).group_by(CpaItem.validation_status))
    validation = [{"status": s, "count": int(c)} for s, c in rows.all()]

    # 4. cluster-size distribution
    rows = await session.execute(text("SELECT CASE WHEN item_count = 1 THEN '1' WHEN item_count <= 5 THEN '2-5' WHEN item_count <= 10 THEN '6-10' ELSE '10+' END AS sz, count(*) AS cnt FROM cpa_clusters GROUP BY sz"))
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

    base = select(CpaItem, CpaDocument).join(CpaDocument, CpaItem.document_id == CpaDocument.id)
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
    # EAI-CUSTOM F3a 离群语义分层: 明细行同样附带簇统计(name 模糊查询可能横跨
    # 多簇/无簇,helper 按行各自 cluster_id 预取;仅对本页 ≤limit 行一条聚合)。
    await _attach_cluster_stats(session, page_items)
    detail = [
        {
            "id": str(it.id),
            "document_id": str(it.document_id),
            "cluster_id": str(it.cluster_id) if it.cluster_id else None,  # EAI-CUSTOM F3a: 前端同簇基线概览分桶用
            "goods_name": it.goods_name,
            "contract_no": it.source_contract_no or "—",
            "supplier": next((d.supplier for d in docs if d.id == it.document_id), None) or "—",
            "unit_price": float(it.unit_price) if it.unit_price is not None else None,
            "price_untaxed": float(it.price_untaxed) if it.price_untaxed is not None else None,
            "quantity": float(it.quantity) if it.quantity is not None else None,
            "unit": it.unit or "—",
            "validation_status": it.validation_status,
            "is_outlier": it.is_outlier,
            "cluster_median": it.cluster_median,
            "deviation_pct": it.deviation_pct,
            "cluster_doc_count": it.cluster_doc_count,
            "source_page": it.source_page,
            "source_bbox": it.source_bbox,
        }
        for it in page_items
    ]

    # Display name: prefer the explicit name; for cluster queries, use the
    # cluster's representative_name (not items[0].goods_name, which may differ
    # in mixed clusters — a known char-ngram limitation).
    display_name = name
    if not display_name and cluster_id:
        cluster_obj = await session.get(CpaCluster, cluster_id)
        if cluster_obj:
            display_name = cluster_obj.representative_name
    if not display_name:
        display_name = items[0].goods_name if items else ""

    return {
        "goods_name": display_name,
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
            cfg = ConfigOut(**json.load(f))
    else:
        cfg = ConfigOut()
    if not cfg.table_seeds:
        from app.extensions.contract_price.seed_defaults import DEFAULT_TABLE_SEEDS

        cfg.table_seeds = copy.deepcopy(DEFAULT_TABLE_SEEDS)  # UI 首次打开即见内置规则库;深拷贝防止嵌套 columns/exclude 与模块常量共享引用
    return cfg


def save_config(cfg: ConfigOut) -> ConfigOut:
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg.model_dump(), f, ensure_ascii=False, indent=2)
    return cfg


def _config_path() -> str:
    return os.path.abspath(_CONFIG_PATH)


def mask_llm_key(cfg: ConfigOut) -> ConfigOut:
    """GET /config 响应边界: 把 llm_key 真值替换为掩码占位(write-only 回显)。

    EAI-CUSTOM (review fix 2026-09-20): system:access 权限点被基础 user 角色
    持有,明文 key 不得经 GET 原样返回。未配置(None/空串)保持原样,前端可据
    此区分"未配置"与"已配置"。仅改响应副本,load_config() 底层真值不受影响
    (service._resolve_llm_args 仍读真值注入子进程)。"""
    if cfg.llm_key:
        return cfg.model_copy(update={"llm_key": LLM_KEY_MASK})
    return cfg


def resolve_llm_key_mask(cfg: ConfigOut) -> ConfigOut:
    """PUT /config 入参边界: 掩码占位原样回传 = "key 未修改",还原为已存真值。

    防止前端把 GET 拿到的掩码在 PUT 往返中覆盖真值。新明文 key / 新 $ENV 形式
    (不等于掩码)直接落盘。已存 key 不可读(配置损坏)时置 None(等效清除,
    LLM 层 fail-closed 关闭),绝不把掩码字面量落盘。"""
    if cfg.llm_key != LLM_KEY_MASK:
        return cfg
    try:
        stored = load_config().llm_key
    except Exception:  # noqa: BLE001 — 配置不可读时掩码还原降级为清除,不阻塞保存
        stored = None
    return cfg.model_copy(update={"llm_key": stored})
