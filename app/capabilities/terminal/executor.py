"""Runs validated commands through the :class:`TerminalProvider` and builds the result.

The executor owns everything between "this command is allowed" and "here is what it printed":
the process environment, OS error translation, output decoding and truncation markers.
"""

import shlex
from collections.abc import Mapping

from app.capabilities.terminal.exceptions import CommandNotFound, CommandPermissionDenied, TerminalError
from app.capabilities.terminal.schemas import CommandResult
from app.capabilities.terminal.validator import TerminalPolicy, ValidatedCommand
from app.providers.terminal import ProcessRequest, StreamOutput, TerminalProvider

# Set for every command: no colours, pagers or interactive prompts (stdin is empty anyway).
NON_INTERACTIVE_ENV: Mapping[str, str] = {
    "NO_COLOR": "1",
    "PAGER": "cat",
    "GIT_PAGER": "cat",
    "GIT_TERMINAL_PROMPT": "0",
    "PYTHONUNBUFFERED": "1",
}


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
            stdout=_decode(result.stdout),
            stderr=_decode(result.stderr) + (_timeout_note(command.timeout) if result.timed_out else ""),
            truncated=result.stdout.truncated or result.stderr.truncated,
        )

    def _environment(self, extra: Mapping[str, str]) -> dict[str, str]:
        """Only the allowed host variables (never API keys or tokens), then fixed and requested ones."""
        host = self._provider.environment()
        inherited = {name: host[name] for name in self._policy.inherited_env if name in host}
        return {**inherited, **NON_INTERACTIVE_ENV, **extra}


def _decode(stream: StreamOutput) -> str:
    head = stream.head.decode("utf-8", errors="replace")
    if not stream.truncated:
        return head + stream.tail.decode("utf-8", errors="replace")
    omitted = stream.total_bytes - len(stream.head) - len(stream.tail)
    return f"{head}\n[... {omitted} bytes omitted ...]\n{stream.tail.decode('utf-8', errors='replace')}"


def _timeout_note(timeout: float) -> str:
    return f"\n[stopped: the command did not finish within {timeout}s]"
