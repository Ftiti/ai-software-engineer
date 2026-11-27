"""CommandValidator: parsing, whitelist/blacklist, subcommands, workspace, timeout, environment."""

import re
from dataclasses import replace
from pathlib import Path

import pytest

from app.capabilities.filesystem import PathValidator
from app.capabilities.terminal import CommandValidator
from app.capabilities.terminal.exceptions import (
    CommandNotAllowed,
    InvalidCommand,
    TerminalError,
    WorkspaceViolation,
)
from tests.unit.terminal.conftest import POLICY

# -- Parsing --------------------------------------------------------------------------------


def test_parse_uses_posix_quoting(validator: CommandValidator) -> None:
    assert validator.parse("python3 -c 'print(1)' \"a b\"") == ["python3", "-c", "print(1)", "a b"]


@pytest.mark.parametrize(
    ("command", "error"),
    [
        ("echo 'unclosed", "Cannot parse"),
        ("ls | wc -l", "Shell operators are not supported (|)"),
        ("ls && rm -rf .", "Shell operators are not supported (&&)"),
        ("echo hi > out.txt", "(>)"),
        ("echo a ; echo b", "(;)"),
    ],
)
def test_parse_refuses_shell_syntax(validator: CommandValidator, command: str, error: str) -> None:
    with pytest.raises(InvalidCommand, match=re.escape(error)):
        validator.parse(command)


def test_quoted_operator_is_a_plain_argument(validator: CommandValidator) -> None:
    assert validator.parse("echo 'a | b'") == ["echo", "a | b"]


@pytest.mark.parametrize("argv", [[], [""], ["  "]])
def test_empty_command(validator: CommandValidator, argv: list[str]) -> None:
    with pytest.raises(InvalidCommand, match="empty"):
        validator.validate(argv)


def test_nul_byte(validator: CommandValidator) -> None:
    with pytest.raises(InvalidCommand, match="NUL"):
        validator.validate(["echo", "a\x00b"])


# -- Programs -------------------------------------------------------------------------------


def test_allowed_command(validator: CommandValidator) -> None:
    command = validator.validate(["echo", "hi"])
    assert command.argv == ("echo", "hi")
    assert command.working_directory.relative == "."


@pytest.mark.parametrize(
    ("argv", "error"),
    [
        (["rm", "-rf", "."], "'rm' is blocked"),
        (["bash", "-c", "ls"], "'bash' is blocked"),
        (["curl", "http://example.com"], "'curl' is not an allowed command"),
        (["/bin/ls"], "not a path"),
        (["./hello.py"], "not a path"),
    ],
)
def test_programs_refused(validator: CommandValidator, argv: list[str], error: str) -> None:
    with pytest.raises(CommandNotAllowed, match=error):
        validator.validate(argv)


def test_wildcard_allows_everything_but_the_blacklist(paths: PathValidator) -> None:
    validator = CommandValidator(paths, replace(POLICY, allowed_commands=("*",)))
    assert validator.validate(["whoami"]).argv == ("whoami",)
    with pytest.raises(CommandNotAllowed, match="blocked"):
        validator.validate(["rm", "x"])


@pytest.mark.parametrize("argv", [["git", "status"], ["git", "log", "-n", "3"], ["npm", "run", "build"]])
def test_allowed_subcommands(validator: CommandValidator, argv: list[str]) -> None:
    assert validator.validate(argv).argv == tuple(argv)


@pytest.mark.parametrize(
    ("argv", "error"),
    [
        (["git", "push", "--force"], "'git push' is not allowed. Allowed git subcommands: status, log"),
        (["git"], "'git' is not allowed"),
        (["git", "-c", "core.pager=sh", "status"], "'git -c' is not allowed"),
        (["npm", "publish"], "'npm publish' is not allowed"),
        (["git", "log", "--exec=evil"], "argument '--exec=evil' is not allowed"),
    ],
)
def test_subcommands_and_arguments_refused(validator: CommandValidator, argv: list[str], error: str) -> None:
    with pytest.raises(CommandNotAllowed, match=error):
        validator.validate(argv)


# -- Workspace ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "error"),
    [
        (["ls", "/etc"], "outside the workspace"),
        (["ls", "../.."], "outside the workspace"),
        (["python3", "--log=../../x.log"], "outside the workspace"),
        (["python3", ".env"], "protected secret"),
        (["python3", "src/../.env"], "protected secret"),
        (["python3", "--env-file=.env"], "protected secret"),
    ],
)
def test_path_arguments_stay_in_the_workspace(
    validator: CommandValidator, argv: list[str], error: str
) -> None:
    with pytest.raises(WorkspaceViolation, match=error):
        validator.validate(argv)


def test_paths_inside_the_workspace_are_accepted(validator: CommandValidator, workspace: Path) -> None:
    validator.validate(["ls", "src/../hello.py", str(workspace / "src")])
    validator.validate(["ls", ".."], working_directory="src")  # back to the root: still inside


def test_working_directory(validator: CommandValidator) -> None:
    assert validator.validate(["ls"], working_directory="src").working_directory.relative == "src"


@pytest.mark.parametrize(
    ("directory", "kind", "error"),
    [
        ("..", WorkspaceViolation, "outside the workspace"),
        ("/tmp", WorkspaceViolation, "outside the workspace"),
        (".env", WorkspaceViolation, "protected secret"),
        ("missing", InvalidCommand, "does not exist"),
        ("hello.py", InvalidCommand, "not a directory"),
    ],
)
def test_working_directory_refused(
    validator: CommandValidator, directory: str, kind: type[TerminalError], error: str
) -> None:
    with pytest.raises(kind, match=error):
        validator.validate(["ls"], working_directory=directory)


# -- Timeout and environment ----------------------------------------------------------------


def test_timeout(validator: CommandValidator) -> None:
    assert validator.validate(["ls"]).timeout == POLICY.default_timeout
    assert validator.validate(["ls"], timeout=5).timeout == 5
    with pytest.raises(InvalidCommand, match=r"exceeds the maximum of 20\.0s"):
        validator.validate(["ls"], timeout=21)
    with pytest.raises(InvalidCommand, match="positive"):
        validator.validate(["ls"], timeout=0)


def test_environment(validator: CommandValidator) -> None:
    assert validator.validate(["ls"], env={"DEBUG": "1"}).env == {"DEBUG": "1"}


@pytest.mark.parametrize(
    ("env", "kind", "error"),
    [
        ({"1BAD": "x"}, InvalidCommand, "Invalid environment variable name"),
        ({"A B": "x"}, InvalidCommand, "Invalid environment variable name"),
        ({"PATH": "/tmp/evil"}, CommandNotAllowed, "'PATH' cannot be set"),
        ({"LD_PRELOAD": "evil.so"}, CommandNotAllowed, "'LD_PRELOAD' cannot be set"),
        ({"OK": "a\x00b"}, InvalidCommand, "NUL"),
    ],
)
def test_environment_refused(
    validator: CommandValidator, env: dict[str, str], kind: type[TerminalError], error: str
) -> None:
    with pytest.raises(kind, match=error):
        validator.validate(["ls"], env=env)
