"""Loading of the MCP servers file.

The format follows the ``mcpServers`` convention used by Claude Desktop, Claude Code and
Cursor, so existing server definitions can be reused as-is::

    {
      "mcpServers": {
        "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]},
        "docs": {"url": "http://localhost:8000/mcp", "headers": {"Authorization": "Bearer ..."}}
      }
    }

Transports are described in :mod:`app.providers.mcp.transport`.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.providers.mcp.transport import MCPServerConfig


class MCPConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    servers: dict[str, MCPServerConfig] = Field(default_factory=dict, alias="mcpServers")

    @classmethod
    def load(cls, path: Path) -> "MCPConfig":
        """Load from a JSON file. A missing file yields an empty configuration."""
        if not path.is_file():
            return cls()
        return cls.model_validate_json(path.read_bytes())
