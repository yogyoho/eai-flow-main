"""Knowledge Factory MCP Server — HTTP (streamable-http) entry point.

Starts a long-lived streamable-HTTP MCP process so the DeerFlow gateway
discovers tools over a persistent connection.  Eliminates the cold-start
race that caused the old stdio transport to time out under load.

Usage:
    python -m app.extensions.knowledge_factory.mcp_server.http_server
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

# ── Reuse the same tool definitions and handler dispatch from server.py ──
from app.extensions.knowledge_factory.mcp_server.server import TOOLS, call_tool

mcp = FastMCP(
    "knowledge-factory",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8765")),
    streamable_http_path=os.getenv("MCP_PATH", "/mcp"),
)

# Register every tool defined in server.py so the agent sees the same
# interface regardless of transport (stdio vs HTTP).
for tool in TOOLS:
    # Bind the tool name to a closure so each handler dispatches correctly.
    def _make_handler(name: str):
        async def handler(arguments: dict):
            result = await call_tool(name, arguments)
            return result

        return handler

    mcp.add_tool(_make_handler(tool.name), name=tool.name, description=tool.description)


def main():
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "streamable-http"))


if __name__ == "__main__":
    main()
