"""Terminal tools: thin wrappers exposing :class:`TerminalService` to the tool system.

They are asynchronous (:class:`AsyncCapabilityTool`): the command runs on the event loop, so
when the tool manager cancels a call (its timeout) the process is stopped instead of being
left running in a background thread.
"""

from typing import Any, TypeVar

from pydantic import BaseModel

from app.capabilities.base import AsyncCapabilityTool
from app.capabilities.terminal.exceptions import TerminalError
from app.capabilities.terminal.schemas import (
    ExecuteCommandRequest,
    RunComposerRequest,
    RunGitRequest,
    RunMakeRequest,
    RunNpmRequest,
    RunPytestRequest,
    RunPythonRequest,
    RunTestsRequest,
)
from app.capabilities.terminal.service import TerminalService
from app.tools import BaseTool

InputT = TypeVar("InputT", bound=BaseModel)

_RESULT = " Returns stdout, stderr and the exit code; a failing command is a normal result to read."


class TerminalTool(AsyncCapabilityTool[InputT]):
    errors = (TerminalError,)

    def __init__(self, service: TerminalService) -> None:
        self._service = service


class ExecuteCommandTool(TerminalTool[ExecuteCommandRequest]):
    name = "execute_command"
    description = (
        "Run one allowed command line in the project, e.g. 'ruff check app'. No shell: no pipes, "
        "redirections or '&&'." + _RESULT
    )
    input_model = ExecuteCommandRequest

    async def _arun(self, params: ExecuteCommandRequest) -> BaseModel:
        return await self._service.execute_command(params.command, params)


class RunTestsTool(TerminalTool[RunTestsRequest]):
    name = "run_tests"
    description = "Run the project's test suite (runner detected automatically unless given)." + _RESULT
    input_model = RunTestsRequest

    async def _arun(self, params: RunTestsRequest) -> BaseModel:
        return await self._service.run_tests(params.runner, params.args, params)


class RunPythonTool(TerminalTool[RunPythonRequest]):
    name = "run_python"
    description = "Run the Python interpreter with arguments (a script or -m module)." + _RESULT
    input_model = RunPythonRequest

    async def _arun(self, params: RunPythonRequest) -> BaseModel:
        return await self._service.run_python(params.args, params)


class RunPytestTool(TerminalTool[RunPytestRequest]):
    name = "run_pytest"
    description = "Run pytest with arguments (paths, -k expression, -x, -q...)." + _RESULT
    input_model = RunPytestRequest

    async def _arun(self, params: RunPytestRequest) -> BaseModel:
        return await self._service.run_pytest(params.args, params)


class RunMakeTool(TerminalTool[RunMakeRequest]):
    name = "run_make"
    description = "Run a Makefile target." + _RESULT
    input_model = RunMakeRequest

    async def _arun(self, params: RunMakeRequest) -> BaseModel:
        return await self._service.run_make(params.target, params.args, params)


class RunNpmTool(TerminalTool[RunNpmRequest]):
    name = "run_npm"
    description = "Run an allowed npm subcommand (install, ci, test, run <script>, ls...)." + _RESULT
    input_model = RunNpmRequest

    async def _arun(self, params: RunNpmRequest) -> BaseModel:
        return await self._service.run_npm(params.args, params)


class RunComposerTool(TerminalTool[RunComposerRequest]):
    name = "run_composer"
    description = "Run an allowed Composer (PHP) subcommand (install, update, test...)." + _RESULT
    input_model = RunComposerRequest

    async def _arun(self, params: RunComposerRequest) -> BaseModel:
        return await self._service.run_composer(params.args, params)


class RunGitCommandTool(TerminalTool[RunGitRequest]):
    name = "run_git_command"
    description = "Run a read-only git subcommand (status, diff, log, show...)." + _RESULT
    input_model = RunGitRequest

    async def _arun(self, params: RunGitRequest) -> BaseModel:
        return await self._service.run_git(params.args, params)


TERMINAL_TOOLS: tuple[type[TerminalTool[Any]], ...] = (
    ExecuteCommandTool,
    RunTestsTool,
    RunPythonTool,
    RunPytestTool,
    RunMakeTool,
    RunNpmTool,
    RunComposerTool,
    RunGitCommandTool,
)


def terminal_tools(service: TerminalService) -> list[BaseTool[Any]]:
    return [tool(service) for tool in TERMINAL_TOOLS]
