"""Errors of the terminal capability. Messages are written to be shown to the LLM.

A command that runs and fails (non-zero exit code, timeout) is *not* an error: it is a normal
:class:`CommandResult` whose output the agent needs to read.
"""


class TerminalError(Exception):
    """Base class. Any terminal failure the caller should see."""


class InvalidCommand(TerminalError):
    """Malformed request: empty or unparsable command, shell syntax, bad timeout or variable."""


class CommandNotAllowed(TerminalError):
    """The program, subcommand, argument or environment variable is refused by the policy."""


class WorkspaceViolation(TerminalError):
    """The working directory or a path argument is outside the workspace, or is a secret."""


class CommandNotFound(TerminalError):
    """The program is allowed but not installed (not on PATH)."""


class CommandPermissionDenied(TerminalError):
    """The operating system refused to execute the program."""
