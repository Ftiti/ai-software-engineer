"""Git provider contract: run the git executable with given arguments, no rules.

A provider executes exactly the arguments it is given in the given repository and returns what
git printed. It raises ``OSError`` when git cannot be started (``FileNotFoundError``: not
installed). Which operations are allowed, and with which arguments, is decided above it by the
Git capability's validator and service.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GitInvocation:
    repository: Path  # absolute working directory of the git process
    args: tuple[str, ...]  # sub-command and its arguments, e.g. ("status", "--porcelain=v2")
    timeout: float  # seconds
    max_output_bytes: int  # per stream


@dataclass(frozen=True, slots=True)
class GitOutput:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool  # the middle of stdout or stderr was cut

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class GitProvider(ABC):
    @abstractmethod
    async def run(self, invocation: GitInvocation) -> GitOutput:
        """Run ``git <args>`` in ``invocation.repository`` (no shell, no input, no prompts)."""
