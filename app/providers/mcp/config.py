"""MCP server configuration models.

The file format follows the ``mcpServers`` convention used by Claude Desktop, Claude Code
and Cursor, so existing server definitions can be reused as-is::

    {
      "mcpServers": {
        "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]},
        "docs": {"url": "http://localhost:8000/mcp", "headers": {"Authorization": "Bearer ..."}}
      }
    }

When ``transport`` is omitted it is inferred: ``stdio`` if ``command`` is set, otherwise
``streamable_http``.
"""

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _infer_transport(data: Any) -> Any:
    if isinstance(data, dict) and "transport" not in data:
        return {**data, "transport": "stdio" if "command" in data else "streamable_http"}
    return data


class _ServerBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class StdioServerConfig(_ServerBase):
    transport: Literal["stdio"]
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: Path | None = None


class HttpServerConfig(_ServerBase):
    transport: Literal["streamable_http", "sse"]
    url: str
    headers: dict[str, str] | None = None


MCPServerConfig = Annotated[
    StdioServerConfig | HttpServerConfig,
    Field(discriminator="transport"),
    BeforeValidator(_infer_transport),
]


class MCPConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    servers: dict[str, MCPServerConfig] = Field(default_factory=dict, alias="mcpServers")

    @classmethod
    def load(cls, path: Path) -> "MCPConfig":
        """Load from a JSON file. A missing file yields an empty configuration."""
        if not path.is_file():
            return cls()
        return cls.model_validate_json(path.read_bytes())
