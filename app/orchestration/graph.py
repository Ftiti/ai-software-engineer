"""Builds and compiles the LangGraph workflow.

Current graph::

    START -> agent -> (route_after_agent) -> END

This module only wires nodes and edges around the agents it receives. It never creates
providers or agents; that happens in the composition root, :mod:`app.container`.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.base import BaseAgent
from app.orchestration.nodes import NodeName, create_agent_node
from app.orchestration.router import route_after_agent
from app.orchestration.state import AgentState

AgentGraph = CompiledStateGraph[AgentState, None, AgentState, AgentState]


def build_graph(agent: BaseAgent) -> AgentGraph:
    """Wire and compile the single-agent graph around ``agent``."""
    builder = StateGraph(AgentState)
    builder.add_node(NodeName.AGENT, create_agent_node(agent))
    builder.add_edge(START, NodeName.AGENT)
    builder.add_conditional_edges(NodeName.AGENT, route_after_agent, {END: END})
    return builder.compile(name="ai-software-engineer")
