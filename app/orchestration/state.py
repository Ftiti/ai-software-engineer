"""Graph state shared by every node.

``messages`` is the single channel all nodes read and write. Its ``add_messages`` reducer
appends new messages (or replaces one with the same id), so a node returns only the
messages it produced, never the whole history.

The message list already covers the planned extensions without schema changes:

- **Tool calls**: ``AIMessage.tool_calls`` carries requests and ``ToolMessage`` carries results.
- **Agent communication**: each agent sets ``AIMessage.name``, so multi-agent turns stay
  attributable inside one shared history.

New channels (plan, active agent, ...) are added here as later sprints need them.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
