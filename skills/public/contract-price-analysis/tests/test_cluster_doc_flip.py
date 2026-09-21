"""Regression for bug-3432: a successful cluster run must advance freshly parsed docs
to confirm_status=clustered.

bug-3432: _persist_clusters flipped docs by confirm_status (old confirm-gate leftover
from 72dfffa9ff's partial restore) while run_cluster selected items by parse_status —
a newly parsed doc (confirm_status=pending) got its items clustered but its UI badge
stuck at 已解析 forever. _flip_clustered_docs must use the same parse_status scope
(_CLUSTER_DOC_STATUSES).

Runs the flip inside a transaction and rolls back — real data is never touched.
Requires the postgres-ext DB (same idiom as test_db_models).
"""

import asyncio
import os
import uuid

import pytest

# conftest.py injects a bogus CPA_DATABASE_URL so collection never needs a DB;
# this test is the opposite — it needs the real one. Drop the sentinel so
# scripts.config falls back to the real default (or the ambient env when set).
if os.environ.get("CPA_DATABASE_URL", "").endswith("@localhost:1/none"):
    del os.environ["CPA_DATABASE_URL"]


def _db_reachable_sync() -> bool:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    async def _probe() -> bool:
        from scripts.config import get_config

        try:
            eng = create_async_engine(get_config().database_url)
            async with eng.connect() as conn:
                await conn.execute(sa.text("SELECT 1"))
            await eng.dispose()
            return True
        except Exception:
            return False

    try:
        # ponytail: asyncio.run, not get_event_loop() — pytest-asyncio leaves a
        # closed loop on the thread, run_until_complete then raises RuntimeError.
        return asyncio.run(_probe())
    except Exception:
        return False


@pytest.fixture
def require_db():
    if not _db_reachable_sync():
        pytest.skip("postgres-ext not reachable from this environment; run inside Docker")


def test_flip_advances_pending_parsed_doc(require_db):
    from scripts.cli import _CLUSTER_DOC_STATUSES, _flip_clustered_docs
    from scripts.db import async_session
    from scripts.models import CpaDocument

    assert set(_CLUSTER_DOC_STATUSES) == {"parsed", "needs_review"}

    async def _run() -> str:
        async with async_session() as session:
            doc_id = uuid.uuid4()
            session.add(
                CpaDocument(
                    id=doc_id,
                    storage_uri=f"s3://test/__test_bug3432__/{doc_id}.pdf",
                    file_name="__test_bug3432__.pdf",
                    file_hash="test-" + doc_id.hex,
                    file_type="pdf",
                    parse_mode="ocr",
                    parse_status="parsed",
                    confirm_status="pending",
                )
            )
            await session.flush()
            await _flip_clustered_docs(session)
            confirm = (await session.get(CpaDocument, doc_id)).confirm_status
            await session.rollback()  # 不污染真实数据
            return confirm

    assert asyncio.run(_run()) == "clustered"
