"""Contracts of the tool system, shared by every tool source (local, MCP, ...).

The pipeline only speaks these types:

    ToolRequest ─► ToolManager ─► ToolRegistry ─► ToolAdapter.execute ─► ToolResult

Nothing here depends on LangChain or LangGraph, so the pipeline can be driven by a graph
node, a CLI or a test alike.
"""

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ToolSource = Literal["local", "mcp"]


class ToolError(Exception):
    """Base class for errors raised inside the tool pipeline."""


class ToolNotFoundError(ToolError):
    """No tool is registered under the requested name."""


class ToolAlreadyRegisteredError(ToolError):
    """A tool with the same name is already registered."""


class ToolValidationError(ToolError):
    """The arguments do not match the tool's input schema."""


class ToolExecutionError(ToolError):
    """The tool ran and reported a failure. The message is shown to the caller (e.g. the LLM)."""


class ToolSpec(BaseModel):
    """What a caller (typically an LLM) needs to know to use a tool."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    input_schema: dict[str, Any] = Field(description="JSON Schema of the arguments object.")
    source: ToolSource


class ToolRequest(BaseModel):
    """A request to run one tool. ``call_id`` links the result back to the LLM's tool call."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = None


class ToolResult(BaseModel):
    """Outcome of a tool request. Failures are results, not exceptions, so the caller can
    report them back to the LLM and let it recover."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    call_id: str | None = None
    output: Any = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @classmethod
    def success(cls, request: ToolRequest, output: Any) -> "ToolResult":
        return cls(tool_name=request.tool_name, call_id=request.call_id, output=output)

    @classmethod
    def failure(cls, request: ToolRequest, error: str) -> "ToolResult":
        return cls(tool_name=request.tool_name, call_id=request.call_id, error=error)


class ToolAdapter(ABC):
    """Uniform executable view of one tool, whatever runs it (in-process code, MCP server...).

    The registry stores adapters; the manager only ever calls :meth:`execute`.
    """

    @property
    @abstractmethod
    def spec(self) -> ToolSpec: ...

    @property
    def name(self) -> str:
        return self.spec.name

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Run the tool. Raise :class:`ToolValidationError` or :class:`ToolExecutionError` on
        expected failures."""
