"""MCP client using langchain-mcp-adapters."""

import logging
from pathlib import Path
from typing import Any

from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig

logger = logging.getLogger(__name__)

# Docker container mount prefix — /app/ is the default WORKDIR in Docker images
_CONTAINER_PREFIX = "/app/"


def _get_project_root() -> Path:
    """Resolve project root from this module's location.

    This file is at: packages/harness/deerflow/mcp/client.py
    parents[4] = backend/; parent = repo root.
    """
    backend_dir = Path(__file__).resolve().parents[4]
    return backend_dir.parent


def resolve_container_path(path: str, project_root: Path) -> str:
    """Resolve Docker container-style absolute paths to local filesystem paths.

    Paths starting with ``/app/`` are treated as relative to *project_root*.
    All other paths pass through unchanged.

    Args:
        path: The path string to resolve.
        project_root: Local project root directory.

    Returns:
        Resolved local path if it was a container path, otherwise unchanged.
    """
    if path.startswith(_CONTAINER_PREFIX):
        relative = path[len(_CONTAINER_PREFIX) :]
        return str(project_root / relative)
    return path


def build_server_params(server_name: str, config: McpServerConfig) -> dict[str, Any]:
    """Build server parameters for MultiServerMCPClient.

    Args:
        server_name: Name of the MCP server.
        config: Configuration for the MCP server.

    Returns:
        Dictionary of server parameters for langchain-mcp-adapters.
    """
    transport_type = config.type or "stdio"
    params: dict[str, Any] = {"transport": transport_type}

    if transport_type == "stdio":
        if not config.command:
            raise ValueError(f"MCP server '{server_name}' with stdio transport requires 'command' field")

        project_root = _get_project_root()
        params["command"] = resolve_container_path(config.command, project_root)
        params["args"] = [resolve_container_path(a, project_root) for a in config.args]
        if config.env:
            params["env"] = {k: resolve_container_path(v, project_root) for k, v in config.env.items()}
        if config.cwd:
            params["cwd"] = resolve_container_path(config.cwd, project_root)
    elif transport_type in ("sse", "http"):
        if not config.url:
            raise ValueError(f"MCP server '{server_name}' with {transport_type} transport requires 'url' field")
        params["url"] = config.url
        # Add headers if present
        if config.headers:
            params["headers"] = config.headers
    else:
        raise ValueError(f"MCP server '{server_name}' has unsupported transport type: {transport_type}")

    return params


def build_servers_config(extensions_config: ExtensionsConfig) -> dict[str, dict[str, Any]]:
    """Build servers configuration for MultiServerMCPClient.

    Args:
        extensions_config: Extensions configuration containing all MCP servers.

    Returns:
        Dictionary mapping server names to their parameters.
    """
    enabled_servers = extensions_config.get_enabled_mcp_servers()

    if not enabled_servers:
        logger.info("No enabled MCP servers found")
        return {}

    servers_config = {}
    for server_name, server_config in enabled_servers.items():
        try:
            servers_config[server_name] = build_server_params(server_name, server_config)
            logger.info(f"Configured MCP server: {server_name}")
        except Exception as e:
            logger.error(f"Failed to configure MCP server '{server_name}': {e}")

    return servers_config
