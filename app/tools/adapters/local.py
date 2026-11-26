"""Adapter for tools implemented in this code base (subclasses of :class:`BaseTool`).

It validates raw arguments against the tool's input model, then runs the tool in-process.
"""

from typing import Any

from pydantic import ValidationError

from app.tools.base import BaseTool
from app.tools.interfaces import ToolAdapter, ToolSpec, ToolValidationError


class LocalToolAdapter(ToolAdapter):
    def __init__(self, tool: BaseTool[Any]) -> None:
        self._tool = tool

    @property
    def spec(self) -> ToolSpec:
        return self._tool.spec

    async def execute(self, arguments: dict[str, Any]) -> Any:
        try:
            params = self._tool.input_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(_describe(self._tool.name, exc)) from exc
        return await self._tool.execute(params)


def _describe(tool_name: str, exc: ValidationError) -> str:
    """Short, LLM-readable summary of what is wrong with the arguments."""
    problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}" for e in exc.errors())
    return f"Invalid arguments for {tool_name!r}: {problems}"
