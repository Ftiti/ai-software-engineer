"""Centralised safety rules of the terminal capability.

Every command goes through :meth:`CommandValidator.validate` before a process starts. The
checks, in order:

1. **Well-formed**: a non-empty argument vector without NUL bytes. Command lines are split
   with POSIX quoting rules and **never run through a shell**, so shell operators (``|``,
   ``&&``, ``>``...) are refused instead of being silently passed as arguments.
2. **Program allowed**: a bare name (no path), not in ``denied_commands`` (the blacklist always
   wins), and in ``allowed_commands`` (the whitelist; ``*`` allows every non-denied program).
3. **Subcommand allowed**: for programs listed in ``allowed_subcommands`` (git, npm,
   composer), the first argument must be one of those subcommands.
4. **Arguments safe**: none matches ``denied_arguments`` (``--exec=...``, ...). Arguments that
   are paths leaving the working directory (absolute or with ``..``) must stay inside the
   workspace, and no argument may name a secret (the filesystem ``denied_patterns``).
5. **Working directory**: an existing directory inside the workspace, checked by the
   filesystem :class:`PathValidator` so both capabilities share one definition of the workspace.
6. **Timeout and environment**: timeout up to ``max_timeout``; variable names valid and not
   in ``denied_env`` (``PATH``, ``LD_PRELOAD``, ...).

These rules stop mistakes and obvious misuse. They are not a sandbox: an allowed interpreter
(``python -c ...``) can still do anything the user running the agent can. Run the agent in a
container for real isolation.
"""

import re
import shlex
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

from app.capabilities.filesystem import Operation, PathValidator
from app.capabilities.filesystem.exceptions import AccessDenied, FilesystemError
from app.capabilities.filesystem.validator import ResolvedPath
from app.capabilities.terminal.exceptions import CommandNotAllowed, InvalidCommand, WorkspaceViolation
from app.config import Settings

ANY_COMMAND = "*"
SHELL_OPERATORS = frozenset({"|", "||", "|&", "&", "&&", ";", ";;", "<", "<<", "<<<", ">", ">>", "&>", "2>"})
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class TerminalPolicy:
    allowed_commands: tuple[str, ...] = ()
    denied_commands: tuple[str, ...] = ()
    allowed_subcommands: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    denied_arguments: tuple[str, ...] = ()  # fnmatch patterns
    denied_env: tuple[str, ...] = ()  # fnmatch patterns on variable names
    inherited_env: tuple[str, ...] = ()  # host variables passed on to commands
    default_timeout: float = 30.0
    max_timeout: float = 50.0
    max_output_bytes: int = 64_000

    @classmethod
    def from_settings(cls, settings: Settings) -> "TerminalPolicy":
        return cls(
            allowed_commands=tuple(settings.terminal_allowed_commands),
            denied_commands=tuple(settings.terminal_denied_commands),
            allowed_subcommands={k: tuple(v) for k, v in settings.terminal_allowed_subcommands.items()},
            denied_arguments=tuple(settings.terminal_denied_arguments),
            denied_env=tuple(settings.terminal_denied_env),
            inherited_env=tuple(settings.terminal_inherited_env),
            default_timeout=settings.terminal_default_timeout,
            max_timeout=settings.terminal_max_timeout,
            max_output_bytes=settings.terminal_max_output_bytes,
        )


@dataclass(frozen=True, slots=True)
class ValidatedCommand:
    """A command that passed every check, ready for the executor."""

    argv: tuple[str, ...]
    working_directory: ResolvedPath
    timeout: float
    env: Mapping[str, str]


