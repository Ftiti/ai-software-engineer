"""Shared fixtures: a small workspace, a test policy and a recording provider."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.capabilities.filesystem import FilesystemPolicy, PathValidator
from app.capabilities.terminal import CommandExecutor, CommandValidator, TerminalPolicy, TerminalService
from app.providers.filesystem import LocalFilesystemProvider
from app.providers.terminal import (
    LocalTerminalProvider,
    ProcessRequest,
    ProcessResult,
    StreamOutput,
    TerminalProvider,
)

POLICY = TerminalPolicy(
    allowed_commands=("python3", "echo", "ls", "git", "npm", "composer", "make", "noexec"),
    denied_commands=("rm", "bash"),
    allowed_subcommands={"git": ("status", "log"), "npm": ("test", "run"), "composer": ("test", "install")},
    denied_arguments=("--exec*",),
    denied_env=("PATH", "LD_*"),
    inherited_env=("PATH", "HOME", "LANG"),
    default_timeout=10.0,
    max_timeout=20.0,
    max_output_bytes=1000,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """
    workspace/
        .env       (secret)
        hello.py   prints "hello" and its arguments
        fail.py    prints "boom" on stderr, exits with 3
        src/
    """
    root = tmp_path / "workspace"
    (root / "src").mkdir(parents=True)
    (root / ".env").write_text("API_KEY=secret\n")
    (root / "hello.py").write_text("import sys\nprint('hello', *sys.argv[1:])\n")
    (root / "fail.py").write_text("import sys\nprint('boom', file=sys.stderr)\nsys.exit(3)\n")
    return root


@pytest.fixture
def paths(workspace: Path) -> PathValidator:
    policy = FilesystemPolicy(workspace_root=workspace, denied_patterns=(".env", "*.pem"))
    return PathValidator(LocalFilesystemProvider(), policy)


@pytest.fixture
def validator(paths: PathValidator) -> CommandValidator:
    return CommandValidator(paths, POLICY)


MakeService = Callable[..., TerminalService]


@pytest.fixture
def make_service(paths: PathValidator) -> MakeService:
    def make(provider: TerminalProvider | None = None, **policy: Any) -> TerminalService:
        terminal_policy = replace(POLICY, **policy)
        executor = CommandExecutor(provider or LocalTerminalProvider(), terminal_policy)
        return TerminalService(CommandValidator(paths, terminal_policy), executor, python="python3")

    return make


@pytest.fixture
def service(make_service: MakeService) -> TerminalService:
    return make_service()


class RecordingProvider(TerminalProvider):
    """Runs nothing: records each request and returns a canned result."""

    def __init__(self, result: ProcessResult | None = None, host_env: dict[str, str] | None = None) -> None:
        self.requests: list[ProcessRequest] = []
        self.result = result or ProcessResult(
            exit_code=0, stdout=StreamOutput(b"ok"), stderr=StreamOutput(b""), timed_out=False, duration=0.01
        )
        self.host_env = host_env if host_env is not None else {"PATH": "/usr/bin"}

    def environment(self) -> dict[str, str]:
        return dict(self.host_env)

    async def run(self, request: ProcessRequest) -> ProcessResult:
        self.requests.append(request)
        return self.result
