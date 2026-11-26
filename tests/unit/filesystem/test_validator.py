"""Safety rules: workspace confinement, traversal, symlinks, secrets, protection, limits."""

import os
from pathlib import Path

import pytest

from app.capabilities.filesystem import Operation, PathValidator
from app.capabilities.filesystem.exceptions import (
    AccessDenied,
    DirectoryNotFound,
    FileAlreadyExists,
    FileNotFound,
    FileTooLarge,
    InvalidPath,
    NotADirectory,
    NotAFile,
)
from app.providers.filesystem import LocalFilesystemProvider
from tests.unit.filesystem.conftest import MakePolicy


@pytest.fixture
def validator(make_policy: MakePolicy) -> PathValidator:
    return PathValidator(LocalFilesystemProvider(), make_policy())


# -- Workspace confinement ------------------------------------------------------------------


@pytest.mark.parametrize("path", ["README.md", "./README.md", "src/../README.md", "src/./app.py"])
def test_paths_inside_workspace_are_resolved(validator: PathValidator, path: str) -> None:
    resolved = validator.resolve(path, Operation.READ)
    assert resolved.absolute.is_relative_to(validator.workspace_root)
    assert not resolved.relative.startswith("..")


def test_relative_path_is_normalised(validator: PathValidator) -> None:
    assert validator.resolve("src/utils/../app.py", Operation.READ).relative == "src/app.py"
    assert validator.resolve(".", Operation.LIST).relative == "."


@pytest.mark.parametrize("path", ["../outside.txt", "../../etc/passwd", "src/../../x", "/etc/passwd"])
def test_paths_escaping_the_workspace_are_denied(validator: PathValidator, path: str) -> None:
    with pytest.raises(AccessDenied, match="outside the workspace"):
        validator.resolve(path, Operation.READ)


def test_absolute_path_inside_workspace_is_accepted(validator: PathValidator, workspace: Path) -> None:
    assert validator.resolve(str(workspace / "README.md"), Operation.READ).relative == "README.md"


def test_symlink_pointing_outside_is_denied(
    validator: PathValidator, workspace: Path, tmp_path: Path
) -> None:
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("top secret")
    os.symlink(secret, workspace / "innocent.txt")

    with pytest.raises(AccessDenied, match="outside the workspace"):
        validator.resolve("innocent.txt", Operation.READ)


def test_symlinked_directory_pointing_outside_is_denied(
    validator: PathValidator, workspace: Path, tmp_path: Path
) -> None:
    os.symlink(tmp_path, workspace / "escape")
    with pytest.raises(AccessDenied):
        validator.resolve("escape/anything.txt", Operation.WRITE)


@pytest.mark.parametrize(("path", "message"), [("", "empty"), ("   ", "empty"), ("a\x00b", "NUL")])
def test_malformed_paths(validator: PathValidator, path: str, message: str) -> None:
    with pytest.raises(InvalidPath, match=message):
        validator.resolve(path, Operation.READ)


def test_workspace_root_must_be_a_directory(make_policy: MakePolicy, workspace: Path) -> None:
    with pytest.raises(DirectoryNotFound):
        PathValidator(LocalFilesystemProvider(), make_policy(workspace_root=workspace / "missing"))


# -- Allowed operations ---------------------------------------------------------------------


@pytest.mark.parametrize("operation", list(Operation))
@pytest.mark.parametrize("path", [".env", "certs/server.pem"])
def test_secrets_are_denied_for_every_operation(
    validator: PathValidator, path: str, operation: Operation
) -> None:
    with pytest.raises(AccessDenied, match="secret"):
        validator.resolve(path, operation)


def test_protected_paths_are_readable_but_not_writable(validator: PathValidator) -> None:
    assert validator.resolve(".git/config", Operation.READ).relative == ".git/config"
    for operation in (Operation.WRITE, Operation.DELETE, Operation.MOVE, Operation.CREATE):
        with pytest.raises(AccessDenied, match="protected"):
            validator.resolve(".git/config", operation)


def test_read_only_mode_allows_only_reading(make_policy: MakePolicy) -> None:
    validator = PathValidator(LocalFilesystemProvider(), make_policy(read_only=True))
    validator.resolve("README.md", Operation.READ)
    validator.resolve(".", Operation.LIST)
    with pytest.raises(AccessDenied, match="read-only"):
        validator.resolve("README.md", Operation.WRITE)


def test_workspace_root_cannot_be_modified(validator: PathValidator) -> None:
    with pytest.raises(AccessDenied, match="workspace root"):
        validator.resolve(".", Operation.DELETE)


def test_patterns_match_any_path_component(validator: PathValidator) -> None:
    assert validator.is_denied("config/.env")
    assert validator.is_ignored("packages/web/node_modules/react/index.js")
    assert not validator.is_denied(".env.example")
    assert not validator.is_denied(".")


# -- Existence, type and size ---------------------------------------------------------------


def test_existence_and_type_checks(validator: PathValidator) -> None:
    readme = validator.resolve("README.md", Operation.READ)
    src = validator.resolve("src", Operation.LIST)
    missing = validator.resolve("missing.txt", Operation.READ)

    assert validator.require_file(readme).size == len("# Demo\n")
    validator.require_directory(src)
    validator.require_absent(missing)

    with pytest.raises(FileNotFound):
        validator.require_file(missing)
    with pytest.raises(NotAFile):
        validator.require_file(src)
    with pytest.raises(DirectoryNotFound):
        validator.require_directory(missing)
    with pytest.raises(NotADirectory):
        validator.require_directory(readme)
    with pytest.raises(FileAlreadyExists):
        validator.require_absent(readme)


def test_size_limits(make_policy: MakePolicy) -> None:
    validator = PathValidator(LocalFilesystemProvider(), make_policy(max_read_bytes=10, max_write_bytes=5))
    path = validator.resolve("README.md", Operation.READ)

    validator.check_read_size(path, 10)
    validator.check_write_size(path, 5)
    with pytest.raises(FileTooLarge, match="read limit is 10"):
        validator.check_read_size(path, 11)
    with pytest.raises(FileTooLarge, match="write limit is 5"):
        validator.check_write_size(path, 6)
