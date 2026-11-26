"""MCP configuration file, transports and server registry."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.providers.mcp import (
    HttpTransport,
    MCPConfig,
    MCPServerNotFoundError,
    MCPServerRegistry,
    MCPTransport,
    StdioTransport,
    WebSocketTransport,
)


def write_config(tmp_path: Path, servers: dict[str, object]) -> Path:
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps({"mcpServers": servers}))
    return path


def test_missing_file_gives_empty_config(tmp_path: Path) -> None:
    assert MCPConfig.load(tmp_path / "absent.json").servers == {}


def test_transports_are_parsed_and_inferred(tmp_path: Path) -> None:
    config = MCPConfig.load(
        write_config(
            tmp_path,
            {
                "fs": {"command": "npx", "args": ["-y", "server-fs", "."]},
                "docs": {"url": "http://localhost:8000/mcp"},
                "legacy": {"transport": "sse", "url": "http://localhost:9000/sse"},
                "ws": {"transport": "websocket", "url": "ws://localhost:7000"},
            },
        )
    )
    servers = config.servers

    assert isinstance(servers["fs"], StdioTransport)
    assert isinstance(servers["docs"], HttpTransport) and servers["docs"].transport == "streamable_http"
    assert isinstance(servers["legacy"], HttpTransport) and servers["legacy"].transport == "sse"
    assert isinstance(servers["ws"], WebSocketTransport)
    assert all(isinstance(s, MCPTransport) for s in servers.values())


def test_to_connection_drops_enabled_and_empty_fields(tmp_path: Path) -> None:
    stdio = StdioTransport(transport="stdio", command="python", args=["server.py"], cwd=tmp_path)
    assert stdio.to_connection() == {
        "transport": "stdio",
        "command": "python",
        "args": ["server.py"],
        "cwd": str(tmp_path),
    }
    http = HttpTransport(transport="streamable_http", url="http://x/mcp", enabled=False)
    assert http.to_connection() == {"transport": "streamable_http", "url": "http://x/mcp"}


def test_unknown_fields_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        MCPConfig.load(write_config(tmp_path, {"fs": {"command": "npx", "typo_field": 1}}))


def test_registry_from_config_keeps_only_enabled(tmp_path: Path) -> None:
    path = write_config(tmp_path, {"on": {"command": "a"}, "off": {"command": "b", "enabled": False}})
    registry = MCPServerRegistry.from_config(MCPConfig.load(path))

    assert registry.names() == ["off", "on"]
    assert list(registry.enabled()) == ["on"]


def test_registry_register_get_unregister() -> None:
    registry = MCPServerRegistry()
    git = StdioTransport(transport="stdio", command="uvx", args=["mcp-server-git"])

    registry.register("git", git)
    assert registry.get("git") is git

    registry.unregister("git")
    with pytest.raises(MCPServerNotFoundError):
        registry.get("git")
    with pytest.raises(MCPServerNotFoundError):
        registry.unregister("git")
