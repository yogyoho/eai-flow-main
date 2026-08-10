"""Tests for the contract_price extension (models, routes, schemas).

These run in the backend test environment (``PYTHONPATH=. uv run pytest``) and
verify the extension is wired into the shared Base + Gateway without needing a
live DB.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


def test_cpa_models_registered_on_shared_base():
    # Importing the extension registers its models on the shared Base.metadata.
    import app.extensions.contract_price  # noqa: F401
    from app.extensions.database import Base

    tables = set(Base.metadata.tables)
    assert {
        "cpa_documents",
        "cpa_items",
        "cpa_clusters",
        "cpa_run_history",
    } <= tables


def test_router_exposes_all_functional_areas():
    from app.extensions.contract_price import router

    paths = {r.path for r in router.routes}
    base = "/api/extensions/contract-price"
    # Functional area 1: documents
    assert f"{base}/documents" in paths
    # Functional area 2: clusters
    assert f"{base}/clusters" in paths
    assert f"{base}/clusters/merge" in paths
    # Functional area 3: items
    assert f"{base}/items" in paths
    # Functional area 4: runs
    assert f"{base}/runs" in paths
    # Functional area 5: config
    assert f"{base}/config" in paths
    # Functional area 6: dashboard
    assert f"{base}/dashboard" in paths
    # Pipeline trigger
    assert f"{base}/pipeline/run" in paths


def test_schemas_roundtrip():
    from app.extensions.contract_price.schemas import (
        ClusterMerge,
        ConfigOut,
        DashboardOut,
        ItemUpdate,
        PipelineRunRequest,
    )

    cfg = ConfigOut()
    assert cfg.cluster_eps == 0.6
    assert DashboardOut(
        contract_count=1, item_count=2, cluster_count=1,
        pending_cluster_count=1, confirmed_cluster_count=0,
    ).price_range is None
    merge = ClusterMerge(
        cluster_ids=["00000000-0000-0000-0000-000000000000"] * 2,
        representative_name="开关柜",
    )
    assert merge.representative_name == "开关柜"
    assert PipelineRunRequest().mode == "table"


def test_config_crud_roundtrip(tmp_path, monkeypatch):
    from app.extensions.contract_price import crud
    from app.extensions.contract_price.schemas import ConfigUpdate

    monkeypatch.setattr(crud, "_CONFIG_PATH", str(tmp_path / "config.json"))
    cfg = ConfigUpdate(parse_mode="list", scheduled_enabled=True, schedule_cron="0 2 * * *")
    crud.save_config(cfg)
    loaded = crud.load_config()
    assert loaded.parse_mode == "list"
    assert loaded.scheduled_enabled is True
    assert loaded.schedule_cron == "0 2 * * *"


@pytest.mark.asyncio
async def test_find_duplicate_document_matches_cross_filename():
    """Dedup-by-content: same hash under a different uri is a duplicate;
    same uri (re-upload) or no match returns None."""
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.contract_price import crud
    from app.extensions.contract_price.models import CpaDocument

    existing = CpaDocument(
        storage_uri="s3://cpa-contracts/orig.pdf",
        file_name="orig.pdf",
        file_hash="h1",
        file_type="pdf",
    )

    def session_returning(row):
        session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=row)  # sync SQLAlchemy method
        session.execute = AsyncMock(return_value=result)
        return session

    # same hash, different filename → duplicate found
    dup = await crud.find_duplicate_document(
        session_returning(existing), "h1", exclude_uri="s3://cpa-contracts/renamed.pdf"
    )
    assert dup is existing

    # no prior doc with that hash → None (new content allowed)
    assert await crud.find_duplicate_document(
        session_returning(None), "h1", exclude_uri="s3://cpa-contracts/x.pdf"
    ) is None


@pytest.mark.asyncio
async def test_delete_document_clears_clusters_when_doc_was_grouped():
    """Deleting a doc whose items are in the cluster snapshot clears all clusters
    (stale-snapshot invalidation)."""
    from app.extensions.contract_price import crud

    session = MagicMock()
    session.scalar = AsyncMock(return_value=1)  # in_snapshot = True
    executed = []

    async def fake_execute(stmt, *a, **kw):
        executed.append(stmt)
        r = MagicMock()
        r.rowcount = 1
        return r

    session.execute = fake_execute
    session.commit = AsyncMock()

    await crud.delete_document(session, uuid.UUID("00000000-0000-0000-0000-000000000000"))
    stmt_strs = [str(s) for s in executed]
    assert any("cpa_clusters" in s for s in stmt_strs), "clusters not cleared"


@pytest.mark.asyncio
async def test_delete_document_keeps_clusters_when_doc_not_grouped():
    """A doc whose items were never clustered doesn't touch the cluster snapshot."""
    from app.extensions.contract_price import crud

    session = MagicMock()
    session.scalar = AsyncMock(return_value=0)  # in_snapshot = False
    executed = []

    async def fake_execute(stmt, *a, **kw):
        executed.append(stmt)
        r = MagicMock()
        r.rowcount = 1
        return r

    session.execute = fake_execute
    session.commit = AsyncMock()

    await crud.delete_document(session, uuid.UUID("00000000-0000-0000-0000-000000000000"))
    stmt_strs = [str(s) for s in executed]
    assert not any("cpa_clusters" in s for s in stmt_strs), "clusters wrongly cleared"


