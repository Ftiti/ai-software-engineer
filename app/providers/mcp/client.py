"""MCP client: loads tools from the servers in :class:`MCPServerRegistry`.

Tools come back as LangChain ``BaseTool`` objects, so LangGraph agents can use them exactly
like local tools.
"""

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.providers.mcp.registry import MCPServerRegistry


class MCPClient:
    def __init__(self, registry: MCPServerRegistry) -> None:
        # Prefix tool names with the server name so tools from different servers cannot collide.
        self._client = MultiServerMCPClient(registry.to_connections(), tool_name_prefix=True)

    async def get_tools(self, server_name: str | None = None) -> list[BaseTool]:
        """Return tools from every enabled server, or from ``server_name`` only."""
        return await self._client.get_tools(server_name=server_name)
