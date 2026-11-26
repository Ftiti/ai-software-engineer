"""Filesystem service on a real temporary workspace, plus a mocked provider for isolation."""

from pathlib import Path
from typing import Any
from unittest.mock import create_autospec

import pytest

from app.capabilities.filesystem import FilesystemService, PathValidator
from app.capabilities.filesystem.exceptions import (
    AccessDenied,
    DirectoryNotFound,
    FileAlreadyExists,
    FileNotFound,
    FilesystemError,
    FileTooLarge,
    NotAFile,
    UnsupportedFile,
)
from app.providers.filesystem import FilesystemProvider, LocalFilesystemProvider
from tests.unit.filesystem.conftest import MakePolicy, MakeService

# -- list_directory -------------------------------------------------------------------------


def test_list_root_hides_secrets(service: FilesystemService) -> None:
    listing = service.list_directory(".")
    assert listing.path == "."
    assert [(e.path, e.type) for e in listing.entries] == [
        (".git", "directory"),
        ("README.md", "file"),
        ("node_modules", "directory"),
        ("src", "directory"),
    ]
    assert listing.entries[1].size == len("# Demo\n")
    assert not listing.truncated


def test_list_recursive_skips_ignored_directories(service: FilesystemService) -> None:
    paths = [e.path for e in service.list_directory(".", recursive=True).entries]
    assert "src/utils/helpers.py" in paths
    assert "node_modules" in paths  # listed...
    assert "node_modules/lib.js" not in paths  # ...but not descended into
    assert ".git/config" not in paths
    assert ".env" not in paths


def test_list_subdirectory(service: FilesystemService) -> None:
    assert [e.path for e in service.list_directory("src").entries] == ["src/app.py", "src/utils"]


def test_list_is_truncated_at_the_limit(make_service: MakeService) -> None:
    listing = make_service(max_list_entries=2).list_directory(".", recursive=True)
    assert len(listing.entries) == 2
    assert listing.truncated


def test_list_errors(service: FilesystemService) -> None:
    with pytest.raises(DirectoryNotFound):
        service.list_directory("nope")
    with pytest.raises(AccessDenied):
        service.list_directory("..")


# -- read_file ------------------------------------------------------------------------------


def test_read_file(service: FilesystemService) -> None:
    result = service.read_file("src/app.py")
    assert (result.path, result.content, result.size) == ("src/app.py", "print('hi')\n", 12)


def test_read_errors(service: FilesystemService, make_service: MakeService, workspace: Path) -> None:
    with pytest.raises(FileNotFound):
        service.read_file("missing.py")
    with pytest.raises(NotAFile):
        service.read_file("src")
    with pytest.raises(AccessDenied):
        service.read_file(".env")
    with pytest.raises(FileTooLarge):
        make_service(max_read_bytes=3).read_file("README.md")

    (workspace / "image.png").write_bytes(b"\x89PNG\x00\x00")
    (workspace / "latin1.txt").write_bytes("café".encode("latin-1"))
    with pytest.raises(UnsupportedFile, match="binary"):
        service.read_file("image.png")
    with pytest.raises(UnsupportedFile, match="UTF-8"):
        service.read_file("latin1.txt")


# -- write_file / create_file ---------------------------------------------------------------


def test_write_creates_file_and_parents(service: FilesystemService, workspace: Path) -> None:
    result = service.write_file("docs/guide/intro.md", "Hello ✓\n")
    assert result.created
    assert result.bytes_written == len("Hello ✓\n".encode())
    assert (workspace / "docs" / "guide" / "intro.md").read_text() == "Hello ✓\n"


def test_write_replaces_existing_file(service: FilesystemService, workspace: Path) -> None:
    result = service.write_file("README.md", "# New\n")
    assert not result.created
    assert (workspace / "README.md").read_text() == "# New\n"


def test_write_errors(service: FilesystemService, make_service: MakeService) -> None:
    with pytest.raises(NotAFile):
        service.write_file("src", "x")
    with pytest.raises(AccessDenied, match="protected"):
        service.write_file(".git/config", "x")
    with pytest.raises(AccessDenied, match="outside"):
        service.write_file("../evil.sh", "x")
    with pytest.raises(FileTooLarge):
        make_service(max_write_bytes=3).write_file("a.txt", "four")
    with pytest.raises(AccessDenied, match="read-only"):
        make_service(read_only=True).write_file("a.txt", "x")


def test_create_file(service: FilesystemService, workspace: Path) -> None:
    assert service.create_file("new.py", "x = 1\n").created
    assert (workspace / "new.py").read_text() == "x = 1\n"
    with pytest.raises(FileAlreadyExists):
        service.create_file("README.md")


# -- delete, mkdir, move, copy --------------------------------------------------------------


def test_delete_file(service: FilesystemService, workspace: Path) -> None:
    assert service.delete_file("src/app.py").detail == "deleted"
    assert not (workspace / "src" / "app.py").exists()
    with pytest.raises(FileNotFound):
        service.delete_file("src/app.py")
    with pytest.raises(NotAFile):
        service.delete_file("src")


def test_create_directory(service: FilesystemService, workspace: Path) -> None:
    service.create_directory("tests/unit")
    assert (workspace / "tests" / "unit").is_dir()
    with pytest.raises(FileAlreadyExists):
        service.create_directory("src")


def test_move_and_copy(service: FilesystemService, workspace: Path) -> None:
    service.copy_file("README.md", "docs.md")
    assert (workspace / "docs.md").read_text() == "# Demo\n"

    service.move_file("docs.md", "src/docs.md")
    assert not (workspace / "docs.md").exists()
    assert (workspace / "src" / "docs.md").read_text() == "# Demo\n"

    with pytest.raises(FileAlreadyExists):
        service.copy_file("README.md", "src/docs.md")
    service.copy_file("README.md", "src/docs.md", overwrite=True)
    with pytest.raises(FilesystemError, match="same file"):
        service.move_file("README.md", "./README.md", overwrite=True)
    with pytest.raises(AccessDenied):
        service.copy_file(".env", "leak.txt")


# -- Isolation: the service only talks to the OS through the provider -------------------------


@pytest.fixture
def provider() -> Any:
    """Mock provider: path queries go to the real OS, every action is recorded but not run."""
    real = LocalFilesystemProvider()
    mock = create_autospec(FilesystemProvider, instance=True)
    mock.resolve.side_effect = real.resolve
    mock.exists.side_effect = real.exists
    mock.stat.side_effect = real.stat
    return mock


def test_service_uses_only_the_provider(make_policy: MakePolicy, provider: Any) -> None:
    service = FilesystemService(provider, PathValidator(provider, make_policy()))

    service.write_file("out.txt", "data")

    provider.write_bytes.assert_called_once()
    path, data = provider.write_bytes.call_args.args
    assert path.name == "out.txt" and data == b"data"


def test_validation_failure_never_reaches_the_provider(make_policy: MakePolicy, provider: Any) -> None:
    service = FilesystemService(provider, PathValidator(provider, make_policy()))

    with pytest.raises(AccessDenied):
        service.write_file("../../etc/passwd", "pwned")
    provider.write_bytes.assert_not_called()


def test_os_errors_are_translated(make_policy: MakePolicy, provider: Any) -> None:
    provider.read_bytes.side_effect = PermissionError(13, "Permission denied")
    service = FilesystemService(provider, PathValidator(provider, make_policy()))

    with pytest.raises(AccessDenied, match=r"Permission denied by the operating system: 'README\.md'"):
        service.read_file("README.md")
