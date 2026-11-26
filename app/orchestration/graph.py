"""Builds and compiles the LangGraph workflow.

Current graph::

    START -> agent -> (route_after_agent) -> END

:func:`build_graph` only wires nodes and edges for agents it is given.
:func:`create_graph` is the composition root: it turns settings into an LLM provider, a
chat model and an agent, then calls :func:`build_graph`.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.base import BaseAgent
from app.config import Settings, get_settings
from app.orchestration.nodes import NodeName, create_agent_node
from app.orchestration.router import route_after_agent
from app.orchestration.state import AgentState
from app.providers.llm import create_llm_provider

AgentGraph = CompiledStateGraph[AgentState, None, AgentState, AgentState]


def build_graph(agent: BaseAgent) -> AgentGraph:
    """Wire and compile the single-agent graph around ``agent``."""
    builder = StateGraph(AgentState)
    builder.add_node(NodeName.AGENT, create_agent_node(agent))
    builder.add_edge(START, NodeName.AGENT)
    builder.add_conditional_edges(NodeName.AGENT, route_after_agent, {END: END})
    return builder.compile(name="ai-software-engineer")


def create_graph(settings: Settings | None = None) -> AgentGraph:
    """Build the graph using the LLM provider selected in the settings."""
    settings = settings or get_settings()
    llm = create_llm_provider(settings).chat_model()
    return build_graph(BaseAgent(llm))
