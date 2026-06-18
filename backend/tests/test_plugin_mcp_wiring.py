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
