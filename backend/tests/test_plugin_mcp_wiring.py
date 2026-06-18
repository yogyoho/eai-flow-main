"""Tests for plugin→MCP wiring (sync_mcp_registration) + demo module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.extensions.plugin.service import PluginService


def _plugin(type_="tool", entry="app.extensions.plugin.builtin.demo_mcp"):
    m = MagicMock()
    m.id = "pid"
    m.name = "示例工具"
    m.type = type_
    m.entry_point = entry
    m.description = "演示"
    return m


def _instance(status="active", config=None):
    m = MagicMock()
    m.id = "iid"
    m.status = status
    m.config = config if config is not None else {}
    return m


def _write_cfg(tmp_path, servers=None):
    cfg = tmp_path / "extensions_config.json"
    cfg.write_text(json.dumps({"mcpServers": servers or {}}), encoding="utf-8")
    return cfg


class TestSyncMcpRegistration:
    def test_active_tool_writes_entry(self, tmp_path):
        cfg = _write_cfg(tmp_path)
        with patch("app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=cfg), patch(
            "app.extensions.plugin.service.reload_extensions_config"
        ):
            PluginService.sync_mcp_registration(_instance(), _plugin())
        data = json.loads(cfg.read_text(encoding="utf-8"))
        entry = data["mcpServers"]["plugin_pid"]
        assert entry["enabled"] is True
        assert entry["args"] == ["-m", "app.extensions.plugin.builtin.demo_mcp"]
        assert entry["command"] == "/app/backend/.venv/bin/python"
        assert entry["cwd"] == "/app/backend"

    def test_inactive_removes_entry(self, tmp_path):
        cfg = _write_cfg(tmp_path, {"plugin_pid": {"enabled": True}})
        with patch("app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=cfg), patch(
            "app.extensions.plugin.service.reload_extensions_config"
        ):
            PluginService.sync_mcp_registration(_instance(status="disabled"), _plugin())
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert "plugin_pid" not in data["mcpServers"]

    def test_force_remove_even_if_active(self, tmp_path):
        cfg = _write_cfg(tmp_path, {"plugin_pid": {"enabled": True}})
        with patch("app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=cfg), patch(
            "app.extensions.plugin.service.reload_extensions_config"
        ):
            PluginService.sync_mcp_registration(_instance(status="active"), _plugin(), remove=True)
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert "plugin_pid" not in data["mcpServers"]

    def test_non_tool_type_not_registered(self, tmp_path):
        cfg = _write_cfg(tmp_path)
        with patch("app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=cfg), patch(
            "app.extensions.plugin.service.reload_extensions_config"
        ):
            PluginService.sync_mcp_registration(_instance(), _plugin(type_="data_connector"))
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert "plugin_pid" not in data["mcpServers"]

    def test_idempotent_double_register(self, tmp_path):
        cfg = _write_cfg(tmp_path)
        for _ in range(2):
            with patch("app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=cfg), patch(
                "app.extensions.plugin.service.reload_extensions_config"
            ):
                PluginService.sync_mcp_registration(_instance(), _plugin())
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert list(data["mcpServers"].keys()).count("plugin_pid") == 1

    def test_write_failure_does_not_raise(self, tmp_path):
        cfg = _write_cfg(tmp_path)
        with patch("app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=cfg), patch(
            "app.extensions.plugin.service.reload_extensions_config"
        ), patch("builtins.open", side_effect=OSError("disk full")):
            PluginService.sync_mcp_registration(_instance(), _plugin())  # no raise


class TestHooksCallSync:
    @pytest.mark.asyncio
    async def test_create_instance_calls_sync(self):
        db = AsyncMock()
        db.add = MagicMock()  # AsyncSession.add is sync
        db.flush = AsyncMock()
        plugin = _plugin()
        req = MagicMock()
        req.plugin_id = "pid"
        req.config = {}
        with patch.object(PluginService, "get_plugin", AsyncMock(return_value=plugin)), patch.object(
            PluginService, "validate_config", MagicMock(return_value=None)
        ), patch.object(PluginService, "sync_mcp_registration") as sync, patch.object(
            PluginService, "sync_skill_registration"
        ), patch.object(
            PluginService, "sync_data_source_registration", AsyncMock()
        ):
            await PluginService.create_instance(db, req, user_id=None)
        sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_instance_calls_sync_remove(self):
        db = AsyncMock()
        inst = _instance()
        plugin = _plugin()
        db.get = AsyncMock(return_value=inst)
        db.delete = AsyncMock()
        db.flush = AsyncMock()
        with patch.object(PluginService, "get_plugin", AsyncMock(return_value=plugin)), patch.object(
            PluginService, "sync_mcp_registration"
        ) as sync, patch.object(PluginService, "sync_skill_registration"), patch.object(
            PluginService, "sync_data_source_registration", AsyncMock()
        ):
            await PluginService.delete_instance(db, "iid")
        sync.assert_called_once()
        assert sync.call_args.kwargs.get("remove") is True


class TestSyncDataSourceRegistration:
    @pytest.mark.asyncio
    async def test_active_data_connector_creates_datasource(self):
        db = AsyncMock()
        rm = MagicMock()
        rm.scalars.return_value.first.return_value = None  # no existing DataSource
        db.execute = AsyncMock(return_value=rm)
        db.add = MagicMock()
        db.flush = AsyncMock()
        plugin = _plugin(type_="data_connector", entry="database")
        plugin.name = "地质数据连接器"
        plugin.description = "对接地质钻孔库"
        inst = _instance(status="active")
        inst.config = {"host": "h", "port": 5432}
        await PluginService.sync_data_source_registration(db, inst, plugin)
        assert db.add.called  # DataSource created

    @pytest.mark.asyncio
    async def test_inactive_removes_existing(self):
        db = AsyncMock()
        existing = MagicMock()
        rm = MagicMock()
        rm.scalars.return_value.first.return_value = existing
        db.execute = AsyncMock(return_value=rm)
        db.delete = AsyncMock()
        db.flush = AsyncMock()
        plugin = _plugin(type_="data_connector", entry="database")
        await PluginService.sync_data_source_registration(db, _instance(status="disabled"), plugin)
        db.delete.assert_called_once_with(existing)

    @pytest.mark.asyncio
    async def test_non_data_connector_no_op(self):
        db = AsyncMock()
        rm = MagicMock()
        rm.scalars.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=rm)
        db.add = MagicMock()
        plugin = _plugin(type_="tool", entry="app.x.mcp")  # tool, not data_connector
        await PluginService.sync_data_source_registration(db, _instance(), plugin)
        assert not db.add.called


class TestSyncSkillRegistration:
    def test_active_output_writes_skill_md(self, tmp_path):
        fake_config = MagicMock()
        fake_config.skills.path = str(tmp_path)
        with patch("deerflow.config.get_app_config", return_value=fake_config), patch(
            "app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=None
        ):
            PluginService.sync_skill_registration(_instance(), _plugin(type_="output"))
        skill_file = tmp_path / "custom" / "plugin-pid" / "SKILL.md"
        assert skill_file.exists()
        content = skill_file.read_text(encoding="utf-8")
        assert "name: plugin-pid" in content
        assert "示例工具" in content

    def test_non_output_no_skill_written(self, tmp_path):
        fake_config = MagicMock()
        fake_config.skills.path = str(tmp_path)
        with patch("deerflow.config.get_app_config", return_value=fake_config), patch(
            "app.extensions.plugin.service.ExtensionsConfig.resolve_config_path", return_value=None
        ):
            PluginService.sync_skill_registration(_instance(), _plugin(type_="tool"))
        skill_file = tmp_path / "custom" / "plugin-pid" / "SKILL.md"
        assert not skill_file.exists()


class TestDemoModule:
    def test_demo_module_exposes_greet(self):
        from app.extensions.plugin.builtin import demo_mcp

        names = {t.name for t in demo_mcp.TOOLS}
        assert "demo_greet" in names

    def test_seed_includes_demo_plugin(self):
        from app.extensions.plugin import seed as seed_mod

        demo = [p for p in seed_mod.BUILTIN_PLUGINS if p["name"].startswith("示例工具")]
        assert demo and demo[0]["type"] == "tool"
        assert demo[0]["entry_point"] == "app.extensions.plugin.builtin.demo_mcp"
