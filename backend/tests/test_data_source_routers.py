"""Router-level tests for data_source endpoints. Service layer is mocked."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.extensions.data_source.routers import router


@pytest.fixture(autouse=True)
def _stub_auth_caches():
    # EAI-CUSTOM: require_permission 内部走 ABAC 引擎 + identity 解析(均查 DB):
    #   engine=load_active_policies(db) → policy_loader AttributeError;
    #   identity=provider.resolve(current_user.id, db) → identity AttributeError。
    # 纯单测里 db 是 AsyncMock,这两条 DB 链全断。check_permission 在拿 engine/identity 前
    # 先查 per-request 缓存(get_cached_engine/get_cached_identity),None 才落 DB。
    # 预填这两个缓存 → 跳过全部 DB 工作;再让 engine.check 直返 True → 放行 current_user。
    fake_engine = MagicMock()
    fake_engine.check.return_value = True
    fake_identity = MagicMock(role_code="test", user_id="t", username="t")
    with patch("app.extensions.auth.cache.get_cached_engine", return_value=fake_engine), patch("app.extensions.auth.cache.get_cached_identity", return_value=fake_identity):
        yield


def _fake_ds(**overrides):
    """A complete fake DataSource with every DataSourceResponse field populated."""
    base = {
        "id": str(uuid4()),
        "name": "prod",
        "description": None,
        "type": "database",
        "connection_config": {"host": "h"},
        "auth_type": "none",
        "sync_mode": "manual",
        "sync_config": None,
        "status": "disconnected",
        "last_sync_at": None,
        "created_by": None,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }
    base.update(overrides)
    m = MagicMock()
    for k, v in base.items():
        setattr(m, k, v)
    return m


def _build_app():
    from fastapi import FastAPI

    from app.extensions.auth.middleware import get_current_user
    from app.extensions.database import get_db

    app = FastAPI()
    app.include_router(router)
    fake_user = MagicMock(id=uuid4())

    async def _fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_db] = _fake_db
    return app


@pytest.mark.asyncio
async def test_list_returns_items():
    with patch(
        "app.extensions.data_source.routers.DataSourceService.list",
        AsyncMock(return_value=[_fake_ds(name="prod")]),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/extensions/data-sources")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["name"] == "prod"


@pytest.mark.asyncio
async def test_create_returns_201():
    # get_by_name MUST be stubbed to None, else the real service returns a truthy mock → 400 duplicate
    with (
        patch(
            "app.extensions.data_source.routers.DataSourceService.get_by_name",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.extensions.data_source.routers.DataSourceService.create",
            AsyncMock(return_value=_fake_ds(name="n", description="测试描述")),
        ),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/extensions/data-sources",
                json={"name": "n", "type": "api", "connection_config": {}, "description": "测试描述"},
            )
    assert resp.status_code == 201
    assert resp.json()["name"] == "n"
    assert resp.json()["description"] == "测试描述"


@pytest.mark.asyncio
async def test_create_400_on_duplicate_name():
    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_name",
        AsyncMock(return_value=_fake_ds()),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/extensions/data-sources",
                json={"name": "dup", "type": "api", "connection_config": {}},
            )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_returns_204_when_found():
    with patch(
        "app.extensions.data_source.routers.DataSourceService.delete",
        AsyncMock(return_value=True),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/api/extensions/data-sources/{uuid4()}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_returns_404_when_missing():
    with patch(
        "app.extensions.data_source.routers.DataSourceService.delete",
        AsyncMock(return_value=False),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/api/extensions/data-sources/{uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_test_endpoint_delegates_to_service():
    from app.extensions.data_source.schemas import TestConnectionResult

    with (
        patch(
            "app.extensions.data_source.routers.DataSourceService.get_by_id",
            AsyncMock(return_value=_fake_ds()),
        ),
        patch(
            "app.extensions.data_source.routers.DataSourceService.test_connection",
            AsyncMock(return_value=TestConnectionResult(success=True, message="ok")),
        ),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/extensions/data-sources/{uuid4()}/test")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_test_endpoint_404_when_missing():
    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_id",
        AsyncMock(return_value=None),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/extensions/data-sources/{uuid4()}/test")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sync_endpoint():
    with (
        patch(
            "app.extensions.data_source.routers.DataSourceService.get_by_id",
            AsyncMock(return_value=_fake_ds()),
        ),
        patch(
            "app.extensions.data_source.routers.DataSourceService.sync",
            AsyncMock(
                return_value={
                    "status": "connected",
                    "last_sync_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "metadata": {"k": 1},
                }
            ),
        ),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/extensions/data-sources/{uuid4()}/sync")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "connected"
    assert body["metadata"] == {"k": 1}


def _fake_dataset(**overrides):
    """Fake DataSourceDataset,字段对齐 DatasetResponse。"""
    base = {
        "id": str(uuid4()),
        "source_id": str(uuid4()),
        "table_name": "bid_summary",
        "label": "投标总览",
        "description": "x",
        "key_columns": [],
        "default_query": "SELECT 1 AS n",
    }
    base.update(overrides)
    m = MagicMock()
    for k, v in base.items():
        setattr(m, k, v)
    return m


@pytest.mark.asyncio
async def test_query_dataset_runs_default_query():
    """罐装 dataset 端点:跑 dataset.default_query,返回行 + label。"""
    sid = uuid4()
    ds = _fake_ds(id=sid)
    dataset = _fake_dataset(source_id=sid, id=uuid4(), label="投标总览")
    with (
        patch(
            "app.extensions.data_source.routers.DataSourceService.get_by_id",
            AsyncMock(return_value=ds),
        ),
        patch(
            "app.extensions.data_source.routers.DataSourceService.get_dataset",
            AsyncMock(return_value=dataset),
        ),
        patch(
            "app.extensions.data_source.routers.DataSourceService.run_readonly_query",
            AsyncMock(return_value=[{"n": 1}]),
        ),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/extensions/data-sources/{sid}/datasets/{dataset.id}/query")
    assert resp.status_code == 200
    assert resp.json() == {"rows": [{"n": 1}], "row_count": 1, "label": "投标总览"}


@pytest.mark.asyncio
async def test_query_dataset_404_when_source_missing():
    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_id",
        AsyncMock(return_value=None),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/extensions/data-sources/{uuid4()}/datasets/{uuid4()}/query")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_query_sql_rejects_write():
    """raw-SQL 端点:DELETE 被 assert_readonly_select 拒 → 400。"""
    sid = uuid4()
    ds = _fake_ds(id=sid)
    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_id",
        AsyncMock(return_value=ds),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/extensions/data-sources/{sid}/query",
                json={"sql": "DELETE FROM mock_bid"},
            )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_query_sql_runs_readonly_select():
    """raw-SQL 端点:合法 SELECT 跑通,返回行(label=None)。"""
    sid = uuid4()
    ds = _fake_ds(id=sid)
    with (
        patch(
            "app.extensions.data_source.routers.DataSourceService.get_by_id",
            AsyncMock(return_value=ds),
        ),
        patch(
            "app.extensions.data_source.routers.DataSourceService.run_readonly_query",
            AsyncMock(return_value=[{"k": 7}]),
        ),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/extensions/data-sources/{sid}/query",
                json={"sql": "SELECT 7 AS k"},
            )
    assert resp.status_code == 200
    assert resp.json() == {"rows": [{"k": 7}], "row_count": 1, "label": None}
