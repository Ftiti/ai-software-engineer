"""Real MCP round trips: the client launches tests/fixtures/echo_mcp_server.py over stdio."""

import sys
from pathlib import Path

from app.container import build_tool_manager
from app.providers.mcp import MCPServerRegistry, SessionMCPClient, StdioTransport
from app.tools import ToolRequest
from app.tools.local.echo import EchoTool
from tests.conftest import make_settings

SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "echo_mcp_server.py"


def echo_server_registry(**extra: StdioTransport) -> MCPServerRegistry:
    registry = MCPServerRegistry()
    registry.register("demo", StdioTransport(transport="stdio", command=sys.executable, args=[str(SERVER)]))
    for name, server in extra.items():
        registry.register(name, server)
    return registry


async def test_connect_discovers_tools() -> None:
    client = SessionMCPClient(echo_server_registry())
    await client.connect()

    tools = {t.name: t for t in await client.list_tools()}

    assert set(tools) == {"echo", "fail"}
    assert tools["echo"].server == "demo"
    assert tools["echo"].description == "Return the given text unchanged."
    assert tools["echo"].input_schema["properties"]["text"]["type"] == "string"
    assert await client.list_tools("unknown") == []


async def test_execute_tool_round_trip() -> None:
    client = SessionMCPClient(echo_server_registry())
    result = await client.execute_tool("demo", "echo", {"text": "Hello"})
    assert (result.content, result.is_error) == ("Hello", False)


async def test_server_error_is_reported_not_raised() -> None:
    client = SessionMCPClient(echo_server_registry())
    result = await client.execute_tool("demo", "fail", {"reason": "disk full"})
    assert result.is_error
    assert "disk full" in result.content


async def test_unreachable_server_does_not_block_the_others() -> None:
    broken = StdioTransport(transport="stdio", command="/nonexistent/mcp-server")
    client = SessionMCPClient(echo_server_registry(broken=broken))

    await client.connect()

    assert {t.name for t in await client.list_tools()} == {"echo", "fail"}
    assert "broken" in client.failed_servers


async def test_full_pipeline_with_local_and_mcp_tools() -> None:
    manager = await build_tool_manager(
        make_settings(),
        local_tools=[EchoTool()],
        mcp_client=SessionMCPClient(echo_server_registry()),
    )

    assert [s.name for s in manager.list_tools()] == ["demo_echo", "demo_fail", "echo"]
    assert {s.source for s in manager.list_tools()} == {"local", "mcp"}

    local, remote, failed = await manager.execute_many(
        [
            ToolRequest(tool_name="echo", arguments={"text": "Hello"}),
            ToolRequest(tool_name="demo_echo", arguments={"text": "Hello"}),
            ToolRequest(tool_name="demo_fail", arguments={"reason": "nope"}),
        ]
    )

    assert local.output == remote.output == "Hello"
    assert not failed.ok and "nope" in (failed.error or "")


async def test_default_tool_manager_has_capability_tools_and_no_mcp_without_config(tmp_path: Path) -> None:
    settings = make_settings(mcp_config_path=tmp_path / "absent.json", fs_workspace_root=tmp_path)
    manager = await build_tool_manager(settings)
    assert [s.name for s in manager.list_tools()] == [
        "create_file",
        "delete_file",
        "list_files",
        "read_file",
        "write_file",
    ]
    assert {s.source for s in manager.list_tools()} == {"local"}
