"""End-to-end pipeline (v2: MinIO + eai-flow-ocr).

Flow: scan MinIO for changed contracts → OCR each via eai-flow-ocr → classify
tables (keep only goods/price) → validate prices (flag glued/implausible) →
DBSCAN cluster → per-cluster stats + outliers → persist cpa_ tables → Excel.

DB ops are best-effort: if postgres-ext is unreachable the pipeline still
parses/clusters/exports, skipping persistence (keeps it usable from host
during dev and testable without a live DB).
"""

import argparse
import asyncio
import base64
import logging
import os
import time
from typing import Any, Optional

from scripts.clustering.engine import cluster_items
from scripts.config import get_config
from scripts.document_parser import parse_document
from scripts.document_scanner import scan_changed
from scripts.excel_generator import generate_excel
from scripts.price_validator import parse_qty, split_glued, validate_price
from scripts.project_fields import extract_project_fields
from scripts.stats import compute_stats
from scripts.storage import ContractStore
from scripts.table_classifier import classify, extract_items

logger = logging.getLogger(__name__)


async def _load_cached_hashes() -> dict:
    """Load {file_name(minio key): file_hash} for incremental filtering."""
    try:
        from sqlalchemy import select

        from scripts.db import async_session
        from scripts.models import CpaDocument

        async with async_session() as session:
            rows = await session.execute(select(CpaDocument.file_name, CpaDocument.file_hash))
            return {name: h for name, h in rows.all()}
    except Exception as exc:
        logger.warning("Could not load cached hashes (DB unavailable): %s", exc)
        return {}


def _cell_bbox(table, row_idx: int, col_idx: int) -> list:
    """Read a cell's page-relative bbox from the table's cell_bboxes grid."""
    try:
        row = table.cell_bboxes[row_idx]
        if col_idx < len(row):
            return row[col_idx]
    except (IndexError, TypeError):
        pass
    return [0, 0, 0, 0]


def _extract_from_tables(tables: list, doc_uri: str) -> tuple:
    """Classify each table; from goods/price tables build item dicts.

    Returns (items, parse_meta). Items carry traceability (page/bbox/row) +
    validation_status. Non-goods tables are counted in parse_meta, never
    silently dropped.
    """
    items: list[dict] = []
    meta: dict = {"tables_found": len(tables), "goods_tables": 0, "rows_extracted": 0, "skipped": {}}
    for table in tables:
        ttype, roles, header_rows = classify(table.rows)
        if ttype != "goods_price":
            meta["skipped"][ttype] = meta["skipped"].get(ttype, 0) + 1
            continue
        meta["goods_tables"] += 1
        raw = extract_items(table.rows, roles, header_rows)
        # peers = single-number 含税 cells (cross-row outlier check on 含税价)
        peers = [
            split_glued(r["price_taxed_raw"])[0]
            for r in raw
            if len(split_glued(r["price_taxed_raw"])) == 1
        ]
        for r in raw:
            taxed, vstatus_t, reason_t = validate_price(r["price_taxed_raw"], peers)
            untaxed, vstatus_u, reason_u = validate_price(r["price_untaxed_raw"], peers)
            vstatus = "needs_review" if "needs_review" in (vstatus_t, vstatus_u) else "ok"
            items.append(
                {
                    "goods_name": r["name"],
                    "spec_model": r["spec"],
                    "tech_params": {},
                    "quantity": parse_qty(r["qty_raw"]),
                    "unit": r["unit"],
                    "unit_price": taxed,  # 含税单价(统计)
                    "price_untaxed": untaxed,  # 不含税单价(审计)
                    "source_doc_uri": doc_uri,
                    "source_page": table.page_no,
                    "source_bbox": _cell_bbox(table, r["row_idx"], roles.get("name", 0)),
                    "source_table_idx": table.table_idx,
                    "source_row_idx": r["row_idx"],
                    "confidence": table.mean_confidence,
                    "validation_status": vstatus,
                    "price_reason": reason_t or reason_u,
                }
            )
        meta["rows_extracted"] += len(raw)
    return items, meta


