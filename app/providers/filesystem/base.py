"""Filesystem provider contract: raw operating-system access, no rules.

A provider performs exactly what it is asked on absolute paths and raises ``OSError`` on
failure. Workspace confinement, permissions and limits are enforced above it, by the
filesystem capability's validator and service.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileStat:
    size: int
    is_file: bool
    is_dir: bool
    modified: float  # POSIX timestamp


@dataclass(frozen=True, slots=True)
class DirEntry:
    name: str
    is_file: bool
    is_dir: bool
    is_symlink: bool
    size: int | None  # files only


class FilesystemProvider(ABC):
    @abstractmethod
    def resolve(self, path: Path) -> Path:
        """Absolute real path: ``..`` collapsed and symlinks followed. The path may not exist."""

    @abstractmethod
    def exists(self, path: Path) -> bool: ...

    @abstractmethod
    def stat(self, path: Path) -> FileStat: ...

    @abstractmethod
    def list_dir(self, path: Path) -> list[DirEntry]:
        """Entries of a directory, sorted by name."""

    @abstractmethod
    def read_bytes(self, path: Path) -> bytes: ...

    @abstractmethod
    def write_bytes(self, path: Path, data: bytes, *, create_parents: bool = False) -> None:
        """Write atomically: readers see either the old or the new content, never a mix."""

    @abstractmethod
    def make_dir(self, path: Path) -> None:
        """Create a directory and any missing parents."""

    @abstractmethod
    def delete_file(self, path: Path) -> None: ...

    @abstractmethod
    def move(self, source: Path, destination: Path) -> None: ...

    @abstractmethod
    def copy_file(self, source: Path, destination: Path) -> None: ...
