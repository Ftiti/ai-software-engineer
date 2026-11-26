"""Composition root: the one place where the application's objects are created and wired.

    Settings -> create_llm_provider -> LLMProvider -> BaseAgent -> build_graph -> graph
    Settings -> local tools + MCP tools -> ToolRegistry -> ToolManager

Every other module receives its collaborators instead of building them, so swapping a
provider or adding a capability (tools, MCP servers, agents) only changes this module.
"""

from typing import Any

from app.agents.base import BaseAgent
from app.config import Settings, get_settings
from app.orchestration import AgentGraph, build_graph
from app.providers.llm import LLMProvider, create_llm_provider
from app.providers.mcp import MCPClient, MCPServerRegistry, SessionMCPClient
from app.tools import BaseTool, ToolManager, ToolRegistry
from app.tools.adapters import LocalToolAdapter, load_mcp_tools


def build_agent(settings: Settings | None = None, provider: LLMProvider | None = None) -> BaseAgent:
    """Create the default agent. ``provider`` overrides the one selected by the settings."""
    return BaseAgent(provider or create_llm_provider(settings or get_settings()))


def build_application(settings: Settings | None = None) -> AgentGraph:
    """Create the compiled agent graph for the configured provider."""
    return build_graph(build_agent(settings))


def build_local_tools(settings: Settings) -> list[BaseTool[Any]]:
    """Local tools offered to agents. Each capability sprint registers its tools here."""
    return []


async def build_tool_manager(
    settings: Settings | None = None,
    *,
    local_tools: list[BaseTool[Any]] | None = None,
    mcp_client: MCPClient | None = None,
) -> ToolManager:
    """Create the tool manager with local tools and the tools of every reachable MCP server.

    ``local_tools`` and ``mcp_client`` override the defaults (used by tests and scripts).
    """
    settings = settings or get_settings()
    tools = build_local_tools(settings) if local_tools is None else local_tools
    registry = ToolRegistry(LocalToolAdapter(tool) for tool in tools)

    client = mcp_client or SessionMCPClient(MCPServerRegistry.from_settings(settings))
    for adapter in await load_mcp_tools(client):
        registry.register(adapter)

    return ToolManager(registry, timeout=settings.tool_timeout)
