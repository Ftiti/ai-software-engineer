"""LocalGitProvider: what it asks the terminal provider to run, and a real round trip."""

from pathlib import Path

import pytest

from app.providers.git import GitInvocation, LocalGitProvider
from app.providers.terminal import (
    LocalTerminalProvider,
    ProcessRequest,
    ProcessResult,
    StreamOutput,
    TerminalProvider,
)


class RecordingTerminal(TerminalProvider):
    def __init__(self) -> None:
        self.requests: list[ProcessRequest] = []

    def environment(self) -> dict[str, str]:
        return {
            "PATH": "/usr/bin",
            "HOME": "/home/me",
            "OPENAI_API_KEY": "sk-secret",
            "GITHUB_TOKEN": "ghp_x",
        }

    async def run(self, request: ProcessRequest) -> ProcessResult:
        self.requests.append(request)
        return ProcessResult(0, StreamOutput(b"out"), StreamOutput(b"err"), timed_out=False, duration=0.01)


def invocation(repo: Path, *args: str) -> GitInvocation:
    return GitInvocation(repository=repo, args=args, timeout=7, max_output_bytes=500)


async def test_request_built_for_the_terminal_provider(tmp_path: Path) -> None:
    terminal = RecordingTerminal()
    output = await LocalGitProvider(terminal, inherited_env=("PATH", "HOME")).run(
        invocation(tmp_path, "status")
    )

    request = terminal.requests[0]
    assert request.argv == (
        "git",
        "--no-pager",
        "--literal-pathspecs",
        "-c",
        "color.ui=never",
        "-c",
        "core.quotepath=off",
        "status",
    )
    assert (request.cwd, request.timeout, request.max_output_bytes) == (tmp_path, 7, 500)
    assert (output.stdout, output.stderr, output.ok) == ("out", "err", True)


async def test_environment_is_non_interactive_and_has_no_secrets(tmp_path: Path) -> None:
    terminal = RecordingTerminal()
    await LocalGitProvider(terminal, inherited_env=("PATH", "HOME")).run(invocation(tmp_path, "status"))
    env = terminal.requests[0].env
    assert env["HOME"] == "/home/me"  # the developer's identity and credential helper still apply
    assert "OPENAI_API_KEY" not in env and "GITHUB_TOKEN" not in env
    assert (env["GIT_TERMINAL_PROMPT"], env["GIT_EDITOR"], env["GIT_PAGER"]) == ("0", "true", "cat")


async def test_hooks_can_be_disabled(tmp_path: Path) -> None:
    terminal = RecordingTerminal()
    await LocalGitProvider(terminal, hooks=False, executable="/opt/git").run(invocation(tmp_path, "commit"))
    argv = terminal.requests[0].argv
    assert argv[0] == "/opt/git"
    assert argv[-3:] == ("-c", "core.hooksPath=/dev/null", "commit")


async def test_real_git(repo: Path) -> None:
    provider = LocalGitProvider(LocalTerminalProvider(), inherited_env=("PATH", "HOME"))
    output = await provider.run(invocation(repo, "rev-parse", "--abbrev-ref", "HEAD"))
    assert (output.exit_code, output.stdout.strip()) == (0, "main")
    failed = await provider.run(invocation(repo, "rev-parse", "--verify", "no-such-ref"))
    assert failed.exit_code != 0 and not failed.ok


async def test_git_not_installed(tmp_path: Path) -> None:
    provider = LocalGitProvider(
        LocalTerminalProvider(), executable="no-such-git-xyz", inherited_env=("PATH",)
    )
    with pytest.raises(FileNotFoundError):
        await provider.run(invocation(tmp_path, "status"))
