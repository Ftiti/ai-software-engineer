"""Terminal provider contract: start a process and capture what it prints, no rules.

A provider runs exactly the argument vector it is given (never through a shell) and raises
``OSError`` when the process cannot be started (``FileNotFoundError``: program not found,
``PermissionError``: not executable). Allowed commands, workspace confinement and limits are
enforced above it, by the terminal capability's validator.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProcessRequest:
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]  # the complete environment of the process
    timeout: float  # seconds; the process is stopped when it is reached
    max_output_bytes: int  # per stream; beyond it only the beginning and the end are kept


@dataclass(frozen=True, slots=True)
class StreamOutput:
    """Captured stream. When it was too long, ``head`` + ``tail`` is less than ``total_bytes``."""

    head: bytes
    tail: bytes = b""
    total_bytes: int = 0

    @property
    def truncated(self) -> bool:
        return self.total_bytes > len(self.head) + len(self.tail)

    def text(self) -> str:
        """Decoded UTF-8 text (invalid bytes replaced), with a marker where the middle was cut."""
        head = self.head.decode("utf-8", errors="replace")
        tail = self.tail.decode("utf-8", errors="replace")
        if not self.truncated:
            return head + tail
        omitted = self.total_bytes - len(self.head) - len(self.tail)
        return f"{head}\n[... {omitted} bytes omitted ...]\n{tail}"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    exit_code: int  # negative: killed by that signal (POSIX)
    stdout: StreamOutput
    stderr: StreamOutput
    timed_out: bool
    duration: float  # seconds


class TerminalProvider(ABC):
    @abstractmethod
    def environment(self) -> dict[str, str]:
        """The environment of the host process (callers decide which variables to pass on)."""

    @abstractmethod
    async def run(self, request: ProcessRequest) -> ProcessResult:
        """Run the process to completion or timeout. Standard input is empty (no prompts).

        If the awaiting task is cancelled, the process and its children are stopped before
        the cancellation propagates.
        """
