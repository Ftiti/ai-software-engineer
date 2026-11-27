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


class AsyncCapabilityTool(BaseTool[InputT]):
    """Shared plumbing of tools backed by a capability service.

    Subclasses implement :meth:`_arun` (one service call) and list in ``errors`` the domain
    exceptions that are expected failures. Expected failures become ``ToolExecutionError``
    (reported to the LLM) and the response model is serialised to plain data.
    """

    errors: ClassVar[tuple[type[Exception], ...]] = ()

    async def execute(self, params: InputT) -> dict[str, Any]:
        try:
            response = await self._arun(params)
        except self.errors as exc:
            raise ToolExecutionError(str(exc)) from exc
        return response.model_dump()

    @abstractmethod
    async def _arun(self, params: InputT) -> BaseModel: ...


class CapabilityTool(AsyncCapabilityTool[InputT]):
    """A tool backed by a *synchronous* service: :meth:`_run` runs in a worker thread so
    blocking I/O never stalls the event loop."""

    async def _arun(self, params: InputT) -> BaseModel:
        return await asyncio.to_thread(self._run, params)

    @abstractmethod
    def _run(self, params: InputT) -> BaseModel: ...
