"""Assembles the terminal capability: provider -> validator -> executor -> service -> tools."""

from app.capabilities.base import Capability
from app.capabilities.filesystem import PathValidator
from app.capabilities.terminal.executor import CommandExecutor
from app.capabilities.terminal.prompts import TERMINAL_PROMPT
from app.capabilities.terminal.service import TerminalService
from app.capabilities.terminal.tool import terminal_tools
from app.capabilities.terminal.validator import CommandValidator, TerminalPolicy
from app.config import Settings
from app.providers.terminal import LocalTerminalProvider, TerminalProvider


def build_terminal_service(
    settings: Settings, paths: PathValidator, provider: TerminalProvider | None = None
) -> TerminalService:
    """``paths`` is the filesystem validator: commands are confined to the same workspace."""
    policy = TerminalPolicy.from_settings(settings)
    executor = CommandExecutor(provider or LocalTerminalProvider(), policy)
    return TerminalService(CommandValidator(paths, policy), executor, python=settings.terminal_python)


def build_terminal_capability(service: TerminalService) -> Capability:
    return Capability(name="terminal", tools=terminal_tools(service), prompt=TERMINAL_PROMPT)
