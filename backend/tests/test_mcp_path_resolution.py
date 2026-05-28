"""Tests for MCP server path resolution (container paths -> local paths)."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig
from deerflow.mcp.client import build_server_params, build_servers_config

# Force _get_project_root to return a stable local path so tests behave
# identically whether running on the host (D:/eai/...) or inside the
# Docker container (/app/).
_MOCK_PROJECT_ROOT = Path("/home/user/myproject")


# ---------------------------------------------------------------------------
# resolve_container_path — unit-level tests
# ---------------------------------------------------------------------------


class TestResolveContainerPath:
    """Test the resolve_container_path utility function."""

    def test_container_path_resolved_to_project_root(self):
        from deerflow.mcp.client import resolve_container_path

        project_root = Path("/home/user/myproject")
        result = resolve_container_path("/app/mcp-server/word/server.py", project_root)
        expected = str(project_root / "mcp-server/word/server.py")
        assert result == expected

    def test_container_path_preserves_subdirs(self):
        from deerflow.mcp.client import resolve_container_path

        project_root = Path("D:/eai/eai-flow-main")
        result = resolve_container_path("/app/mcp-server/Office-Word-MCP-Server/word_mcp_server.py", project_root)
        expected = str(project_root / "mcp-server/Office-Word-MCP-Server/word_mcp_server.py")
        assert result == expected

    def test_non_container_absolute_path_unchanged(self):
        from deerflow.mcp.client import resolve_container_path

        project_root = Path("/home/user/myproject")
        linux_path = "/usr/bin/python"
        assert resolve_container_path(linux_path, project_root) == linux_path

    def test_relative_path_unchanged(self):
        from deerflow.mcp.client import resolve_container_path

        project_root = Path("/home/user/myproject")
        relative = "mcp-server/word/server.py"
        assert resolve_container_path(relative, project_root) == relative

    def test_plain_command_unchanged(self):
        from deerflow.mcp.client import resolve_container_path

        project_root = Path("/home/user/myproject")
        assert resolve_container_path("python", project_root) == "python"
        assert resolve_container_path("npx", project_root) == "npx"

    def test_empty_string_unchanged(self):
        from deerflow.mcp.client import resolve_container_path

        project_root = Path("/home/user/myproject")
        assert resolve_container_path("", project_root) == ""

    def test_windows_project_root_with_container_path(self):
        from deerflow.mcp.client import resolve_container_path

        project_root = Path("D:/eai/eai-flow-main")
        result = resolve_container_path("/app/mcp-server/Office-Word-MCP-Server", project_root)
        expected = str(project_root / "mcp-server/Office-Word-MCP-Server")
        assert result == expected


# ---------------------------------------------------------------------------
# Integration: build_server_params with path resolution
# ---------------------------------------------------------------------------


class TestBuildServerParamsPathResolution:
    """Test that build_server_params resolves container paths."""

    @patch("deerflow.mcp.client._get_project_root", return_value=_MOCK_PROJECT_ROOT)
    def test_stdio_args_resolved(self, _mock_root):
        config = McpServerConfig(
            type="stdio",
            command="python",
            args=["/app/mcp-server/Office-Word-MCP-Server/word_mcp_server.py"],
            env={"PYTHONPATH": "/app/mcp-server/Office-Word-MCP-Server"},
        )

        params = build_server_params("word-server", config)

        # Args should be resolved to local project paths (use Path for cross-platform check)
        resolved_arg = Path(params["args"][0])
        assert resolved_arg.parts[-3:] == ("mcp-server", "Office-Word-MCP-Server", "word_mcp_server.py")
        assert not params["args"][0].startswith("/app/")

        # Env PYTHONPATH should also be resolved
        pythonpath = params["env"]["PYTHONPATH"]
        resolved_pythonpath = Path(pythonpath)
        assert resolved_pythonpath.parts[-2:] == ("mcp-server", "Office-Word-MCP-Server")
        assert not pythonpath.startswith("/app/")

    def test_stdio_command_npx_unchanged(self):
        """Non-container commands like 'npx' should remain unchanged."""
        config = McpServerConfig(
            type="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/path/to/files"],
            env={},
        )

        params = build_server_params("filesystem", config)

        assert params["command"] == "npx"
        # The third arg is a non-/app/ absolute path, should be unchanged
        assert params["args"][2] == "/path/to/files"

    def test_stdio_command_python_unchanged(self):
        """Plain 'python' command should remain unchanged."""
        config = McpServerConfig(
            type="stdio",
            command="python",
            args=["some_script.py"],
            env={},
        )

        params = build_server_params("test-server", config)
        assert params["command"] == "python"

    def test_env_with_non_path_values_unchanged(self):
        """Env vars that are not paths should remain unchanged."""
        config = McpServerConfig(
            type="stdio",
            command="npx",
            args=["server"],
            env={"API_KEY": "secret123", "DEBUG": "true"},
        )

        params = build_server_params("test-server", config)
        assert params["env"]["API_KEY"] == "secret123"
        assert params["env"]["DEBUG"] == "true"

    @patch("deerflow.mcp.client._get_project_root", return_value=_MOCK_PROJECT_ROOT)
    def test_multiple_env_vars_with_container_paths(self, _mock_root):
        """Multiple env vars with container paths should all be resolved."""
        config = McpServerConfig(
            type="stdio",
            command="python",
            args=["/app/scripts/run.py"],
            env={
                "PYTHONPATH": "/app/libs",
                "CONFIG_PATH": "/app/config/settings.yaml",
                "API_KEY": "key123",
            },
        )

        params = build_server_params("multi-env-server", config)

        assert not params["env"]["PYTHONPATH"].startswith("/app/")
        assert not params["env"]["CONFIG_PATH"].startswith("/app/")
        assert params["env"]["API_KEY"] == "key123"

    def test_http_transport_no_path_resolution(self):
        """HTTP/SSE transport should not have path resolution applied."""
        config = McpServerConfig(
            type="http",
            url="https://example.com/mcp",
            headers={"Authorization": "Bearer token"},
        )

        params = build_server_params("remote", config)
        assert params["url"] == "https://example.com/mcp"
        assert "command" not in params
        assert "args" not in params


# ---------------------------------------------------------------------------
# Integration: build_servers_config end-to-end
# ---------------------------------------------------------------------------


class TestBuildServersConfigPathResolution:
    """End-to-end test for build_servers_config with container paths."""

    @patch("deerflow.mcp.client._get_project_root", return_value=_MOCK_PROJECT_ROOT)
    def test_mixed_servers_container_paths_resolved(self, _mock_root):
        """Config with mixed container/normal paths should resolve correctly."""
        extensions = ExtensionsConfig(
            mcp_servers={
                "word-server": McpServerConfig(
                    enabled=True,
                    type="stdio",
                    command="python",
                    args=["/app/mcp-server/Office-Word-MCP-Server/word_mcp_server.py"],
                    env={"PYTHONPATH": "/app/mcp-server/Office-Word-MCP-Server"},
                ),
                "filesystem": McpServerConfig(
                    enabled=True,
                    type="stdio",
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem", "/path/to/files"],
                    env={},
                ),
                "disabled-server": McpServerConfig(
                    enabled=False,
                    type="stdio",
                    command="python",
                    args=["/app/disabled/server.py"],
                ),
            },
            skills={},
        )

        result = build_servers_config(extensions)

        # word-server: paths resolved
        assert "word-server" in result
        word_params = result["word-server"]
        assert not word_params["args"][0].startswith("/app/")
        assert not word_params["env"]["PYTHONPATH"].startswith("/app/")

        # filesystem: paths unchanged
        assert "filesystem" in result
        assert result["filesystem"]["args"][2] == "/path/to/files"

        # disabled: not included
        assert "disabled-server" not in result


# ---------------------------------------------------------------------------
# cwd parameter tests
# ---------------------------------------------------------------------------


class TestCwdParameter:
    """Test that the cwd parameter is correctly passed through build_server_params."""

    @patch("deerflow.mcp.client._get_project_root", return_value=_MOCK_PROJECT_ROOT)
    def test_stdio_cwd_resolved(self, _mock_root):
        """Container-style cwd should be resolved to local project path."""
        config = McpServerConfig(
            type="stdio",
            command="python",
            args=["/app/mcp-server/word/server.py"],
            cwd="/app/mcp-server/word",
        )

        params = build_server_params("word-server", config)

        assert "cwd" in params
        resolved_cwd = Path(params["cwd"])
        assert resolved_cwd.parts[-2:] == ("mcp-server", "word")
        assert not params["cwd"].startswith("/app/")

    def test_stdio_cwd_none_not_included(self):
        """When cwd is None, it should not appear in params."""
        config = McpServerConfig(
            type="stdio",
            command="python",
            args=["server.py"],
        )

        params = build_server_params("test-server", config)

        assert "cwd" not in params

    def test_stdio_cwd_relative_path(self):
        """Relative cwd should pass through unchanged."""
        config = McpServerConfig(
            type="stdio",
            command="python",
            args=["server.py"],
            cwd="./workspace",
        )

        params = build_server_params("test-server", config)

        assert params["cwd"] == "./workspace"

    @patch("deerflow.mcp.client._get_project_root", return_value=_MOCK_PROJECT_ROOT)
    def test_stdio_cwd_absolute_non_container(self, _mock_root):
        """Absolute non-container cwd (e.g. /tmp) should pass through unchanged."""
        config = McpServerConfig(
            type="stdio",
            command="python",
            args=["server.py"],
            cwd="/tmp/mcp-workspace",
        )

        params = build_server_params("test-server", config)

        assert params["cwd"] == "/tmp/mcp-workspace"
