"""Registry of configured MCP servers."""

from typing import Any

from app.config import Settings, get_settings
from app.providers.mcp.config import MCPConfig, MCPServerConfig, StdioServerConfig


class MCPServerRegistry:
    """Holds MCP server definitions and exposes the enabled ones."""

    def __init__(self, config: MCPConfig) -> None:
        self._servers = dict(config.servers)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "MCPServerRegistry":
        settings = settings or get_settings()
        return cls(MCPConfig.load(settings.mcp_config_path))

    def enabled(self) -> dict[str, MCPServerConfig]:
        return {name: server for name, server in self._servers.items() if server.enabled}

    def to_connections(self) -> dict[str, Any]:
        """Return enabled servers in the connection format expected by ``langchain-mcp-adapters``."""
        connections: dict[str, Any] = {}
        for name, server in self.enabled().items():
            conn = server.model_dump(exclude={"enabled"}, exclude_none=True)
            if isinstance(server, StdioServerConfig) and server.cwd is not None:
                conn["cwd"] = str(server.cwd)
            connections[name] = conn
        return connections
