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
