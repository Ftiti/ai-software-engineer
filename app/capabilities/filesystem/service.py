"""Business logic of the filesystem capability.

Every operation follows the same shape: validate (paths, rules, existence, size) through the
:class:`PathValidator`, then act through the :class:`FilesystemProvider`. The service never
touches the OS itself, and OS errors are translated into :mod:`exceptions` with readable
messages.
"""

from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager

from app.capabilities.filesystem.exceptions import (
    AccessDenied,
    FileNotFound,
    FilesystemError,
    UnsupportedFile,
)
from app.capabilities.filesystem.schemas import (
    DirectoryEntry,
    FileOperationResponse,
    ListDirectoryResponse,
    ReadFileResponse,
    WriteFileResponse,
)
from app.capabilities.filesystem.validator import Operation, PathValidator, ResolvedPath
from app.providers.filesystem import DirEntry, FilesystemProvider

_BINARY_SNIFF_BYTES = 8192


class FilesystemService:
    def __init__(self, provider: FilesystemProvider, validator: PathValidator) -> None:
        self._provider = provider
        self._validator = validator

    @property
    def validator(self) -> PathValidator:
        """The workspace rules, shared with capabilities that act on the workspace (terminal)."""
        return self._validator

    # -- Read-only inspection ----------------------------------------------------------------

    def list_directory(self, path: str = ".", *, recursive: bool = False) -> ListDirectoryResponse:
        directory = self._validator.resolve(path, Operation.LIST)
        self._validator.require_directory(directory)
        limit = self._validator.policy.max_list_entries

        entries: list[DirectoryEntry] = []
        pending = deque([directory])
        while pending:
            current = pending.popleft()
            with _os_errors(current):
                children = self._provider.list_dir(current.absolute)
            for entry in children:
                child = self._validator.child(current, entry.name)
                if self._validator.is_denied(child.relative):
                    continue
                if len(entries) == limit:
                    return ListDirectoryResponse(path=directory.relative, entries=entries, truncated=True)
                entries.append(_to_entry(child.relative, entry))
                if recursive and self._should_descend(child, entry):
                    pending.append(child)
        return ListDirectoryResponse(path=directory.relative, entries=entries)

    def read_file(self, path: str) -> ReadFileResponse:
        file = self._validator.resolve(path, Operation.READ)
        stat = self._validator.require_file(file)
        self._validator.check_read_size(file, stat.size)
        with _os_errors(file):
            data = self._provider.read_bytes(file.absolute)
        return ReadFileResponse(path=file.relative, content=_decode(file, data), size=len(data))

    # -- Modifications -----------------------------------------------------------------------

    def write_file(self, path: str, content: str) -> WriteFileResponse:
        """Create or replace a text file. Missing parent directories are created."""
        file = self._validator.resolve(path, Operation.WRITE)
        created = not self._validator.exists(file)
        if not created:
            self._validator.require_file(file)
        return self._write(file, content, created=created)

    def create_file(self, path: str, content: str = "") -> WriteFileResponse:
        """Create a new text file; fails if the path already exists."""
        file = self._validator.resolve(path, Operation.CREATE)
        self._validator.require_absent(file)
        return self._write(file, content, created=True)

    def delete_file(self, path: str) -> FileOperationResponse:
        file = self._validator.resolve(path, Operation.DELETE)
        self._validator.require_file(file)
        with _os_errors(file):
            self._provider.delete_file(file.absolute)
        return FileOperationResponse(path=file.relative, detail="deleted")

    def create_directory(self, path: str) -> FileOperationResponse:
        directory = self._validator.resolve(path, Operation.MKDIR)
        self._validator.require_absent(directory)
        with _os_errors(directory):
            self._provider.make_dir(directory.absolute)
        return FileOperationResponse(path=directory.relative, detail="directory created")

    def move_file(self, source: str, destination: str, *, overwrite: bool = False) -> FileOperationResponse:
        src, dst = self._transfer_paths(source, destination, Operation.MOVE, overwrite=overwrite)
        with _os_errors(src):
            self._provider.move(src.absolute, dst.absolute)
        return FileOperationResponse(path=dst.relative, detail=f"moved from {src.relative}")

    def copy_file(self, source: str, destination: str, *, overwrite: bool = False) -> FileOperationResponse:
        src, dst = self._transfer_paths(source, destination, Operation.COPY, overwrite=overwrite)
        with _os_errors(src):
            self._provider.copy_file(src.absolute, dst.absolute)
        return FileOperationResponse(path=dst.relative, detail=f"copied from {src.relative}")

    # -- Internals ---------------------------------------------------------------------------

    def _should_descend(self, child: ResolvedPath, entry: DirEntry) -> bool:
        """Recurse into real subdirectories only: never through symlinks or ignored folders."""
        return entry.is_dir and not entry.is_symlink and not self._validator.is_ignored(child.relative)

    def _write(self, file: ResolvedPath, content: str, *, created: bool) -> WriteFileResponse:
        data = content.encode("utf-8")
        self._validator.check_write_size(file, len(data))
        with _os_errors(file):
            self._provider.write_bytes(file.absolute, data, create_parents=True)
        return WriteFileResponse(path=file.relative, bytes_written=len(data), created=created)

    def _transfer_paths(
        self, source: str, destination: str, operation: Operation, *, overwrite: bool
    ) -> tuple[ResolvedPath, ResolvedPath]:
        src = self._validator.resolve(source, Operation.READ if operation is Operation.COPY else operation)
        dst = self._validator.resolve(destination, operation)
        self._validator.require_file(src)
        self._validator.require_writable_target(dst, overwrite=overwrite)
        if src.absolute == dst.absolute:
            raise FilesystemError(f"Source and destination are the same file: {src.relative!r}")
        return src, dst


def _to_entry(relative: str, entry: DirEntry) -> DirectoryEntry:
    kind = "symlink" if entry.is_symlink else "directory" if entry.is_dir else "file"
    return DirectoryEntry(path=relative, type=kind, size=entry.size if kind == "file" else None)


def _decode(file: ResolvedPath, data: bytes) -> str:
    if b"\x00" in data[:_BINARY_SNIFF_BYTES]:
        raise UnsupportedFile(f"{file.relative!r} is a binary file")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedFile(f"{file.relative!r} is not valid UTF-8 text") from exc


@contextmanager
def _os_errors(path: ResolvedPath) -> Iterator[None]:
    """Translate OS errors raised by the provider into capability errors."""
    try:
        yield
    except FilesystemError:
        raise
    except PermissionError as exc:
        raise AccessDenied(f"Permission denied by the operating system: {path.relative!r}") from exc
    except FileNotFoundError as exc:
        raise FileNotFound(f"{path.relative!r} no longer exists") from exc
    except OSError as exc:
        raise FilesystemError(f"Filesystem error on {path.relative!r}: {exc.strerror or exc}") from exc
