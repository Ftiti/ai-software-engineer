"""Terminal provider backed by local subprocesses (POSIX).

Each command starts in its own process group, so stopping it (timeout or cancellation) also
stops the processes it spawned: ``make`` -> ``pytest`` -> workers.
"""

import asyncio
import contextlib
import os
import signal
import time
from asyncio.subprocess import DEVNULL, PIPE, Process

from app.providers.terminal.base import ProcessRequest, ProcessResult, StreamOutput, TerminalProvider

_CHUNK = 65_536
_GRACE_SECONDS = 2.0  # between SIGTERM and SIGKILL


class LocalTerminalProvider(TerminalProvider):
    def environment(self) -> dict[str, str]:
        return dict(os.environ)

    async def run(self, request: ProcessRequest) -> ProcessResult:
        started = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *request.argv,
            cwd=request.cwd,
            env=dict(request.env),
            stdin=DEVNULL,
            stdout=PIPE,
            stderr=PIPE,
            start_new_session=True,  # own process group
        )
        stdout, stderr = _Capture(request.max_output_bytes), _Capture(request.max_output_bytes)
        finished = timed_out = False
        try:
            await asyncio.wait_for(_communicate(process, stdout, stderr), request.timeout)
            finished = True
        except TimeoutError:
            timed_out = True
        finally:
            if not finished:  # timeout, or the caller was cancelled
                await _stop(process)
        return ProcessResult(
            exit_code=process.returncode if process.returncode is not None else -signal.SIGKILL,
            stdout=stdout.result(),
            stderr=stderr.result(),
            timed_out=timed_out,
            duration=time.monotonic() - started,
        )


async def _communicate(process: Process, stdout: "_Capture", stderr: "_Capture") -> None:
    await asyncio.gather(_drain(process.stdout, stdout), _drain(process.stderr, stderr))
    await process.wait()


async def _drain(stream: asyncio.StreamReader | None, capture: "_Capture") -> None:
    if stream is None:
        return
    while chunk := await stream.read(_CHUNK):
        capture.add(chunk)


async def _stop(process: Process) -> None:
    """SIGTERM the whole process group, then SIGKILL whatever is still running."""
    _signal_group(process, signal.SIGTERM)
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(asyncio.shield(process.wait()), _GRACE_SECONDS)
    _signal_group(process, signal.SIGKILL)  # also children that ignored SIGTERM
    await process.wait()


def _signal_group(process: Process, sig: signal.Signals) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, sig)


class _Capture:
    """Keeps the first and the last ``limit / 2`` bytes of a stream, whatever its length."""

    def __init__(self, limit: int) -> None:
        self._head_limit = limit // 2 + limit % 2
        self._tail_limit = limit // 2
        self._head = bytearray()
        self._tail = bytearray()
        self._total = 0

    def add(self, chunk: bytes) -> None:
        self._total += len(chunk)
        room = self._head_limit - len(self._head)
        if room > 0:
            self._head += chunk[:room]
            chunk = chunk[room:]
        if chunk and self._tail_limit:
            self._tail += chunk
            del self._tail[: max(0, len(self._tail) - self._tail_limit)]

    def result(self) -> StreamOutput:
        return StreamOutput(head=bytes(self._head), tail=bytes(self._tail), total_bytes=self._total)
