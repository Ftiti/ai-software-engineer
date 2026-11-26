"""Adapters giving every tool source the same :class:`ToolAdapter` interface."""

from app.tools.adapters.local import LocalToolAdapter
from app.tools.adapters.mcp import MCPToolAdapter, load_mcp_tools

__all__ = ["LocalToolAdapter", "MCPToolAdapter", "load_mcp_tools"]