def _build_groups(result, all_items: list) -> list:
    """Turn clustering output + items into Excel-ready group dicts."""
    groups: list[dict] = []
    for label in sorted(l for l in set(result.labels) if l != -1):
        idxs = [i for i, l in enumerate(result.labels) if l == label]
        prices = [all_items[i].get("unit_price") or 0.0 for i in idxs]
        stats = compute_stats(prices)
        threshold = stats.get("outlier_threshold")
        items = []
        for i in idxs:
            it = all_items[i]
            price = it.get("unit_price") or 0
            it["is_outlier"] = threshold is not None and price > threshold
            items.append(it)
        groups.append({"name": result.representatives[label], "category": "未分类", "stats": stats, "items": items})
    return groups


async def _persist(documents: list, groups: list, run_record: dict) -> None:
    """Upsert documents (by storage_uri), write clusters + items, record run."""
    try:
        from datetime import datetime, timezone

        from sqlalchemy import delete, select

        from scripts.db import async_session
        from scripts.models import CpaCluster, CpaDocument, CpaItem, CpaRunHistory

        async with async_session() as session:
            doc_id_map: dict = {}
            now = datetime.now(timezone.utc)
            for doc in documents:
                existing = (
                    await session.execute(select(CpaDocument).where(CpaDocument.storage_uri == doc["storage_uri"]))
                ).scalar_one_or_none()
                if existing is None:
                    existing = CpaDocument(
                        storage_uri=doc["storage_uri"],
                        file_name=doc["file_name"],
                        file_hash=doc["hash"],
                        file_type=doc["type"],
                        quick_fp=doc.get("quick_fp"),
                        parse_mode=doc.get("parse_mode", "ocr"),
                        parse_status=doc.get("parse_status", "parsed"),
                        parse_meta=doc.get("parse_meta"),
                        page_count=doc.get("page_count"),
                        preview_prefix=doc.get("preview_prefix"),
                        project_name=doc.get("project_name"),
                        project_location=doc.get("project_location"),
                        parsed_at=now,
                    )
                    session.add(existing)
                    await session.flush()
                else:
                    existing.file_hash = doc["hash"]
                    existing.parse_status = doc.get("parse_status", "parsed")
                    existing.parse_meta = doc.get("parse_meta")
                    existing.preview_prefix = doc.get("preview_prefix")
                    existing.parsed_at = now
                    # only overwrite project fields when re-OCR found them, so a
                    # manual UI edit (stored earlier) is not wiped by a null hit.
                    if doc.get("project_name"):
                        existing.project_name = doc["project_name"]
                    if doc.get("project_location"):
                        existing.project_location = doc["project_location"]
                    await session.execute(delete(CpaItem).where(CpaItem.document_id == existing.id))
                doc_id_map[doc["storage_uri"]] = existing.id

            for group in groups:
                cluster = CpaCluster(
                    category=group["category"],
                    representative_name=group["name"],
                    status="pending",
                    stats=group["stats"],
                    item_count=len(group["items"]),
                )
                session.add(cluster)
                await session.flush()
                for it in group["items"]:
                    dpk = doc_id_map.get(it.get("source_doc_uri"))
                    if dpk is None:
                        continue  # no resolvable doc → skip rather than violate FK
                    session.add(
                        CpaItem(
                            document_id=dpk,
                            goods_name=it["goods_name"],
                            spec_model=it.get("spec_model"),
                            tech_params=it.get("tech_params"),
                            quantity=it.get("quantity"),
                            unit=it.get("unit"),
                            unit_price=it.get("unit_price"),
                            price_untaxed=it.get("price_untaxed"),
                            cluster_id=cluster.id,
                            is_outlier=bool(it.get("is_outlier")),
                            source_page=it.get("source_page"),
                            source_bbox=it.get("source_bbox"),
                            source_table_idx=it.get("source_table_idx"),
                            source_row_idx=it.get("source_row_idx"),
                            confidence=it.get("confidence"),
                            validation_status=it.get("validation_status", "ok"),
                        )
                    )
            session.add(
                CpaRunHistory(**{k: v for k, v in run_record.items() if k in CpaRunHistory.__table__.columns})
            )
            await session.commit()
    except Exception as exc:
        logger.warning("Persistence skipped (DB unavailable): %s", exc)


