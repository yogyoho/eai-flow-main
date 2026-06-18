"""Demo MCP server — proves plugin→MCP wiring end-to-end.

Registered as a `type=tool` plugin (entry_point=this module). When the plugin
instance is enabled, sync_mcp_registration writes it into extensions_config.mcpServers,
and the agent gains the `demo_greet` tool via function calling.
"""

from __future__ import annotations

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

TOOLS = [
    Tool(
        name="demo_greet",
        description="演示工具(来自插件 MCP):返回一句问候。证明插件→MCP→function calling 通路已接通。",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "要问候的名字"}},
            "required": ["name"],
        },
    )
]


async def _handle_demo_greet(arguments: dict) -> list[TextContent]:
    name = arguments.get("name", "世界")
    return [TextContent(type="text", text=f"你好,{name}!这是来自插件 MCP 的演示工具。")]


server = Server("plugin_demo")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "demo_greet":
        return await _handle_demo_greet(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
