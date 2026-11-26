"""MCP client: discovers and calls tools on the servers of an :class:`MCPServerRegistry`.

:class:`MCPClient` is the contract the tool system depends on. :class:`SessionMCPClient` is
the implementation: it opens a short-lived MCP session per operation (connect, call), using
the transport described by each server's config. Persistent sessions can be added later
behind the same contract.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from langchain_mcp_adapters.sessions import create_session
from mcp import ClientSession
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict

from app.providers.mcp.registry import MCPServerRegistry

logger = logging.getLogger(__name__)


class MCPToolInfo(BaseModel):
    """A tool as advertised by an MCP server."""

    model_config = ConfigDict(frozen=True)

    server: str
    name: str
    description: str
    input_schema: dict[str, Any]


class MCPToolCallResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str
    is_error: bool = False


class MCPClient(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Reach every enabled server and discover its tools."""

    @abstractmethod
    async def list_tools(self, server: str | None = None) -> list[MCPToolInfo]:
        """Tools discovered on ``server``, or on all servers. Connects first if needed."""

    @abstractmethod
    async def execute_tool(self, server: str, tool: str, arguments: dict[str, Any]) -> MCPToolCallResult:
        """Call ``tool`` on ``server``."""


class SessionMCPClient(MCPClient):
    def __init__(self, registry: MCPServerRegistry) -> None:
        self._registry = registry
        self._tools: dict[str, list[MCPToolInfo]] | None = None
        self.failed_servers: dict[str, str] = {}

    async def connect(self) -> None:
        tools: dict[str, list[MCPToolInfo]] = {}
        self.failed_servers = {}
        for name in self._registry.enabled():
            try:
                tools[name] = await self._discover(name)
            except Exception as exc:  # one unreachable server must not disable the others
                logger.warning("MCP server %r unavailable: %s", name, exc)
                self.failed_servers[name] = f"{type(exc).__name__}: {exc}"
        self._tools = tools

    async def list_tools(self, server: str | None = None) -> list[MCPToolInfo]:
        if self._tools is None:
            await self.connect()
        tools = self._tools or {}
        if server is not None:
            return list(tools.get(server, []))
        return [tool for server_tools in tools.values() for tool in server_tools]

    async def execute_tool(self, server: str, tool: str, arguments: dict[str, Any]) -> MCPToolCallResult:
        async with self._session(server) as session:
            result = await session.call_tool(tool, arguments)
        return MCPToolCallResult(content=_result_text(result), is_error=result.isError)

    async def _discover(self, server: str) -> list[MCPToolInfo]:
        found: list[MCPToolInfo] = []
        async with self._session(server) as session:
            cursor: str | None = None
            while True:
                page = await session.list_tools(cursor)
                found.extend(
                    MCPToolInfo(
                        server=server,
                        name=t.name,
                        description=t.description or "",
                        input_schema=t.inputSchema,
                    )
                    for t in page.tools
                )
                cursor = page.nextCursor
                if not cursor:
                    return found

    def _session(self, server: str) -> AbstractAsyncContextManager[ClientSession]:
        return _open_session(self._registry.get(server).to_connection())


@asynccontextmanager
async def _open_session(connection: dict[str, Any]) -> AsyncIterator[ClientSession]:
    """Open an MCP session for a connection and run the protocol handshake."""
    async with create_session(connection) as session:  # type: ignore[arg-type]
        await session.initialize()
        yield session


def _result_text(result: CallToolResult) -> str:
    parts = [c.text if isinstance(c, TextContent) else f"[{c.type} content]" for c in result.content]
    return "\n".join(parts)