async def run_pipeline(trigger: str = "manual") -> list:
    """Run the full pipeline. Returns cluster groups (for Excel/reporting)."""
    started = time.monotonic()
    cfg = get_config()

    try:
        from scripts.db import init_schema
        await init_schema()
    except Exception as exc:
        logger.warning("Schema init skipped (DB unavailable): %s", exc)

    store = ContractStore(cfg)
    cached = await _load_cached_hashes()
    changed = scan_changed(store, cached)
    logger.info("Scan: %d changed / %d cached contracts", len(changed), len(cached))

    docs_processed = 0
    items_extracted = 0
    error: Optional[str] = None
    documents: list[dict] = []
    all_items: list[dict] = []

    try:
        for ch in changed:
            key = ch["key"]
            try:
                file_bytes = store.get(key)
                tables, page_texts = await parse_document(file_bytes, key, cfg.ocr_service_url)
                items, meta = _extract_from_tables(tables, f"s3://{cfg.minio_bucket}/{key}")
                project_name, project_location = extract_project_fields(page_texts)
                # Persist preview PNGs for pages that contain a goods table, so
                # the traceback UI can overlay bboxes later.
                preview_prefix = None
                goods_pages = {
                    t.page_no for t in tables if classify(t.rows)[0] == "goods_price"
                }
                for t in tables:
                    if t.page_no in goods_pages and t.page_preview_b64 and not preview_prefix:
                        doc_id = ch["hash"][:8]
                        preview_prefix = store.put_preview(doc_id, t.page_no, base64.b64decode(t.page_preview_b64))
                    elif t.page_no in goods_pages and preview_prefix and t.page_preview_b64:
                        store.put_preview(ch["hash"][:8], t.page_no, base64.b64decode(t.page_preview_b64))
                documents.append(
                    {
                        "storage_uri": f"s3://{cfg.minio_bucket}/{key}",
                        "file_name": key,
                        "hash": ch["hash"],
                        "type": os.path.splitext(key)[1].lstrip(".").lower() or "pdf",
                        "quick_fp": f"{key}|{ch['size']}",
                        "parse_mode": "ocr",
                        # needs_review when nothing was extracted OR both project
                        # fields are missing (regex couldn't anchor front-page labels
                        # → human fills them via the management UI).
                        "parse_status": "needs_review"
                        if (not (items or meta["tables_found"]))
                        or (not project_name and not project_location)
                        else "parsed",
                        "parse_meta": meta,
                        "page_count": max((t.page_no for t in tables), default=None),
                        "preview_prefix": preview_prefix,
                        "project_name": project_name,
                        "project_location": project_location,
                    }
                )
                all_items.extend(items)
                docs_processed += 1
                items_extracted += len(items)
                logger.info("Parsed %s: %d tables, %d items", key, meta["tables_found"], len(items))
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", key, exc)
                documents.append(
                    {
                        "storage_uri": f"s3://{cfg.minio_bucket}/{key}",
                        "file_name": key,
                        "hash": ch["hash"],
                        "type": os.path.splitext(key)[1].lstrip(".").lower() or "pdf",
                        "parse_mode": "ocr",
                        "parse_status": "failed",
                        "parse_meta": {"error": repr(exc)},
                    }
                )

        samples = [(it["goods_name"], it.get("tech_params") or {}) for it in all_items]
        result = cluster_items(samples)
        groups = _build_groups(result, all_items)
    except Exception as exc:
        error = repr(exc)
        logger.exception("Pipeline failed")
        groups = []

    duration_ms = int((time.monotonic() - started) * 1000)
    run_record = {
        "trigger_type": trigger,
        "status": "failed" if error else "completed",
        "docs_processed": docs_processed,
        "items_extracted": items_extracted,
        "clusters_formed": len(groups),
        "duration_ms": duration_ms,
        "error": error,
        "scope": {"engine": "ocr-v2"},
    }

    excel_path: Optional[str] = None
    if groups and not error:
        try:
            os.makedirs(cfg.output_dir, exist_ok=True)
            out_path = os.path.join(cfg.output_dir, f"contract-price-{trigger}.xlsx")
            generate_excel(groups, out_path)
            excel_path = out_path
            run_record["excel_path"] = excel_path
            logger.info("Excel written to %s", out_path)
        except Exception:
            logger.exception("Excel generation failed")

    await _persist(documents, groups, run_record)
    return groups


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Contract price analysis pipeline (v2: OCR)")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    args = parser.parse_args()
    groups = asyncio.run(run_pipeline(trigger=args.trigger))
    print(f"Done. {len(groups)} cluster groups.")


if __name__ == "__main__":
    main()
