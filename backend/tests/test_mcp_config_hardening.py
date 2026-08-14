"""Tests for MCP config endpoint hardening (upstream #3425, dev-adapted).

Covers the stdio command allowlist + input validation added to
``app.gateway.routers.mcp``. The admin-only check (``_require_admin_user``)
is exercised too. These are the security pieces NOT already present in dev
(masking / cross-site / symlink / docs-toggle were already in place).

The upstream ``test_mcp_config_secrets.py`` imports endpoints dev does not
expose (e.g. ``reset_mcp_tools_cache_endpoint``), so this focused suite
replaces it for the hardening logic.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.gateway.deps import require_admin_user
from app.gateway.routers.mcp import (
    McpConfigUpdateRequest,
    McpServerConfigResponse,
    _allowed_stdio_commands,
    _stdio_command_name,
    _validate_mcp_update_request,
)


def _server(command=None, transport="stdio") -> McpServerConfigResponse:
    return McpServerConfigResponse(command=command, type=transport)


# --- _stdio_command_name -----------------------------------------------------

@pytest.mark.parametrize("good", ["npx", "uvx", "python"])
def test_stdio_command_name_accepts_plain_executable(good):
    assert _stdio_command_name(good, server_name="s") == good


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_stdio_command_name_rejects_empty(bad):
    with pytest.raises(HTTPException) as exc:
        _stdio_command_name(bad, server_name="s")
    assert exc.value.status_code == 400


@pytest.mark.parametrize("bad", ["npx -y", "/usr/bin/npx", "./run", "npx;x", "npx|x", "npx&&x", "npx`x", "npx\nx"])
def test_stdio_command_name_rejects_paths_spaces_metachars(bad):
    with pytest.raises(HTTPException) as exc:
        _stdio_command_name(bad, server_name="s")
    assert exc.value.status_code == 400


# --- _allowed_stdio_commands -------------------------------------------------

def test_allowed_stdio_commands_default_includes_npx_uvx():
    cmds = _allowed_stdio_commands()
    assert {"npx", "uvx"} <= cmds


def test_allowed_stdio_commands_extends_via_env(monkeypatch):
    monkeypatch.setenv("DEER_FLOW_MCP_STDIO_COMMAND_ALLOWLIST", "python, node ,docker")
    cmds = _allowed_stdio_commands()
    assert {"npx", "uvx", "python", "node", "docker"} <= cmds


# --- _validate_mcp_update_request -------------------------------------------

def test_validate_allows_allowlisted_command():
    req = McpConfigUpdateRequest(mcp_servers={"gh": _server("npx")})
    _validate_mcp_update_request(req)  # no raise


def test_validate_rejects_disallowed_command():
    req = McpConfigUpdateRequest(mcp_servers={"bad": _server("curl")})
    with pytest.raises(HTTPException) as exc:
        _validate_mcp_update_request(req)
    assert exc.value.status_code == 400


def test_validate_skips_non_stdio_transport():
    # http/sse transports are not subject to the stdio command allowlist.
    req = McpConfigUpdateRequest(mcp_servers={"api": _server(command=None, transport="http")})
    _validate_mcp_update_request(req)  # no raise


# --- require_admin_user ------------------------------------------------------
# EAI-CUSTOM: the actual admin gate is `require_admin_user` from app.gateway.deps
# (mcp.py calls it on every config-mutating route); the old `_require_admin_user`
# name never existed. Fixed 2026-08-15 to test the real gate.

def _request_with_user(system_role):
    request = MagicMock()
    request.state.user = SimpleNamespace(system_role=system_role)
    return request


def test_require_admin_user_allows_admin():
    asyncio.run(require_admin_user(_request_with_user("admin"), detail="x"))  # no raise


def test_require_admin_user_rejects_regular_user():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_admin_user(_request_with_user("user"), detail="x"))
    assert exc.value.status_code == 403


def test_require_admin_user_rejects_internal_channel_user():
    # IM-channel internal auth must NOT manage MCP config (admin-only).
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_admin_user(_request_with_user("internal"), detail="x"))
    assert exc.value.status_code == 403
