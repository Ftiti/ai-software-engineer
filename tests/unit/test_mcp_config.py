import json
from pathlib import Path

from app.providers.mcp import HttpServerConfig, MCPConfig, MCPServerRegistry, StdioServerConfig


def test_missing_file_gives_empty_config(tmp_path: Path) -> None:
    assert MCPConfig.load(tmp_path / "absent.json").servers == {}


def test_loads_and_infers_transport(tmp_path: Path) -> None:
    path = tmp_path / "mcp_servers.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fs": {"command": "npx", "args": ["-y", "server-fs", "."]},
                    "docs": {"url": "http://localhost:8000/mcp"},
                    "legacy": {"transport": "sse", "url": "http://localhost:9000/sse"},
                    "off": {"command": "disabled-server", "enabled": False},
                }
            }
        )
    )
    config = MCPConfig.load(path)

    assert isinstance(config.servers["fs"], StdioServerConfig)
    assert isinstance(config.servers["docs"], HttpServerConfig)
    assert config.servers["docs"].transport == "streamable_http"
    assert config.servers["legacy"].transport == "sse"

    connections = MCPServerRegistry(config).to_connections()
    assert set(connections) == {"fs", "docs", "legacy"}
    assert connections["fs"] == {"transport": "stdio", "command": "npx", "args": ["-y", "server-fs", "."]}
    assert connections["docs"] == {"transport": "streamable_http", "url": "http://localhost:8000/mcp"}
