"""A capability bundles what an agent gains from one domain (filesystem, git, code intelligence...):
the tools it can call and the instructions explaining how to use them.

Capabilities are built in the composition root (``app/container.py``) with their
dependencies; the tool system and the agent only see the result.
"""

from dataclasses import dataclass, field
from typing import Any

from app.tools import BaseTool


@dataclass(frozen=True)
class Capability:
    name: str
    tools: list[BaseTool[Any]] = field(default_factory=list)
    prompt: str = ""
