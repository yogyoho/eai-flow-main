"""Router-level tests for data_source endpoints. Service layer is mocked."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.extensions.data_source.routers import router


def _fake_ds(**overrides):
    """A complete fake DataSource with every DataSourceResponse field populated."""
    base = {
        "id": str(uuid4()),
        "name": "prod",
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
    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_name",
        AsyncMock(return_value=None),
    ), patch(
        "app.extensions.data_source.routers.DataSourceService.create",
        AsyncMock(return_value=_fake_ds(name="n")),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/extensions/data-sources",
                json={"name": "n", "type": "api", "connection_config": {}},
            )
    assert resp.status_code == 201
    assert resp.json()["name"] == "n"


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

    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_id",
        AsyncMock(return_value=_fake_ds()),
    ), patch(
        "app.extensions.data_source.routers.DataSourceService.test_connection",
        AsyncMock(return_value=TestConnectionResult(success=True, message="ok")),
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
    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_id",
        AsyncMock(return_value=_fake_ds()),
    ), patch(
        "app.extensions.data_source.routers.DataSourceService.sync",
        AsyncMock(
            return_value={
                "status": "connected",
                "last_sync_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "metadata": {"k": 1},
            }
        ),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/extensions/data-sources/{uuid4()}/sync")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "connected"
    assert body["metadata"] == {"k": 1}
