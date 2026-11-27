"""TerminalService and CommandExecutor: real commands in a temporary workspace, plus argument
vectors and environments checked with a recording provider."""

import os
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.capabilities.terminal import TerminalService
from app.capabilities.terminal.exceptions import (
    CommandNotAllowed,
    CommandNotFound,
    CommandPermissionDenied,
    InvalidCommand,
    TerminalError,
    WorkspaceViolation,
)
from app.capabilities.terminal.schemas import CommandOptions, TestRunner
from app.providers.terminal import LocalTerminalProvider, ProcessRequest, ProcessResult, StreamOutput
from tests.unit.terminal.conftest import MakeService, RecordingProvider

# -- Real commands --------------------------------------------------------------------------


async def test_successful_command(service: TerminalService) -> None:
    result = await service.execute_command("python3 hello.py 'big world'")
    assert result.succeeded
    assert (result.exit_code, result.timed_out, result.truncated) == (0, False, False)
    assert result.stdout == "hello big world\n"
    assert result.stderr == ""
    assert result.command == "python3 hello.py 'big world'"
    assert result.working_directory == "."


async def test_failed_command_is_a_result(service: TerminalService) -> None:
    result = await service.execute_command("python3 fail.py")
    assert not result.succeeded
    assert result.exit_code == 3
    assert result.stderr == "boom\n"


async def test_timeout(service: TerminalService) -> None:
    result = await service.execute_command(
        "python3 -c 'import time; time.sleep(30)'", CommandOptions(timeout=0.5)
    )
    assert result.timed_out and not result.succeeded
    assert "did not finish within 0.5s" in result.stderr


async def test_working_directory(service: TerminalService, workspace: Path) -> None:
    result = await service.run_python(
        ["-c", "import os; print(os.getcwd())"], CommandOptions(working_directory="src")
    )
    assert result.stdout.strip() == str(workspace / "src")
    assert result.working_directory == "src"


