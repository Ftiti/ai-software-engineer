"""Typed requests and responses of the terminal capability.

Requests double as tool input models: their field descriptions end up in the JSON Schema the
LLM reads. Every request extends :class:`CommandOptions` (where and how long to run).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# -- Requests -------------------------------------------------------------------------------


class CommandOptions(_Model):
    working_directory: str = Field(
        default=".", description="Directory to run in, relative to the workspace root. '.' is the root."
    )
    timeout: float | None = Field(
        default=None, gt=0, description="Seconds before the command is stopped. Omit for the default."
    )
    env: dict[str, str] = Field(
        default_factory=dict, description="Extra environment variables, e.g. {'DEBUG': '1'}."
    )


def _args(example: str) -> list[str]:
    return Field(default_factory=list, description=f"Arguments, one per item, e.g. {example}.")


class ExecuteCommandRequest(CommandOptions):
    command: str = Field(
        description=(
            "One command line, e.g. 'pytest -q tests/unit'. It runs without a shell: no pipes, "
            "redirections, '&&' or variable expansion."
        )
    )


TestRunner = Literal["auto", "pytest", "npm", "composer", "make"]


class RunTestsRequest(CommandOptions):
    runner: TestRunner = Field(
        default="auto",
        description=(
            "Test runner. 'auto' detects it from the project files (Python project -> pytest, "
            "package.json -> npm test, composer.json -> composer test, Makefile -> make test)."
        ),
    )
    args: list[str] = _args("['-k', 'login'] (passed to the runner)")


class RunPythonRequest(CommandOptions):
    args: list[str] = _args("['scripts/build.py', '--fast'] or ['-m', 'pip', 'list']")


class RunPytestRequest(CommandOptions):
    args: list[str] = _args("['tests/unit', '-q', '-k', 'login']")


class RunMakeRequest(CommandOptions):
    target: str | None = Field(default=None, description="Makefile target, e.g. 'build'. Omit for default.")
    args: list[str] = _args("['VERBOSE=1']")


class RunNpmRequest(CommandOptions):
    args: list[str] = _args("['test'], ['run', 'build'] or ['install']")


class RunComposerRequest(CommandOptions):
    args: list[str] = _args("['install'] or ['test']")


class RunGitRequest(CommandOptions):
    args: list[str] = _args("['status', '--short'] or ['diff', 'app/main.py'] (read-only subcommands)")


# -- Response -------------------------------------------------------------------------------


class CommandResult(_Model):
    command: str = Field(description="The command that ran, shell-quoted.")
    working_directory: str
    exit_code: int = Field(description="0 means success; negative: stopped by that signal.")
    succeeded: bool = Field(description="True when the exit code is 0 and it did not time out.")
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str
    truncated: bool = Field(description="True when the middle of a long output was cut.")
