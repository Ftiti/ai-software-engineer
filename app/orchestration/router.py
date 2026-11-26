"""Conditional-edge functions: given the state, decide which node runs next.

Routers only read state and return a node name (or ``END``). They never call models or
tools, which keeps every routing decision testable on its own.

Planned branches, added in this module as each capability lands:

- ``tools``: the last ``AIMessage`` contains ``tool_calls`` (Sprint 2).
- another agent: the supervisor delegates (multi-agent sprint).
- planner steps: continue with the next plan step or finish (planner sprint).
"""

from langgraph.graph import END

from app.orchestration.state import AgentState


def route_after_agent(state: AgentState) -> str:
    """Return the next node name. With no tools yet, the turn always ends."""
    return END
