"""Terminal capability: safe command execution in the workspace.

tool.py ─► service.py ─► validator.py (rules) ─► executor.py ─► providers/terminal (OS)
"""

from app.capabilities.terminal.capability import build_terminal_capability, build_terminal_service
from app.capabilities.terminal.executor import CommandExecutor
from app.capabilities.terminal.service import TerminalService
from app.capabilities.terminal.validator import CommandValidator, TerminalPolicy, ValidatedCommand

__all__ = [
    "CommandExecutor",
    "CommandValidator",
    "TerminalPolicy",
    "TerminalService",
    "ValidatedCommand",
    "build_terminal_capability",
    "build_terminal_service",
]
