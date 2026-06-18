"""Tests for the plugin backend models."""

from app.extensions.models import ApiKey, Plugin, PluginInstance


class TestPluginModel:
    def test_defaults(self):
        p = Plugin(name="CAD预览", type="tool")
        assert p.name == "CAD预览"
        assert p.type == "tool"
        assert p.version == "1.0.0"
        assert p.status == "registered"
        assert p.permissions == []
        assert p.config_schema is None
        assert p.entry_point is None

    def test_tablenames(self):
        assert Plugin.__tablename__ == "plugins"
        assert PluginInstance.__tablename__ == "plugin_instances"
        assert ApiKey.__tablename__ == "plugin_api_keys"


class TestPluginInstanceModel:
    def test_defaults(self):
        inst = PluginInstance(plugin_id=None, plugin_name="x", plugin_type="tool")
        assert inst.plugin_name == "x"
        assert inst.status == "disabled"
        assert inst.config == {}
        assert inst.project_id is None


class TestApiKeyModel:
    def test_defaults(self):
        k = ApiKey(name="ci", key_prefix="abcd1234", key_hash="0" * 64)
        assert k.name == "ci"
        assert k.key_prefix == "abcd1234"
        assert k.scope == []
        assert k.expires_at is None
