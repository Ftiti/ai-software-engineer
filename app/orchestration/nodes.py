"""Graph nodes.

A node reads :class:`AgentState` and returns a partial state update. Nodes are built by
factories that receive their collaborators (agents, later tools), so a node never knows
which LLM provider, tools or MCP servers exist.
"""

from typing import Any

from langchain_core.runnables import RunnableLambda

from app.agents.base import BaseAgent
from app.orchestration.state import AgentState


class NodeName:
    """Node identifiers used when wiring the graph and returned by routers."""

    AGENT = "agent"


def create_agent_node(agent: BaseAgent) -> RunnableLambda[AgentState, dict[str, Any]]:
    """Build the node that sends the conversation to ``agent`` and appends its reply.

    Both sync and async entry points are provided, so ``graph.invoke`` and ``graph.ainvoke``
    each call the model natively.
    """

    def agent_node(state: AgentState) -> dict[str, Any]:
        return {"messages": [agent.invoke(state["messages"])]}

    async def aagent_node(state: AgentState) -> dict[str, Any]:
        return {"messages": [await agent.ainvoke(state["messages"])]}

    return RunnableLambda(agent_node, afunc=aagent_node, name="agent_node")
