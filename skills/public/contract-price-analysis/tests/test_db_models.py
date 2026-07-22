"""Tests for cpa_ ORM models.

The insert test requires a live PostgreSQL (``postgres-ext``). In the Docker dev
environment the DB is not reachable from the host, so it auto-skips — run it
inside a container on the docker network when needed. The table-structure test
runs anywhere (no DB connection).
"""

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine


def test_models_define_expected_tables():
    """All four cpa_ tables and key columns are declared (no DB needed)."""
    from scripts.models import Base, CpaCluster, CpaDocument, CpaItem, CpaRunHistory

    table_names = set(Base.metadata.tables.keys())
    assert {
        "cpa_documents",
        "cpa_items",
        "cpa_clusters",
        "cpa_run_history",
    } <= table_names

    # JSONB tech_params on items + optimistic-lock version on clusters
    assert "tech_params" in CpaItem.__table__.columns
    assert "is_outlier" in CpaItem.__table__.columns
    assert "version" in CpaCluster.__table__.columns
    assert "status" in CpaCluster.__table__.columns


def _db_reachable_sync() -> bool:
    """Best-effort synchronous reachability probe (connect then dispose)."""
    import asyncio

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
        return asyncio.get_event_loop().run_until_complete(_probe())
    except Exception:
        return False


@pytest.fixture
def require_db():
    if not _db_reachable_sync():
        pytest.skip("postgres-ext not reachable from this environment; run inside Docker")


@pytest.mark.asyncio
async def test_insert_document_and_item(require_db):
    """Round-trip a document + item through the real DB (skipped without DB)."""
    from sqlalchemy import select

    from scripts.db import async_session, engine
    from scripts.models import Base, CpaDocument, CpaItem

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with async_session() as session:
            doc = CpaDocument(
                ragflow_doc_id="doc-1",
                doc_hash="h1",
                contract_no="C001",
                parse_mode="table",
                parse_status="parsed",
            )
            session.add(doc)
            await session.flush()
            item = CpaItem(
                document_id=doc.id,
                goods_name="高压开关柜",
                spec_model="KYN28",
                tech_params={"voltage_kv": 10},
                quantity=2,
                unit="台",
                unit_price=120000.00,
                source_contract_no="C001",
            )
            session.add(item)
            await session.commit()

        async with async_session() as session:
            result = await session.execute(
                select(CpaItem).where(CpaItem.goods_name == "高压开关柜")
            )
            fetched = result.scalar_one()
            assert float(fetched.unit_price) == 120000.00
            assert fetched.tech_params["voltage_kv"] == 10
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.drop_all,
                tables=[CpaItem.__table__, CpaDocument.__table__],
            )
