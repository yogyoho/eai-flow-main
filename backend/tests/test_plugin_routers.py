"""Router-level tests for plugin endpoints. Service layer is mocked."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.extensions.plugin import routers as plugin_routers
from app.extensions.plugin.routers import router


def _fake_plugin(**ov):
    base = {
        "id": str(uuid4()), "name": "CAD 文件预览", "type": "tool", "version": "1.0.0",
        "author": None, "description": None, "config_schema": None, "entry_point": None,
        "icon": None, "permissions": [], "status": "registered",
        "created_at": datetime(2026, 1, 1), "updated_at": datetime(2026, 1, 1),
    }
    base.update(ov)
    m = MagicMock()
    for k, v in base.items():
        setattr(m, k, v)
    return m


def _fake_instance(**ov):
    base = {
        "id": str(uuid4()), "plugin_id": str(uuid4()), "plugin_name": "CAD 文件预览",
        "plugin_type": "tool", "project_id": None, "config": {}, "status": "active",
        "last_sync_at": None, "created_at": datetime(2026, 1, 1),
    }
    base.update(ov)
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
async def test_list_registry():
    with patch.object(plugin_routers.PluginService, "list_plugins",
                      AsyncMock(return_value=[_fake_plugin(name="CAD 文件预览")])):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/extensions/plugins/registry")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["name"] == "CAD 文件预览"


@pytest.mark.asyncio
async def test_install_instance_201():
    with patch.object(plugin_routers.PluginService, "create_instance", AsyncMock(return_value=_fake_instance())):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/extensions/plugins/instances",
                                     json={"plugin_id": str(uuid4()), "config": {}})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_install_instance_400_on_invalid_config():
    from jsonschema import ValidationError

    with patch.object(plugin_routers.PluginService, "validate_config",
                      MagicMock(side_effect=ValidationError("bad"))):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/extensions/plugins/instances",
                                     json={"plugin_id": str(uuid4()), "config": {}})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_instance_toggle():
    with patch.object(plugin_routers.PluginService, "update_instance",
                      AsyncMock(return_value=_fake_instance(status="disabled"))):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(f"/api/extensions/plugins/instances/{uuid4()}",
                                      json={"status": "disabled"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"


@pytest.mark.asyncio
async def test_delete_instance_204():
    with patch.object(plugin_routers.PluginService, "delete_instance", AsyncMock(return_value=True)):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/api/extensions/plugins/instances/{uuid4()}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_create_api_key_returns_plaintext_once():
    fake_rec = MagicMock()
    fake_rec.id = str(uuid4())
    with patch.object(plugin_routers.PluginService, "create_api_key",
                      AsyncMock(return_value=(fake_rec, "PLAINTEXT_KEY_123"))):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/extensions/plugins/api-keys",
                                     json={"name": "ci", "scope": []})
    assert resp.status_code == 201
    body = resp.json()
    assert body["key"] == "PLAINTEXT_KEY_123"
    assert "id" in body


@pytest.mark.asyncio
async def test_list_api_keys_no_plaintext():
    fake_key = MagicMock()
    fake_key.id = str(uuid4())
    fake_key.name = "ci"
    fake_key.key_prefix = "abcd1234"
    fake_key.scope = []
    fake_key.project_id = None
    fake_key.created_by = None
    fake_key.expires_at = None
    fake_key.last_used_at = None
    fake_key.created_at = datetime(2026, 1, 1)
    with patch.object(plugin_routers.PluginService, "list_api_keys", AsyncMock(return_value=[fake_key])):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/extensions/plugins/api-keys")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["key_prefix"] == "abcd1234"
    assert "key" not in item and "key_hash" not in item


@pytest.mark.asyncio
async def test_revoke_api_key_204():
    with patch.object(plugin_routers.PluginService, "delete_api_key", AsyncMock(return_value=True)):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/api/extensions/plugins/api-keys/{uuid4()}")
    assert resp.status_code == 204