async def test_environment_is_filtered_then_extended(
    service: TerminalService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECRET_TOKEN", "do-not-leak")
    code = "import os; print([os.environ.get(k) for k in ('SECRET_TOKEN', 'DEBUG', 'NO_COLOR')])"
    result = await service.run_python(["-c", code], CommandOptions(env={"DEBUG": "1"}))
    assert result.stdout.strip() == "[None, '1', '1']"


async def test_run_python_script(service: TerminalService) -> None:
    result = await service.run_python(["hello.py", "x"])
    assert result.stdout == "hello x\n"


async def test_run_pytest(service: TerminalService, workspace: Path) -> None:
    (workspace / "tests").mkdir()
    (workspace / "tests" / "test_sample.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    result = await service.run_pytest(["-q", "-p", "no:cacheprovider", "tests"])
    assert result.succeeded, result.stdout + result.stderr
    assert "1 passed" in result.stdout


@pytest.mark.parametrize(
    ("command", "kind", "error"),
    [
        ("ls | wc", InvalidCommand, "Shell operators"),
        ("rm -rf .", CommandNotAllowed, "blocked"),
        ("ls /etc", WorkspaceViolation, "outside the workspace"),
        ("python3 .env", WorkspaceViolation, "protected secret"),
        ("noexec", CommandNotFound, "'noexec' is not installed or not on PATH"),
    ],
)
async def test_invalid_commands(
    service: TerminalService, command: str, kind: type[Exception], error: str
) -> None:
    with pytest.raises(kind, match=error):
        await service.execute_command(command)


async def test_workspace_restriction_on_working_directory(service: TerminalService) -> None:
    with pytest.raises(WorkspaceViolation, match="outside the workspace"):
        await service.execute_command("ls", CommandOptions(working_directory=".."))


async def test_permission_denied(make_service: MakeService, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "noexec").write_text("#!/bin/sh\necho hi\n")  # allowed by the policy, not executable

    class PathProvider(LocalTerminalProvider):
        def environment(self) -> dict[str, str]:
            return {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    with pytest.raises(CommandPermissionDenied, match="refused to run 'noexec'"):
        await make_service(PathProvider()).execute_command("noexec")


# -- Argument vectors and environment (recording provider) ----------------------------------


@pytest.fixture
def recorder() -> RecordingProvider:
    return RecordingProvider(host_env={"PATH": "/usr/bin", "HOME": "/home/me", "OPENAI_API_KEY": "sk-secret"})


@pytest.fixture
def recorded(make_service: MakeService, recorder: RecordingProvider) -> TerminalService:
    return make_service(recorder)


def argv(recorder: RecordingProvider) -> tuple[str, ...]:
    return recorder.requests[-1].argv


async def test_program_shortcuts(recorded: TerminalService, recorder: RecordingProvider) -> None:
    await recorded.run_pytest(["-k", "login"])
    assert argv(recorder) == ("python3", "-m", "pytest", "-k", "login")
    await recorded.run_make("build", ["V=1"])
    assert argv(recorder) == ("make", "build", "V=1")
    await recorded.run_make(None, [])
    assert argv(recorder) == ("make",)
    await recorded.run_npm(["run", "build"])
    assert argv(recorder) == ("npm", "run", "build")
    await recorded.run_composer(["install"])
    assert argv(recorder) == ("composer", "install")
    await recorded.run_git(["status"])
    assert argv(recorder) == ("git", "status")


async def test_shortcuts_are_validated_too(recorded: TerminalService) -> None:
    with pytest.raises(CommandNotAllowed, match="'git push' is not allowed"):
        await recorded.run_git(["push"])
    with pytest.raises(CommandNotAllowed, match="'npm publish' is not allowed"):
        await recorded.run_npm(["publish"])


@pytest.mark.parametrize(
    ("runner", "args", "expected"),
    [
        ("pytest", ["-x"], ("python3", "-m", "pytest", "-x")),
        ("npm", [], ("npm", "test")),
        ("npm", ["--watch=false"], ("npm", "test", "--", "--watch=false")),
        ("composer", ["--filter", "Login"], ("composer", "test", "--", "--filter", "Login")),
        ("make", [], ("make", "test")),
    ],
)
async def test_run_tests_with_a_runner(
    recorded: TerminalService,
    recorder: RecordingProvider,
    runner: TestRunner,
    args: Sequence[str],
    expected: tuple[str, ...],
) -> None:
    await recorded.run_tests(runner, args)
    assert argv(recorder) == expected


@pytest.mark.parametrize(
    ("marker", "program"),
    [
        ("pyproject.toml", "python3"),
        ("package.json", "npm"),
        ("composer.json", "composer"),
        ("Makefile", "make"),
    ],
)
async def test_run_tests_detects_the_runner(
    recorded: TerminalService, recorder: RecordingProvider, workspace: Path, marker: str, program: str
) -> None:
    (workspace / "src" / marker).write_text("")
    await recorded.run_tests(options=CommandOptions(working_directory="src"))
    assert argv(recorder)[0] == program


async def test_run_tests_without_a_known_project(recorded: TerminalService) -> None:
    with pytest.raises(InvalidCommand, match="No test runner detected"):
        await recorded.run_tests()


async def test_process_request(
    recorded: TerminalService, recorder: RecordingProvider, workspace: Path
) -> None:
    await recorded.execute_command(
        "echo hi", CommandOptions(working_directory="src", timeout=3, env={"DEBUG": "1"})
    )
    request = recorder.requests[-1]
    assert request.cwd == (workspace / "src").resolve()
    assert request.timeout == 3
    assert request.max_output_bytes == 1000
    # Host variables: only the inherited ones (never the API key), then fixed and requested ones.
    assert request.env["PATH"] == "/usr/bin" and request.env["HOME"] == "/home/me"
    assert "OPENAI_API_KEY" not in request.env
    assert request.env["NO_COLOR"] == request.env["DEBUG"] == "1"
    assert request.env["GIT_TERMINAL_PROMPT"] == "0"


async def test_truncated_output_is_marked(make_service: MakeService) -> None:
    long = ProcessResult(
        exit_code=0,
        stdout=StreamOutput(head=b"first", tail=b"last", total_bytes=109),
        stderr=StreamOutput(b""),
        timed_out=False,
        duration=0.1,
    )
    result = await make_service(RecordingProvider(long)).execute_command("echo")
    assert result.truncated
    assert result.stdout == "first\n[... 100 bytes omitted ...]\nlast"


async def test_os_errors_are_translated(make_service: MakeService) -> None:
    class Broken(RecordingProvider):
        async def run(self, request: ProcessRequest) -> ProcessResult:
            raise OSError(7, "Argument list too long")

    with pytest.raises(TerminalError, match="Cannot start 'echo': Argument list too long"):
        await make_service(Broken()).execute_command("echo")
