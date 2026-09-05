"""MCP client using langchain-mcp-adapters.

EAI-CUSTOM: 本文件含对上游 deer-flow 的定制增强——build_server_params 透传 stdio MCP 的 cwd
（bug-712，2026-08-02）。所有 EAI 改动以 `# ── EAI-CUSTOM START/END ──` 包裹，升级/差分时按此识别。
"""

import logging
from typing import Any

from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig
from deerflow.mcp.headers import illegal_header_value_reason

logger = logging.getLogger(__name__)


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
        params["command"] = config.command
        params["args"] = config.args
        # Add environment variables if present
        if config.env:
            params["env"] = config.env
        # ── EAI-CUSTOM START ──────────────────────────────────────────────────
        # 上游 deer-flow 的 build_server_params 不透传 McpServerConfig 的 cwd(extra 字段)。
        # 后果：stdio MCP 子进程默认继承 gateway 进程 cwd，`python -m app.extensions.*`
        # 找不到 `app` 包（ModuleNotFoundError），导致 session.initialize() 抛
        # McpError: Connection closed。影响所有 stdio MCP(project/data_sources/contract-price)。
        # 参考：bug-712（2026-08-02）。extensions_config.json 的 stdio server 须配
        # `"cwd": "/app/backend"` 才能 import app 包。
        # 升级注意：若上游补上 cwd 透传，删去本段（EAI-CUSTOM END 以内）。
        cwd = getattr(config, "cwd", None)
        if cwd:
            params["cwd"] = cwd
        # ── EAI-CUSTOM END ────────────────────────────────────────────────────
    elif transport_type in ("sse", "http"):
        if not config.url:
            raise ValueError(f"MCP server '{server_name}' with {transport_type} transport requires 'url' field")
        params["url"] = config.url
        # Add headers if present
        if config.headers:
            # A statically configured value the transport would refuse gets the
            # same treatment as a request-scoped one: h11 renders the full
            # value into its exception on a line break or surrounding
            # whitespace, which reaches the model through
            # ToolErrorHandlingMiddleware. These values are API keys often
            # enough to be worth refusing here, where build_servers_config
            # already drops just this server and logs the reason.
            for header_name, header_value in config.headers.items():
                reason = illegal_header_value_reason(header_value)
                if reason is not None:
                    raise ValueError(f"MCP server '{server_name}' has a header '{header_name}' that cannot be sent as an HTTP header value: it {reason}")
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
