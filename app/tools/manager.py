"""Single entry point for running tools.

    ToolRequest ─► registry lookup ─► adapter.execute (with timeout) ─► ToolResult

The manager never raises for a tool problem (unknown tool, bad arguments, tool failure,
timeout, crash): it returns a failed :class:`ToolResult` whose message can be sent back to
the LLM, so one bad call never stops the agent loop.
"""

import asyncio
import logging
from collections.abc import Iterable

from app.tools.interfaces import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolRequest,
    ToolResult,
    ToolSpec,
    ToolValidationError,
)
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolManager:
    def __init__(self, registry: ToolRegistry, *, timeout: float | None = None) -> None:
        self._registry = registry
        self._timeout = timeout

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def list_tools(self) -> list[ToolSpec]:
        return self._registry.list_specs()

    async def execute(self, request: ToolRequest) -> ToolResult:
        try:
            adapter = self._registry.get(request.tool_name)
            output = await asyncio.wait_for(adapter.execute(request.arguments), self._timeout)
        except (ToolNotFoundError, ToolValidationError, ToolExecutionError) as exc:
            return ToolResult.failure(request, str(exc))
        except TimeoutError:
            return ToolResult.failure(request, f"Tool {request.tool_name!r} timed out after {self._timeout}s")
        except Exception as exc:
            logger.exception("Tool %r crashed", request.tool_name)
            return ToolResult.failure(
                request, f"Tool {request.tool_name!r} failed: {type(exc).__name__}: {exc}"
            )
        return ToolResult.success(request, output)

    async def execute_many(self, requests: Iterable[ToolRequest]) -> list[ToolResult]:
        """Run independent requests concurrently (an LLM may emit several tool calls at once).
        Results keep the order of the requests."""
        return list(await asyncio.gather(*(self.execute(r) for r in requests)))
