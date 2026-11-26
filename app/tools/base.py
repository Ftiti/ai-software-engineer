"""Base class for tools implemented in this code base (local tools).

A tool declares a name, a description and a Pydantic input model, and implements
:meth:`BaseTool.execute`. The input model gives both validation and the JSON Schema an LLM
needs. Dependencies (services, workspace root...) are passed to the constructor, never
looked up globally.

Example::

    class EchoInput(BaseModel):
        text: str

    class EchoTool(BaseTool[EchoInput]):
        name = "echo"
        description = "Return the text unchanged."
        input_model = EchoInput

        async def execute(self, params: EchoInput) -> str:
            return params.text
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.tools.interfaces import ToolSpec

InputT = TypeVar("InputT", bound=BaseModel)

# Accepted by every major LLM API for function/tool names.
TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class BaseTool(ABC, Generic[InputT]):
    name: str
    description: str
    input_model: type[InputT]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        name = cls.__dict__.get("name")
        if name is not None and not TOOL_NAME_PATTERN.fullmatch(name):
            raise TypeError(f"Invalid tool name {name!r}: use 1-64 characters from [a-zA-Z0-9_-]")

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description, input_schema=self.input_schema, source="local"
        )

    @abstractmethod
    async def execute(self, params: InputT) -> Any:
        """Run the tool with validated parameters.

        Raise :class:`app.tools.interfaces.ToolExecutionError` for failures the caller should
        see (e.g. "file not found"); any other exception is treated as an internal error.
        """
