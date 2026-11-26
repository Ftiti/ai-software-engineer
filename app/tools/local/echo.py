"""Demonstration tool used to validate the tool pipeline. Not registered by the application."""

from pydantic import BaseModel, Field

from app.tools.base import BaseTool


class EchoInput(BaseModel):
    text: str = Field(description="Text to return unchanged.")


class EchoTool(BaseTool[EchoInput]):
    name = "echo"
    description = "Return the given text unchanged. Used to test the tool pipeline."
    input_model = EchoInput

    async def execute(self, params: EchoInput) -> str:
        return params.text
