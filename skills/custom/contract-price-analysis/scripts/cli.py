"""End-to-end pipeline orchestration.

Flow: pull changed docs from RAGFlow → parse chunks → vectorize → DBSCAN cluster
→ compute per-cluster stats (flag outliers) → persist to cpa_ tables → emit Excel.

DB operations are best-effort: if ``postgres-ext`` is unreachable the pipeline
still parses/clusters/exports, skipping persistence. This keeps the CLI usable
from the host during development (the DB lives in Docker) and makes it testable
without a live database.
"""

import argparse
import asyncio
import logging
import os
import time
from typing import Any, Optional

from scripts.clustering.engine import cluster_items
from scripts.config import get_config
from scripts.db import init_schema
from scripts.excel_generator import generate_excel
from scripts.parser import parse_chunks
from scripts.ragflow_client import RagflowClient
from scripts.stats import compute_stats

logger = logging.getLogger(__name__)


async def _load_cached_hashes() -> dict[str, str]:
    """Load {ragflow_doc_id: doc_hash} for incremental filtering. Best-effort."""
    try:
        from scripts.db import async_session
        from scripts.models import CpaDocument
        from sqlalchemy import select

        async with async_session() as session:
            rows = await session.execute(select(CpaDocument.ragflow_doc_id, CpaDocument.doc_hash))
            return {doc_id: h for doc_id, h in rows.all()}
    except Exception as exc:
        logger.warning("Could not load cached hashes (DB unavailable): %s", exc)
        return {}


async def _persist(documents: list[dict], groups: list[dict], run_record: dict) -> None:
    """Persist documents, items, clusters + run history to cpa_ tables. Best-effort."""
    try:
        import uuid
        from datetime import datetime, timezone

        from scripts.db import async_session
        from scripts.models import CpaCluster, CpaDocument, CpaItem, CpaRunHistory

        async with async_session() as session:
            for doc in documents:
                session.add(
                    CpaDocument(
                        ragflow_doc_id=doc["id"],
                        doc_hash=doc.get("hash", ""),
                        contract_no=doc.get("name"),
                        parse_mode=run_record.get("scope", {}).get("mode", "table"),
                        parse_status="parsed",
                        parsed_at=datetime.now(timezone.utc),
                    )
                )
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
                    session.add(
                        CpaItem(
                            document_id=uuid.uuid4(),  # loose link; real doc mapping set by Plan 2 API
                            goods_name=it["goods_name"],
                            unit_price=it.get("unit_price"),
                            is_outlier=bool(it.get("is_outlier")),
                            cluster_id=cluster.id,
                            source_contract_no=it.get("source_contract_no"),
                            tech_params=it.get("tech_params"),
                            spec_model=it.get("spec_model"),
                        )
                    )
            session.add(CpaRunHistory(**{k: v for k, v in run_record.items() if k in CpaRunHistory.__table__.columns}))
            await session.commit()
    except Exception as exc:
        logger.warning("Persistence skipped (DB unavailable): %s", exc)


async def run_pipeline(
    mode: str = "table",
    trigger: str = "manual",
    client: Optional[RagflowClient] = None,
) -> list[dict[str, Any]]:
    """Run the full pipeline. Returns the list of cluster groups (for Excel/reporting).

    ``client`` is injectable for testing; if None a real RagflowClient is built
    from config.
    """
    started = time.monotonic()
    cfg = get_config()

    # DB schema init is best-effort.
    try:
        await init_schema()
    except Exception as exc:
        logger.warning("Schema init skipped (DB unavailable): %s", exc)

    own_client = client is None
    if own_client:
        client = RagflowClient(cfg.ragflow_base_url, cfg.ragflow_api_key, cfg.ragflow_kb_id)

    docs_processed = 0
    items_extracted = 0
    error: Optional[str] = None
    groups: list[dict[str, Any]] = []
    changed_docs: list[dict] = []
    try:
        all_docs = await client.list_documents()
        cached = await _load_cached_hashes()
        changed_docs = client.filter_changed(all_docs, cached)

        all_items: list[tuple[str, dict, Optional[float], dict]] = []
        for doc in changed_docs:
            try:
                chunks = await client.get_document_chunks(doc["id"])
                texts = [c.get("content_with_weight") or c.get("content") or "" for c in chunks]
                parsed = parse_chunks(texts, mode=mode)
                docs_processed += 1
                for p in parsed:
                    all_items.append(
                        (p.goods_name, p.tech_params, p.unit_price, {"spec_model": p.spec_model})
                    )
                    items_extracted += 1
            except Exception as exc:
                logger.warning("Failed to parse doc %s: %s", doc.get("id"), exc)

        samples = [(name, params) for name, params, _, _ in all_items]
        result = cluster_items(samples)

        groups = _build_groups(result, all_items)
    except Exception as exc:
        error = repr(exc)
        logger.exception("Pipeline failed")
    finally:
        if own_client:
            await client.close()

    duration_ms = int((time.monotonic() - started) * 1000)
    run_record = {
        "trigger_type": trigger,
        "status": "failed" if error else "completed",
        "docs_processed": docs_processed,
        "items_extracted": items_extracted,
        "clusters_formed": len(groups),
        "duration_ms": duration_ms,
        "error": error,
        "scope": {"mode": mode},
    }

    excel_path: Optional[str] = None
    if groups and not error:
        try:
            out_path = os.path.join(cfg.output_dir, f"contract-price-{trigger}.xlsx")
            os.makedirs(cfg.output_dir, exist_ok=True)
            generate_excel(groups, out_path)
            excel_path = out_path
            run_record["excel_path"] = excel_path
            logger.info("Excel written to %s", out_path)
        except Exception as exc:
            logger.exception("Excel generation failed")

    await _persist(changed_docs, groups, run_record)
    return groups


def _build_groups(result, all_items) -> list[dict[str, Any]]:
    """Turn clustering output + items into Excel-ready group dicts with outliers."""
    groups: list[dict[str, Any]] = []
    for label in sorted(l for l in set(result.labels) if l != -1):
        idxs = [i for i, l in enumerate(result.labels) if l == label]
        prices = [all_items[i][2] or 0.0 for i in idxs]
        stats = compute_stats(prices)
        threshold = stats.get("outlier_threshold")
        items = []
        for i in idxs:
            name, params, price, extra = all_items[i]
            is_outlier = threshold is not None and (price or 0) > threshold
            items.append({
                "goods_name": name,
                "spec_model": extra.get("spec_model"),
                "tech_params": params,
                "unit_price": price,
                "is_outlier": is_outlier,
            })
        groups.append({
            "name": result.representatives[label],
            "category": "未分类",
            "stats": stats,
            "items": items,
        })
    return groups


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Contract price analysis pipeline")
    parser.add_argument("--mode", choices=["table", "list", "mixed"], default="table")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    args = parser.parse_args()
    groups = asyncio.run(run_pipeline(mode=args.mode, trigger=args.trigger))
    print(f"Done. {len(groups)} cluster groups.")


if __name__ == "__main__":
    main()
