"""Centralised safety rules of the filesystem capability.

Every path coming from a caller (usually an LLM) goes through :meth:`PathValidator.resolve`
before anything touches the disk. The checks, in order:

1. **Well-formed**: not empty after stripping, no NUL byte.
2. **Inside the workspace**: the *real* path (``..`` collapsed, symlinks followed) must be the
   workspace root or below it. ``../../etc/passwd`` and symlinks pointing outside are refused.
3. **Not secret**: no component may match ``denied_patterns`` (``.env``, keys...), for any
   operation, including listing.
4. **Operation allowed**: mutating operations are refused in read-only mode, on paths matching
   ``protected_patterns`` (``.git``) and on the workspace root itself.

Existence, type and size checks are helpers used by the service.
"""

from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

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
from app.config import Settings
from app.providers.filesystem import FileStat, FilesystemProvider


class Operation(StrEnum):
    LIST = "list"
    READ = "read"
    WRITE = "write"
    CREATE = "create"
    DELETE = "delete"
    MKDIR = "mkdir"
    MOVE = "move"
    COPY = "copy"

    @property
    def mutating(self) -> bool:
        return self not in (Operation.LIST, Operation.READ)


@dataclass(frozen=True, slots=True)
class FilesystemPolicy:
    workspace_root: Path
    read_only: bool = False
    max_read_bytes: int = 1_048_576
    max_write_bytes: int = 1_048_576
    max_list_entries: int = 1000
    denied_patterns: tuple[str, ...] = ()
    protected_patterns: tuple[str, ...] = ()
    ignored_patterns: tuple[str, ...] = ()

    @classmethod
    def from_settings(cls, settings: Settings) -> "FilesystemPolicy":
        return cls(
            workspace_root=settings.fs_workspace_root,
            read_only=settings.fs_read_only,
            max_read_bytes=settings.fs_max_read_bytes,
            max_write_bytes=settings.fs_max_write_bytes,
            max_list_entries=settings.fs_max_list_entries,
            denied_patterns=tuple(settings.fs_denied_patterns),
            protected_patterns=tuple(settings.fs_protected_patterns),
            ignored_patterns=tuple(settings.fs_ignored_patterns),
        )


@dataclass(frozen=True, slots=True)
class ResolvedPath:
    """A validated path: ``absolute`` for the provider, ``relative`` for messages and results."""

    absolute: Path
    relative: str


class PathValidator:
    def __init__(self, provider: FilesystemProvider, policy: FilesystemPolicy) -> None:
        self._provider = provider
        self._policy = policy
        self._root = provider.resolve(policy.workspace_root)
        if not (provider.exists(self._root) and provider.stat(self._root).is_dir):
            raise DirectoryNotFound(f"Workspace root {str(policy.workspace_root)!r} is not a directory")

    @property
    def policy(self) -> FilesystemPolicy:
        return self._policy

    @property
    def workspace_root(self) -> Path:
        return self._root

    # -- Path resolution and access rules ----------------------------------------------------

    def resolve(self, path: str, operation: Operation) -> ResolvedPath:
        raw = path.strip()
        if not raw:
            raise InvalidPath("Path is empty")
        if "\x00" in raw:
            raise InvalidPath("Path contains a NUL byte")

        candidate = Path(raw)
        real = self._provider.resolve(candidate if candidate.is_absolute() else self._root / candidate)
        if real != self._root and self._root not in real.parents:
            raise AccessDenied(f"{raw!r} is outside the workspace")

        resolved = ResolvedPath(absolute=real, relative=real.relative_to(self._root).as_posix())
        self._check_operation(resolved, operation)
        return resolved

    def child(self, directory: ResolvedPath, name: str) -> ResolvedPath:
        """Entry ``name`` of an already validated directory, as listed by the provider.

        Not followed if it is a symlink: callers must not descend into symlinked directories.
        """
        relative = name if directory.relative == "." else f"{directory.relative}/{name}"
        return ResolvedPath(absolute=directory.absolute / name, relative=relative)

    def exists(self, path: ResolvedPath) -> bool:
        return self._provider.exists(path.absolute)

    def is_directory(self, path: ResolvedPath) -> bool:
        return self._provider.exists(path.absolute) and self._provider.stat(path.absolute).is_dir

    def is_denied(self, relative: str) -> bool:
        return _matches(relative, self._policy.denied_patterns)

    def is_ignored(self, relative: str) -> bool:
        return _matches(relative, self._policy.ignored_patterns)

    def _check_operation(self, path: ResolvedPath, operation: Operation) -> None:
        if self.is_denied(path.relative):
            raise AccessDenied(f"Access to {path.relative!r} is not allowed (protected secret)")
        if not operation.mutating:
            return
        if self._policy.read_only:
            raise AccessDenied(f"Cannot {operation} {path.relative!r}: the workspace is read-only")
        if path.relative == ".":
            raise AccessDenied(f"Cannot {operation} the workspace root")
        if _matches(path.relative, self._policy.protected_patterns):
            raise AccessDenied(f"Cannot {operation} {path.relative!r}: the path is protected")

    # -- Existence, type and size ------------------------------------------------------------

    def require_file(self, path: ResolvedPath) -> FileStat:
        if not self._provider.exists(path.absolute):
            raise FileNotFound(f"File {path.relative!r} does not exist")
        stat = self._provider.stat(path.absolute)
        if not stat.is_file:
            raise NotAFile(f"{path.relative!r} is not a file")
        return stat

    def require_directory(self, path: ResolvedPath) -> None:
        if not self._provider.exists(path.absolute):
            raise DirectoryNotFound(f"Directory {path.relative!r} does not exist")
        if not self._provider.stat(path.absolute).is_dir:
            raise NotADirectory(f"{path.relative!r} is not a directory")

    def require_absent(self, path: ResolvedPath) -> None:
        if self._provider.exists(path.absolute):
            raise FileAlreadyExists(f"{path.relative!r} already exists")

    def require_writable_target(self, path: ResolvedPath, *, overwrite: bool) -> None:
        """Target of a write, move or copy: absent, or an existing file when ``overwrite``."""
        if not self._provider.exists(path.absolute):
            return
        if not overwrite:
            raise FileAlreadyExists(f"{path.relative!r} already exists")
        if not self._provider.stat(path.absolute).is_file:
            raise NotAFile(f"{path.relative!r} is not a file")

    def check_read_size(self, path: ResolvedPath, size: int) -> None:
        if size > self._policy.max_read_bytes:
            raise FileTooLarge(
                f"{path.relative!r} is {size} bytes; the read limit is {self._policy.max_read_bytes} bytes"
            )

    def check_write_size(self, path: ResolvedPath, size: int) -> None:
        if size > self._policy.max_write_bytes:
            raise FileTooLarge(
                f"Content for {path.relative!r} is {size} bytes; the write limit is "
                f"{self._policy.max_write_bytes} bytes"
            )


def _matches(relative: str, patterns: tuple[str, ...]) -> bool:
    """True if any component of ``relative`` matches any pattern (so ``.git`` covers ``.git/x``)."""
    if relative == ".":
        return False
    return any(fnmatchcase(part, p) for part in PurePosixPath(relative).parts for p in patterns)
