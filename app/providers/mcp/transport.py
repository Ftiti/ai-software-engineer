"""How to reach an MCP server.

Each transport is a small Pydantic model that validates its own settings and turns them into
the connection parameters understood by the MCP session layer (``to_connection``):

- ``stdio``: launch a local process and talk over stdin/stdout.
- ``streamable_http`` / ``sse``: talk to a remote server over HTTP.
- ``websocket``: talk to a remote server over a WebSocket.

Adding a transport means adding a model here and to :data:`MCPServerConfig`; the client and
the registry do not change.
"""

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


class TransportType(StrEnum):
    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"
    SSE = "sse"
    WEBSOCKET = "websocket"


@runtime_checkable
class MCPTransport(Protocol):
    """Anything that knows how to describe a connection to one MCP server."""

    @property
    def transport(self) -> TransportType | str: ...

    def to_connection(self) -> dict[str, Any]: ...


class _TransportBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True

    def to_connection(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"enabled"}, exclude_none=True)


class StdioTransport(_TransportBase):
    transport: Literal["stdio"]
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: Path | None = None


class HttpTransport(_TransportBase):
    transport: Literal["streamable_http", "sse"]
    url: str
    headers: dict[str, str] | None = None


class WebSocketTransport(_TransportBase):
    transport: Literal["websocket"]
    url: str


def _infer_transport(data: Any) -> Any:
    """Allow the common short form: ``command`` means stdio, ``url`` means streamable HTTP."""
    if isinstance(data, dict) and "transport" not in data:
        return {**data, "transport": "stdio" if "command" in data else "streamable_http"}
    return data


MCPServerConfig = Annotated[
    StdioTransport | HttpTransport | WebSocketTransport,
    Field(discriminator="transport"),
    BeforeValidator(_infer_transport),
]
