"""Adapter for tools served by MCP servers.

It forwards execution to an :class:`MCPClient`; validation of the arguments is done by the
MCP server against the schema it advertised. Tool names are prefixed with the server name
(``<server>_<tool>``) so two servers can expose a tool with the same name.
"""

import re
from typing import Any

from app.providers.mcp.client import MCPClient, MCPToolInfo
from app.tools.interfaces import ToolAdapter, ToolExecutionError, ToolSpec

_INVALID_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


class MCPToolAdapter(ToolAdapter):
    def __init__(self, client: MCPClient, tool: MCPToolInfo) -> None:
        self._client = client
        self._tool = tool
        self._spec = ToolSpec(
            name=qualified_name(tool.server, tool.name),
            description=tool.description,
            input_schema=tool.input_schema,
            source="mcp",
        )

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, arguments: dict[str, Any]) -> Any:
        result = await self._client.execute_tool(self._tool.server, self._tool.name, arguments)
        if result.is_error:
            raise ToolExecutionError(result.content)
        return result.content


def qualified_name(server: str, tool: str) -> str:
    """``<server>_<tool>``, reduced to characters every LLM API accepts, max 64 chars."""
    return _INVALID_NAME_CHARS.sub("_", f"{server}_{tool}")[:64]


async def load_mcp_tools(client: MCPClient) -> list[MCPToolAdapter]:
    """Connect to the client's servers and wrap every discovered tool in an adapter."""
    await client.connect()
    return [MCPToolAdapter(client, tool) for tool in await client.list_tools()]
