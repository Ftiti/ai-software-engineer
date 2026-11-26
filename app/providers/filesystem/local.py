"""Filesystem provider backed by the local operating system."""

import os
import shutil
import stat as stat_module
import tempfile
from pathlib import Path

from app.providers.filesystem.base import DirEntry, FileStat, FilesystemProvider


class LocalFilesystemProvider(FilesystemProvider):
    def resolve(self, path: Path) -> Path:
        return path.resolve(strict=False)

    def exists(self, path: Path) -> bool:
        return os.path.lexists(path)

    def stat(self, path: Path) -> FileStat:
        st = path.stat()
        return FileStat(
            size=st.st_size,
            is_file=stat_module.S_ISREG(st.st_mode),
            is_dir=stat_module.S_ISDIR(st.st_mode),
            modified=st.st_mtime,
        )

    def list_dir(self, path: Path) -> list[DirEntry]:
        with os.scandir(path) as it:
            entries = [_entry(e) for e in it]
        return sorted(entries, key=lambda e: e.name)

    def read_bytes(self, path: Path) -> bytes:
        return path.read_bytes()

    def write_bytes(self, path: Path, data: bytes, *, create_parents: bool = False) -> None:
        if create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary file in the same directory, then atomically replace the target.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            if path.exists():
                shutil.copymode(path, tmp)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def make_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def delete_file(self, path: Path) -> None:
        path.unlink()

    def move(self, source: Path, destination: Path) -> None:
        shutil.move(source, destination)

    def copy_file(self, source: Path, destination: Path) -> None:
        shutil.copy2(source, destination)


def _entry(e: os.DirEntry[str]) -> DirEntry:
    is_file = e.is_file()
    return DirEntry(
        name=e.name,
        is_file=is_file,
        is_dir=e.is_dir(),
        is_symlink=e.is_symlink(),
        size=e.stat().st_size if is_file else None,
    )
