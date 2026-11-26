"""Composition root: the one place where the application's objects are created and wired.

    Settings -> create_llm_provider -> LLMProvider -> BaseAgent -> build_graph -> graph

Every other module receives its collaborators instead of building them, so swapping a
provider (or, later, adding tools, MCP clients and more agents) only changes this module.
"""

from app.agents.base import BaseAgent
from app.config import Settings, get_settings
from app.orchestration import AgentGraph, build_graph
from app.providers.llm import LLMProvider, create_llm_provider


def build_agent(settings: Settings | None = None, provider: LLMProvider | None = None) -> BaseAgent:
    """Create the default agent. ``provider`` overrides the one selected by the settings."""
    return BaseAgent(provider or create_llm_provider(settings or get_settings()))


def build_application(settings: Settings | None = None) -> AgentGraph:
    """Create the compiled agent graph for the configured provider."""
    return build_graph(build_agent(settings))
