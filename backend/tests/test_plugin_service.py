"""Tests for plugin schemas + service logic."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.extensions.plugin.schemas import (
    ApiKeyCreate,
    ApiKeyResponse,
    PluginInstanceCreate,
    PluginInstanceUpdate,
    PluginResponse,
)


class TestSchemas:
    def test_plugin_instance_create_minimal(self):
        r = PluginInstanceCreate(plugin_id=str(uuid4()))
        assert r.config == {}
        assert r.project_id is None

    def test_plugin_instance_update_partial(self):
        r = PluginInstanceUpdate(status="active")
        assert r.status == "active"
        assert r.config is None

    def test_api_key_create_requires_name(self):
        with pytest.raises(ValidationError):
            ApiKeyCreate(name="", scope=[])

    def test_plugin_response_from_attributes(self):
        class _Fake:
            id = "p1"
            name = "CAD预览"
            type = "tool"
            version = "1.0.0"
            author = None
            description = None
            config_schema = None
            entry_point = None
            icon = None
            permissions = []
            status = "registered"
            created_at = None
            updated_at = None

        resp = PluginResponse.model_validate(_Fake())
        assert resp.name == "CAD预览"

    def test_api_key_response_has_no_plaintext_field(self):
        # ApiKeyResponse must NOT expose key/key_hash — only prefix
        fields = set(ApiKeyResponse.model_fields.keys())
        assert "key" not in fields
        assert "key_hash" not in fields
        assert "key_prefix" in fields


from unittest.mock import AsyncMock, MagicMock, patch

from app.extensions.plugin.service import PluginService


def _plugin(config_schema=None):
    m = MagicMock()
    m.config_schema = config_schema
    m.name = "CAD预览"
    m.type = "tool"
    m.version = "1.0.0"
    m.id = "pid"
    return m


class TestValidateConfig:
    def test_no_schema_passes(self):
        PluginService.validate_config(_plugin(config_schema=None), {"anything": 1})  # no raise

    def test_valid_config_passes(self):
        schema = {"type": "object", "properties": {"host": {"type": "string"}}, "required": ["host"]}
        PluginService.validate_config(_plugin(config_schema=schema), {"host": "localhost"})

    def test_invalid_config_raises(self):
        from jsonschema import ValidationError

        schema = {"type": "object", "required": ["host"]}
        with pytest.raises(ValidationError):
            PluginService.validate_config(_plugin(config_schema=schema), {})


class TestApiKeyHashing:
    @pytest.mark.asyncio
    async def test_create_returns_plaintext_and_stores_hash(self):
        import hashlib

        db = AsyncMock()
        added = []

        async def _add(obj):
            added.append(obj)

        async def _flush():
            for o in added:
                o.id = "k1"

        db.add = AsyncMock(side_effect=_add)
        db.flush = AsyncMock(side_effect=_flush)
        req = MagicMock()
        req.name = "ci"
        req.scope = []
        req.project_id = None
        req.expires_at = None
        with patch("app.extensions.plugin.service.secrets.token_urlsafe", return_value="ABCDEFGH12345678"):
            rec, raw = await PluginService.create_api_key(db, req, user_id=None)
        assert raw == "ABCDEFGH12345678"  # plaintext returned once
        assert rec.key_prefix == "ABCDEFGH"  # first 8 chars
        assert rec.key_hash == hashlib.sha256(b"ABCDEFGH12345678").hexdigest()
        assert rec.key_hash != raw  # hash, not plaintext, stored


class TestInstanceCrud:
    @pytest.mark.asyncio
    async def test_create_denormalizes_name_type_and_sets_active(self):
        db = AsyncMock()
        added = []

        async def _add(obj):
            added.append(obj)

        async def _flush():
            for o in added:
                o.id = "iid"

        db.add = AsyncMock(side_effect=_add)
        db.flush = AsyncMock(side_effect=_flush)
        plugin = _plugin()
        req = MagicMock()
        req.plugin_id = "pid"
        req.config = {}
        with patch.object(PluginService, "get_plugin", AsyncMock(return_value=plugin)), patch.object(
            PluginService, "validate_config", MagicMock(return_value=None)
        ):
            inst = await PluginService.create_instance(db, req, user_id=None)
        assert inst.plugin_name == "CAD预览"
        assert inst.plugin_type == "tool"
        assert inst.status == "active"
        assert added, "instance should be added to session"

    @pytest.mark.asyncio
    async def test_create_404_when_plugin_missing(self):
        db = AsyncMock()
        req = MagicMock()
        req.plugin_id = "nope"
        req.config = {}
        with patch.object(PluginService, "get_plugin", AsyncMock(return_value=None)):
            with pytest.raises(ValueError):
                await PluginService.create_instance(db, req, user_id=None)
