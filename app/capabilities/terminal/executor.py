"""Runs validated commands through the :class:`TerminalProvider` and builds the result.

The executor owns everything between "this command is allowed" and "here is what it printed":
the process environment, OS error translation, output decoding and truncation markers.
"""

import shlex
from collections.abc import Mapping

from app.capabilities.terminal.exceptions import CommandNotFound, CommandPermissionDenied, TerminalError
from app.capabilities.terminal.schemas import CommandResult
from app.capabilities.terminal.validator import TerminalPolicy, ValidatedCommand
from app.providers.terminal import ProcessRequest, TerminalProvider, process_environment


class CommandExecutor:
    def __init__(self, provider: TerminalProvider, policy: TerminalPolicy) -> None:
        self._provider = provider
        self._policy = policy

    async def execute(self, command: ValidatedCommand) -> CommandResult:
        program = command.argv[0]
        request = ProcessRequest(
            argv=command.argv,
            cwd=command.working_directory.absolute,
            env=self._environment(command.env),
            timeout=command.timeout,
            max_output_bytes=self._policy.max_output_bytes,
        )
        try:
            result = await self._provider.run(request)
        except FileNotFoundError as exc:
            raise CommandNotFound(f"{program!r} is not installed or not on PATH") from exc
        except PermissionError as exc:
            raise CommandPermissionDenied(f"The operating system refused to run {program!r}") from exc
        except OSError as exc:
            raise TerminalError(f"Cannot start {program!r}: {exc.strerror or exc}") from exc

        return CommandResult(
            command=shlex.join(command.argv),
            working_directory=command.working_directory.relative,
            exit_code=result.exit_code,
            succeeded=result.exit_code == 0 and not result.timed_out,
            timed_out=result.timed_out,
            duration_seconds=round(result.duration, 3),
            stdout=result.stdout.text(),
            stderr=result.stderr.text() + (_timeout_note(command.timeout) if result.timed_out else ""),
            truncated=result.stdout.truncated or result.stderr.truncated,
        )

    def _environment(self, extra: Mapping[str, str]) -> dict[str, str]:
        """Only the allowed host variables (never API keys or tokens), then fixed and requested ones."""
        return process_environment(self._provider.environment(), self._policy.inherited_env, extra)


def _timeout_note(timeout: float) -> str:
    return f"\n[stopped: the command did not finish within {timeout}s]"