def test_skill_dir_exists():
    """The gateway triggers the skill as a subprocess at service._SKILL_DIR.

    If that path drifts (the skill migrated custom→public in commit 86735708 and
    service.py missed it → bug-526), POST /pipeline/run fails silently with
    'skill not found'. This guard makes that regression loud. If the skill
    moves again, update service.py:_SKILL_DIR, not this test."""
    from app.extensions.contract_price.service import _SKILL_DIR

    assert _SKILL_DIR.exists(), (
        f"skill dir missing: {_SKILL_DIR} — the pipeline subprocess trigger is broken "
        "(upload→auto-parse workflow will fail). Update service.py:_SKILL_DIR."
    )
    assert (_SKILL_DIR / "scripts" / "cli.py").exists()


def _literal(stmt) -> str:
    """Render a SQLAlchemy statement with bound values inlined for assertion."""
    from sqlalchemy.dialects import postgresql

    return str(
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


@pytest.mark.asyncio
async def test_mark_documents_parsing_bulk_flips_pending_to_parsing():
    """「开始解析」:一条 UPDATE 把全部 pending 文档置为 parsing。"""
    from app.extensions.contract_price import crud

    session = MagicMock()
    captured = {}

    async def fake_execute(stmt, *a, **kw):
        captured["stmt"] = stmt
        r = MagicMock()
        r.rowcount = 3
        return r

    session.execute = fake_execute
    session.commit = AsyncMock()

    n = await crud.mark_documents_parsing(session)
    assert n == 3
    sql = _literal(captured["stmt"])
    assert "cpa_documents" in sql
    # WHERE 只命中 pending,SET 写入 parsing
    assert "parse_status = 'pending'" in sql
    assert "parse_status='parsing'" in sql
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_documents_parsing_scoped_to_single_storage_uri():
    """传 storage_uri 时只置该单文档(WHERE 同时含 storage_uri 与 pending)。"""
    from app.extensions.contract_price import crud

    session = MagicMock()
    captured = {}

    async def fake_execute(stmt, *a, **kw):
        captured["stmt"] = stmt
        r = MagicMock()
        r.rowcount = 1
        return r

    session.execute = fake_execute
    session.commit = AsyncMock()

    await crud.mark_documents_parsing(session, storage_uri="s3://cpa-contracts/x.pdf")
    sql = _literal(captured["stmt"])
    assert "storage_uri = 's3://cpa-contracts/x.pdf'" in sql
    assert "parse_status = 'pending'" in sql


@pytest.mark.asyncio
async def test_set_document_parse_status_overwrites_regardless_of_current():
    """「重新解析」:被重解析的文档当前可能是 parsed/needs_review,按 id 强制覆写。"""
    from app.extensions.contract_price import crud
    from app.extensions.contract_price.models import CpaDocument

    doc = CpaDocument(
        storage_uri="s3://cpa-contracts/a.pdf",
        file_name="a.pdf",
        file_hash="h",
        file_type="pdf",
        parse_status="parsed",
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=doc)
    session.commit = AsyncMock()

    returned = await crud.set_document_parse_status(
        session, uuid.UUID("00000000-0000-0000-0000-000000000000"), "parsing"
    )
    assert returned is doc
    assert doc.parse_status == "parsing"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_document_parse_status_missing_doc_returns_none():
    from app.extensions.contract_price import crud

    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    assert await crud.set_document_parse_status(
        session, uuid.UUID("00000000-0000-0000-0000-000000000000"), "parsing"
    ) is None


@pytest.mark.asyncio
async def test_mark_stale_parsing_failed_flips_parsing_to_failed():
    """子进程整体失败兜底:仍卡在 parsing 的文档 → failed。"""
    from app.extensions.contract_price import crud

    session = MagicMock()
    captured = {}

    async def fake_execute(stmt, *a, **kw):
        captured["stmt"] = stmt
        r = MagicMock()
        r.rowcount = 2
        return r

    session.execute = fake_execute
    session.commit = AsyncMock()

    n = await crud.mark_stale_parsing_failed(session, "解析任务失败: boom")
    assert n == 2
    sql = _literal(captured["stmt"])
    assert "parse_status = 'parsing'" in sql
    assert "parse_status='failed'" in sql
