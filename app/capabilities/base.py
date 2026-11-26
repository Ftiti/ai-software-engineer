"""A capability bundles what an agent gains from one domain (filesystem, git, code intelligence...):
the tools it can call and the instructions explaining how to use them.

Capabilities are built in the composition root (``app/container.py``) with their
dependencies; the tool system and the agent only see the result.
"""

import asyncio
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel

from app.tools import BaseTool, ToolExecutionError

InputT = TypeVar("InputT", bound=BaseModel)


@dataclass(frozen=True)
class Capability:
    name: str
    tools: list[BaseTool[Any]] = field(default_factory=list)
    prompt: str = ""


class CapabilityTool(BaseTool[InputT]):
    """Shared plumbing of tools backed by a synchronous capability service.

    Subclasses implement :meth:`_run` (one service call) and list in ``errors`` the domain
    exceptions that are expected failures. The call runs in a worker thread so blocking I/O
    never stalls the event loop; expected failures become ``ToolExecutionError`` (reported to
    the LLM) and the response model is serialised to plain data.
    """

    errors: ClassVar[tuple[type[Exception], ...]] = ()

    async def execute(self, params: InputT) -> dict[str, Any]:
        try:
            response = await asyncio.to_thread(self._run, params)
        except self.errors as exc:
            raise ToolExecutionError(str(exc)) from exc
        return response.model_dump()

    @abstractmethod
    def _run(self, params: InputT) -> BaseModel: ...