class CommandValidator:
    def __init__(self, paths: PathValidator, policy: TerminalPolicy) -> None:
        self._paths = paths
        self._policy = policy

    @property
    def policy(self) -> TerminalPolicy:
        return self._policy

    def parse(self, command: str) -> list[str]:
        """Split a command line into arguments (POSIX quoting), refusing shell syntax."""
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            raise InvalidCommand(f"Cannot parse the command: {exc}") from exc
        operators = sorted({arg for arg in argv if arg in SHELL_OPERATORS})
        if operators:
            raise InvalidCommand(
                f"Shell operators are not supported ({' '.join(operators)}): commands run without a "
                "shell. Run one command per call."
            )
        return argv

    def validate(
        self,
        argv: Sequence[str],
        *,
        working_directory: str = ".",
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ValidatedCommand:
        command = tuple(argv)
        if not command or not command[0].strip():
            raise InvalidCommand("The command is empty")
        if any("\x00" in arg for arg in command):
            raise InvalidCommand("The command contains a NUL byte")
        self._check_program(command)
        cwd = self.working_directory(working_directory)
        for argument in command[1:]:
            self._check_argument(argument, cwd)
        return ValidatedCommand(
            argv=command,
            working_directory=cwd,
            timeout=self._timeout(timeout),
            env=self._environment(env or {}),
        )

    def working_directory(self, path: str) -> ResolvedPath:
        with _workspace_errors():
            directory = self._paths.resolve(path, Operation.LIST)
            self._paths.require_directory(directory)
        return directory

    def has_file(self, directory: ResolvedPath, name: str) -> bool:
        return self._paths.exists(self._paths.child(directory, name))

    # -- Checks ------------------------------------------------------------------------------

    def _check_program(self, argv: tuple[str, ...]) -> None:
        program = argv[0]
        if "/" in program or "\\" in program:
            raise CommandNotAllowed(f"Give the program name only (e.g. 'pytest'), not a path: {program!r}")
        if program in self._policy.denied_commands:
            raise CommandNotAllowed(f"{program!r} is blocked: it is considered dangerous")
        allowed = self._policy.allowed_commands
        if ANY_COMMAND not in allowed and program not in allowed:
            raise CommandNotAllowed(f"{program!r} is not an allowed command. Allowed: {', '.join(allowed)}")

        subcommands = self._policy.allowed_subcommands.get(program)
        if subcommands is None:
            return
        subcommand = argv[1] if len(argv) > 1 else ""
        if subcommand not in subcommands:
            shown = f"{program} {subcommand}".strip()
            raise CommandNotAllowed(
                f"{shown!r} is not allowed. Allowed {program} subcommands: {', '.join(subcommands)}"
            )

    def _check_argument(self, argument: str, cwd: ResolvedPath) -> None:
        if any(fnmatchcase(argument, pattern) for pattern in self._policy.denied_arguments):
            raise CommandNotAllowed(f"The argument {argument!r} is not allowed")
        # '--file=../x' -> check '../x'
        value = argument.split("=", 1)[1] if argument.startswith("-") and "=" in argument else argument
        if not value:
            return
        if self._paths.is_denied(value.lstrip("/")):
            raise WorkspaceViolation(f"The argument {argument!r} refers to a protected secret")
        if value.startswith("/") or ".." in PurePosixPath(value).parts:
            relative_to_root = value.startswith("/") or cwd.relative == "."
            target = value if relative_to_root else f"{cwd.relative}/{value}"
            with _workspace_errors():
                self._paths.resolve(target, Operation.READ)

    def _timeout(self, timeout: float | None) -> float:
        if timeout is None:
            return self._policy.default_timeout
        if timeout <= 0:
            raise InvalidCommand("The timeout must be positive")
        if timeout > self._policy.max_timeout:
            raise InvalidCommand(f"Timeout {timeout}s exceeds the maximum of {self._policy.max_timeout}s")
        return timeout

    def _environment(self, env: Mapping[str, str]) -> dict[str, str]:
        for name, value in env.items():
            if not _ENV_NAME.fullmatch(name):
                raise InvalidCommand(f"Invalid environment variable name: {name!r}")
            if "\x00" in value:
                raise InvalidCommand(f"Environment variable {name!r} contains a NUL byte")
            if any(fnmatchcase(name, pattern) for pattern in self._policy.denied_env):
                raise CommandNotAllowed(f"Environment variable {name!r} cannot be set")
        return dict(env)


@contextmanager
def _workspace_errors() -> Iterator[None]:
    """Report filesystem rule violations as terminal errors."""
    try:
        yield
    except AccessDenied as exc:
        raise WorkspaceViolation(str(exc)) from exc
    except FilesystemError as exc:
        raise InvalidCommand(str(exc)) from exc
