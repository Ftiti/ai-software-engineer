"""Terminal providers: the only code allowed to start operating-system processes."""

from app.providers.terminal.base import ProcessRequest, ProcessResult, StreamOutput, TerminalProvider
from app.providers.terminal.environment import NON_INTERACTIVE_ENV, process_environment
from app.providers.terminal.local import LocalTerminalProvider

__all__ = [
    "NON_INTERACTIVE_ENV",
    "LocalTerminalProvider",
    "ProcessRequest",
    "ProcessResult",
    "StreamOutput",
    "TerminalProvider",
    "process_environment",
]
