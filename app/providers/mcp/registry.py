"""Registry of known MCP servers (filesystem, git, databases, browsers, ...).

Servers come from the MCP config file and can also be registered in code. The registry only
knows *how to reach* each server; talking to them is the client's job.
"""

from app.config import Settings, get_settings
from app.providers.mcp.config import MCPConfig
from app.providers.mcp.transport import MCPServerConfig


class MCPServerNotFoundError(KeyError):
    pass


class MCPServerRegistry:
    def __init__(self, servers: dict[str, MCPServerConfig] | None = None) -> None:
        self._servers: dict[str, MCPServerConfig] = dict(servers or {})

    @classmethod
    def from_config(cls, config: MCPConfig) -> "MCPServerRegistry":
        return cls(config.servers)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "MCPServerRegistry":
        settings = settings or get_settings()
        return cls.from_config(MCPConfig.load(settings.mcp_config_path))

    def register(self, name: str, server: MCPServerConfig) -> None:
        self._servers[name] = server

    def unregister(self, name: str) -> None:
        if self._servers.pop(name, None) is None:
            raise MCPServerNotFoundError(name)

    def get(self, name: str) -> MCPServerConfig:
        try:
            return self._servers[name]
        except KeyError:
            raise MCPServerNotFoundError(name) from None

    def names(self) -> list[str]:
        return sorted(self._servers)

    def enabled(self) -> dict[str, MCPServerConfig]:
        return {name: server for name, server in sorted(self._servers.items()) if server.enabled}
