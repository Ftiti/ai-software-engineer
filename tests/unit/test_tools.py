"""Tool system: base tool, registry, local adapter, manager and the demo echo tool."""

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from app.tools import (
    BaseTool,
    ToolAlreadyRegisteredError,
    ToolExecutionError,
    ToolManager,
    ToolNotFoundError,
    ToolRegistry,
    ToolRequest,
    ToolResult,
    ToolValidationError,
)
from app.tools.adapters import LocalToolAdapter
from app.tools.local.echo import EchoTool

# -- Test tools -----------------------------------------------------------------------------


class NoInput(BaseModel):
    pass


class FailingTool(BaseTool[NoInput]):
    name = "failing"
    description = "Reports an expected failure."
    input_model = NoInput

    async def execute(self, params: NoInput) -> Any:
        raise ToolExecutionError("file not found: missing.txt")


class CrashingTool(BaseTool[NoInput]):
    name = "crashing"
    description = "Has a bug."
    input_model = NoInput

    async def execute(self, params: NoInput) -> Any:
        raise ZeroDivisionError("division by zero")


class SleepInput(BaseModel):
    seconds: float


class SleepTool(BaseTool[SleepInput]):
    name = "sleep"
    description = "Waits, then returns the delay."
    input_model = SleepInput

    async def execute(self, params: SleepInput) -> float:
        await asyncio.sleep(params.seconds)
        return params.seconds


def manager_with(*tools: BaseTool[Any], timeout: float | None = None) -> ToolManager:
    return ToolManager(ToolRegistry(LocalToolAdapter(t) for t in tools), timeout=timeout)


def request(name: str, **arguments: Any) -> ToolRequest:
    return ToolRequest(tool_name=name, arguments=arguments, call_id=f"call-{name}")


# -- BaseTool -------------------------------------------------------------------------------


def test_tool_spec_exposes_name_description_and_schema() -> None:
    spec = EchoTool().spec
    assert spec.name == "echo"
    assert spec.source == "local"
    assert "unchanged" in spec.description
    assert spec.input_schema["properties"]["text"]["type"] == "string"
    assert spec.input_schema["required"] == ["text"]


def test_invalid_tool_name_is_rejected_at_class_definition() -> None:
    with pytest.raises(TypeError, match="Invalid tool name"):

        class BadName(BaseTool[NoInput]):
            name = "read file"  # spaces are not accepted by LLM APIs
            description = ""
            input_model = NoInput

            async def execute(self, params: NoInput) -> None:
                return None


# -- Registry -------------------------------------------------------------------------------


def test_register_and_lookup() -> None:
    registry = ToolRegistry()
    adapter = LocalToolAdapter(EchoTool())
    registry.register(adapter)

    assert "echo" in registry
    assert len(registry) == 1
    assert registry.get("echo") is adapter
    assert registry.names() == ["echo"]
    assert [s.name for s in registry.list_specs()] == ["echo"]


def test_lookup_unknown_tool_lists_available() -> None:
    registry = ToolRegistry([LocalToolAdapter(EchoTool())])
    with pytest.raises(ToolNotFoundError, match="Available: echo"):
        registry.get("nope")


def test_duplicate_registration_is_rejected_unless_replace() -> None:
    registry = ToolRegistry([LocalToolAdapter(EchoTool())])
    with pytest.raises(ToolAlreadyRegisteredError):
        registry.register(LocalToolAdapter(EchoTool()))

    replacement = LocalToolAdapter(EchoTool())
    registry.register(replacement, replace=True)
    assert registry.get("echo") is replacement


def test_unregister() -> None:
    registry = ToolRegistry([LocalToolAdapter(EchoTool())])
    registry.unregister("echo")
    assert "echo" not in registry
    with pytest.raises(ToolNotFoundError):
        registry.unregister("echo")


def test_specs_are_sorted_by_name() -> None:
    registry = ToolRegistry([LocalToolAdapter(SleepTool()), LocalToolAdapter(EchoTool())])
    assert registry.names() == ["echo", "sleep"]


# -- Local adapter --------------------------------------------------------------------------


async def test_local_adapter_validates_then_executes() -> None:
    adapter = LocalToolAdapter(EchoTool())
    assert await adapter.execute({"text": "Hello"}) == "Hello"


async def test_local_adapter_reports_invalid_arguments() -> None:
    adapter = LocalToolAdapter(EchoTool())
    with pytest.raises(ToolValidationError, match="Invalid arguments for 'echo': text: Field required"):
        await adapter.execute({"wrong": "x"})


# -- Manager --------------------------------------------------------------------------------


async def test_manager_executes_echo() -> None:
    result = await manager_with(EchoTool()).execute(request("echo", text="Hello"))
    assert result == ToolResult(tool_name="echo", call_id="call-echo", output="Hello")
    assert result.ok


async def test_manager_unknown_tool_is_a_failed_result() -> None:
    result = await manager_with(EchoTool()).execute(request("missing"))
    assert not result.ok
    assert "Unknown tool 'missing'" in (result.error or "")


async def test_manager_invalid_arguments_is_a_failed_result() -> None:
    result = await manager_with(EchoTool()).execute(request("echo", text=123))
    assert not result.ok
    assert "Input should be a valid string" in (result.error or "")


async def test_manager_tool_failure_message_is_kept() -> None:
    result = await manager_with(FailingTool()).execute(request("failing"))
    assert result.error == "file not found: missing.txt"


async def test_manager_unexpected_crash_is_contained() -> None:
    result = await manager_with(CrashingTool()).execute(request("crashing"))
    assert result.error == "Tool 'crashing' failed: ZeroDivisionError: division by zero"


async def test_manager_timeout() -> None:
    result = await manager_with(SleepTool(), timeout=0.05).execute(request("sleep", seconds=1))
    assert result.error == "Tool 'sleep' timed out after 0.05s"


async def test_manager_execute_many_runs_concurrently_and_keeps_order() -> None:
    manager = manager_with(SleepTool(), EchoTool())
    started = asyncio.get_running_loop().time()

    results = await manager.execute_many(
        [request("sleep", seconds=0.2), request("echo", text="a"), request("sleep", seconds=0.2)]
    )

    assert [r.output for r in results] == [0.2, "a", 0.2]
    assert asyncio.get_running_loop().time() - started < 0.35  # not 0.4: ran concurrently


def test_manager_lists_tool_specs() -> None:
    assert [s.name for s in manager_with(EchoTool(), SleepTool()).list_tools()] == ["echo", "sleep"]
