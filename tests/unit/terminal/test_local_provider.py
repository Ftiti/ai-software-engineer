"""LocalTerminalProvider: real processes, output capture, timeout, cancellation."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

from app.providers.terminal import LocalTerminalProvider, ProcessRequest

PYTHON = sys.executable


def request(cwd: Path, *code: str, timeout: float = 10, limit: int = 10_000, **env: str) -> ProcessRequest:
    return ProcessRequest(
        argv=(PYTHON, "-c", "\n".join(code)),
        cwd=cwd,
        env={"PATH": os.environ["PATH"], **env},
        timeout=timeout,
        max_output_bytes=limit,
    )


@pytest.fixture
def provider() -> LocalTerminalProvider:
    return LocalTerminalProvider()


async def test_captures_stdout_stderr_and_exit_code(provider: LocalTerminalProvider, tmp_path: Path) -> None:
    result = await provider.run(
        request(tmp_path, "import sys", "print('out')", "print('err', file=sys.stderr)", "sys.exit(4)")
    )
    assert (result.exit_code, result.timed_out) == (4, False)
    assert result.stdout.head == b"out\n"
    assert result.stderr.head == b"err\n"
    assert result.duration > 0


async def test_runs_in_the_working_directory_with_only_the_given_environment(
    provider: LocalTerminalProvider, tmp_path: Path
) -> None:
    result = await provider.run(
        request(
            tmp_path,
            "import os",
            "print(os.getcwd())",
            "print(os.environ.get('HOME'))",
            "print(os.environ['A'])",
            A="1",
        )
    )
    assert result.stdout.head.decode().splitlines() == [str(tmp_path), "None", "1"]


async def test_stdin_is_empty(provider: LocalTerminalProvider, tmp_path: Path) -> None:
    result = await provider.run(request(tmp_path, "import sys", "print(repr(sys.stdin.read()))"))
    assert result.stdout.head == b"''\n"


async def test_timeout_stops_the_process_and_keeps_partial_output(
    provider: LocalTerminalProvider, tmp_path: Path
) -> None:
    result = await provider.run(
        request(tmp_path, "import time", "print('started', flush=True)", "time.sleep(30)", timeout=0.5)
    )
    assert result.timed_out
    assert result.exit_code < 0  # killed by a signal
    assert result.stdout.head == b"started\n"
    assert result.duration < 5


async def test_timeout_also_stops_child_processes(provider: LocalTerminalProvider, tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    child = "import time; time.sleep(30)"
    code = (
        "import subprocess, sys, time",
        f"p = subprocess.Popen([sys.executable, '-c', {child!r}])",
        f"open({str(pid_file)!r}, 'w').write(str(p.pid))",
        "time.sleep(30)",
    )
    result = await provider.run(request(tmp_path, *code, timeout=1))
    assert result.timed_out
    await _assert_dead(int(pid_file.read_text()))


async def test_cancellation_stops_the_process(provider: LocalTerminalProvider, tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    code = ("import os, time", f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))", "time.sleep(30)")
    task = asyncio.create_task(provider.run(request(tmp_path, *code, timeout=30)))
    while not pid_file.exists() or not pid_file.read_text():
        await asyncio.sleep(0.05)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await _assert_dead(int(pid_file.read_text()))


async def test_long_output_keeps_beginning_and_end(provider: LocalTerminalProvider, tmp_path: Path) -> None:
    result = await provider.run(request(tmp_path, "print('a' * 5000 + 'END', end='')", limit=100))
    out = result.stdout
    assert out.truncated
    assert out.total_bytes == 5003
    assert (len(out.head), len(out.tail)) == (50, 50)
    assert out.tail.endswith(b"END")


async def test_missing_program(provider: LocalTerminalProvider, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        await provider.run(ProcessRequest(("no-such-program-xyz",), tmp_path, os.environ, 5, 100))


async def test_not_executable(provider: LocalTerminalProvider, tmp_path: Path) -> None:
    script = tmp_path / "script"
    script.write_text("#!/bin/sh\necho hi\n")
    script.chmod(0o644)
    with pytest.raises(PermissionError):
        await provider.run(ProcessRequest((str(script),), tmp_path, os.environ, 5, 100))


async def _assert_dead(pid: int) -> None:
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        if _is_zombie(pid):  # killed, waiting for its parent (already gone) to be reaped by init
            return
        await asyncio.sleep(0.05)
    pytest.fail(f"process {pid} is still running")


def _is_zombie(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().split()[2] == "Z"
    except OSError:
        return False
