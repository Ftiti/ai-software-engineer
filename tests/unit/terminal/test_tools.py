"""Terminal tools through the tool system: registry, manager, cancellation and the container."""

import asyncio
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.capabilities.filesystem import build_filesystem_service
from app.capabilities.terminal import TerminalService, build_terminal_capability, build_terminal_service
from app.capabilities.terminal.prompts import TERMINAL_PROMPT
from app.capabilities.terminal.tool import terminal_tools
from app.container import build_capabilities, build_local_tools
from app.tools import ToolManager, ToolRegistry, ToolRequest
from app.tools.adapters import LocalToolAdapter
from tests.conftest import make_settings

TOOL_NAMES = [
    "execute_command",
    "run_composer",
    "run_make",
    "run_npm",
    "run_pytest",
    "run_python",
    "run_tests",
]


def make_manager(service: TerminalService, timeout: float | None = None) -> ToolManager:
    return ToolManager(ToolRegistry(LocalToolAdapter(t) for t in terminal_tools(service)), timeout=timeout)


@pytest.fixture
def manager(service: TerminalService) -> ToolManager:
    return make_manager(service)


def call(name: str, **arguments: object) -> ToolRequest:
    return ToolRequest(tool_name=name, arguments=arguments, call_id=name)


def test_all_tools_are_registered(manager: ToolManager) -> None:
    specs = manager.list_tools()
    assert [s.name for s in specs] == TOOL_NAMES
    assert all(s.source == "local" and "exit code" in s.description for s in specs)


def test_input_schema_describes_arguments(manager: ToolManager) -> None:
    schema = manager.registry.get("execute_command").spec.input_schema
    assert schema["required"] == ["command"]
    assert "without a shell" in schema["properties"]["command"]["description"]
    assert set(schema["properties"]) == {"command", "working_directory", "timeout", "env"}


async def test_execute_command(manager: ToolManager) -> None:
    result = await manager.execute(call("execute_command", command="python3 hello.py"))
    assert result.ok
    assert result.output["succeeded"] and result.output["stdout"] == "hello\n"


async def test_failed_command_is_a_successful_tool_call(manager: ToolManager) -> None:
    result = await manager.execute(call("run_python", args=["fail.py"]))
    assert result.ok  # the tool worked; the command failed
    assert (result.output["succeeded"], result.output["exit_code"]) == (False, 3)


@pytest.mark.parametrize(
    ("request_", "error"),
    [
        (call("execute_command", command="rm -rf ."), "'rm' is blocked"),
        (call("execute_command", command="cat .env"), "'cat' is not an allowed command"),
        (call("execute_command", command="ls | wc"), "Shell operators"),
        (call("execute_command", command="ls", working_directory=".."), "outside the workspace"),
        (call("execute_command", command="git status"), "'git' is blocked"),
        (call("run_npm", args=["publish"]), "'npm publish' is not allowed"),
        (call("execute_command", command="ls", timeout=999), "exceeds the maximum"),
        (call("execute_command", command="ls", timeout=-1), "greater than 0"),
        (call("execute_command"), "command: Field required"),
    ],
)
async def test_errors_become_readable_tool_results(
    manager: ToolManager, request_: ToolRequest, error: str
) -> None:
    result = await manager.execute(request_)
    assert not result.ok
    assert error in (result.error or "")


async def test_tool_manager_timeout_stops_the_process(service: TerminalService, workspace: Path) -> None:
    """Cancellation: the manager gives up after 0.5s and the command does not keep running."""
    pid_file = workspace / "pid"
    code = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(30)"
    result = await make_manager(service, timeout=0.5).execute(call("run_python", args=["-c", code]))

    assert not result.ok and "timed out after 0.5s" in (result.error or "")
    pid = int(pid_file.read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.05)
    pytest.fail("the command is still running")


def test_capability_bundles_tools_and_prompt(workspace: Path) -> None:
    settings = make_settings(fs_workspace_root=workspace)
    capability = build_terminal_capability(
        build_terminal_service(settings, build_filesystem_service(settings).validator)
    )
    assert capability.name == "terminal"
    assert sorted(t.name for t in capability.tools) == TOOL_NAMES
    assert capability.prompt == TERMINAL_PROMPT
    assert "without a shell" in capability.prompt


def test_container_registers_terminal_tools(workspace: Path) -> None:
    settings = make_settings(fs_workspace_root=workspace)
    assert "terminal" in [c.name for c in build_capabilities(settings)]
    assert set(TOOL_NAMES) <= {t.name for t in build_local_tools(settings)}


def test_terminal_can_be_disabled(workspace: Path) -> None:
    settings = make_settings(fs_workspace_root=workspace, terminal_enabled=False)
    assert "terminal" not in [c.name for c in build_capabilities(settings)]
    assert not set(TOOL_NAMES) & {t.name for t in build_local_tools(settings)}


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"terminal_max_timeout": 60, "tool_timeout": 60}, "lower than TOOL_TIMEOUT"),
        ({"terminal_default_timeout": 40, "terminal_max_timeout": 30}, "must not exceed"),
    ],
)
def test_settings_reject_inconsistent_timeouts(overrides: dict[str, float], error: str) -> None:
    with pytest.raises(ValidationError, match=error):
        make_settings(**overrides)


def test_settings_without_tool_timeout() -> None:
    assert make_settings(tool_timeout=None, terminal_max_timeout=600).terminal_max_timeout == 600
