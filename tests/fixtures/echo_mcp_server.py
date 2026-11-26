"""Minimal MCP server over stdio, launched by the MCP integration tests."""

from mcp.server.fastmcp import FastMCP

server = FastMCP("echo-test")


@server.tool()
def echo(text: str) -> str:
    """Return the given text unchanged."""
    return text


@server.tool()
def fail(reason: str) -> str:
    """Always fail with the given reason."""
    raise ValueError(reason)


if __name__ == "__main__":
    server.run()  # stdio transport
