"""MCP tool adapter, tested against a fake MCP client (no server involved)."""

from typing import Any

import pytest

from app.providers.mcp import MCPClient, MCPToolCallResult, MCPToolInfo
from app.tools import ToolExecutionError, ToolManager, ToolRegistry, ToolRequest
from app.tools.adapters import MCPToolAdapter, load_mcp_tools
from app.tools.adapters.mcp import qualified_name


class FakeMCPClient(MCPClient):
    def __init__(self, tools: list[MCPToolInfo], replies: dict[str, MCPToolCallResult] | None = None) -> None:
        self.tools = tools
        self.replies = replies or {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def list_tools(self, server: str | None = None) -> list[MCPToolInfo]:
        return [t for t in self.tools if server in (None, t.server)]

    async def execute_tool(self, server: str, tool: str, arguments: dict[str, Any]) -> MCPToolCallResult:
        self.calls.append((server, tool, arguments))
        return self.replies.get(tool, MCPToolCallResult(content="ok"))


READ = MCPToolInfo(
    server="filesystem",
    name="read_file",
    description="Read a file.",
    input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
)


def test_spec_comes_from_mcp_tool_with_server_prefix() -> None:
    spec = MCPToolAdapter(FakeMCPClient([READ]), READ).spec
    assert spec.name == "filesystem_read_file"
    assert spec.description == "Read a file."
    assert spec.input_schema == READ.input_schema
    assert spec.source == "mcp"


async def test_execution_is_forwarded_to_the_client() -> None:
    client = FakeMCPClient([READ], {"read_file": MCPToolCallResult(content="file body")})
    output = await MCPToolAdapter(client, READ).execute({"path": "a.txt"})

    assert output == "file body"
    assert client.calls == [("filesystem", "read_file", {"path": "a.txt"})]


async def test_server_side_error_becomes_tool_execution_error() -> None:
    client = FakeMCPClient([READ], {"read_file": MCPToolCallResult(content="no such file", is_error=True)})
    with pytest.raises(ToolExecutionError, match="no such file"):
        await MCPToolAdapter(client, READ).execute({"path": "x"})


async def test_load_mcp_tools_connects_and_wraps_every_tool() -> None:
    other = READ.model_copy(update={"server": "git", "name": "status"})
    client = FakeMCPClient([READ, other])

    adapters = await load_mcp_tools(client)

    assert client.connected
    assert [a.name for a in adapters] == ["filesystem_read_file", "git_status"]


async def test_manager_runs_mcp_tool_through_registry() -> None:
    client = FakeMCPClient([READ], {"read_file": MCPToolCallResult(content="hello")})
    manager = ToolManager(ToolRegistry(await load_mcp_tools(client)))

    result = await manager.execute(ToolRequest(tool_name="filesystem_read_file", arguments={"path": "a"}))

    assert result.ok
    assert result.output == "hello"


@pytest.mark.parametrize(
    ("server", "tool", "expected"),
    [
        ("git", "status", "git_status"),
        ("my.server", "do it", "my_server_do_it"),
        ("s" * 40, "t" * 40, "s" * 40 + "_" + "t" * 23),
    ],
)
def test_qualified_name_is_llm_safe(server: str, tool: str, expected: str) -> None:
    assert qualified_name(server, tool) == expected
