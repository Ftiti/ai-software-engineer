"""Local provider: the thin OS layer."""

import os
from pathlib import Path

from app.providers.filesystem import LocalFilesystemProvider

provider = LocalFilesystemProvider()


def test_stat_and_list_dir(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("12345")
    (tmp_path / "a").mkdir()
    os.symlink(tmp_path / "b.txt", tmp_path / "c")

    entries = provider.list_dir(tmp_path)

    assert [e.name for e in entries] == ["a", "b.txt", "c"]
    assert entries[0].is_dir and entries[0].size is None
    assert entries[1].is_file and entries[1].size == 5
    assert entries[2].is_symlink
    assert provider.stat(tmp_path / "b.txt").size == 5


def test_write_is_atomic_and_keeps_permissions(tmp_path: Path) -> None:
    target = tmp_path / "script.sh"
    target.write_text("old")
    target.chmod(0o755)

    provider.write_bytes(target, b"new")

    assert target.read_bytes() == b"new"
    assert target.stat().st_mode & 0o777 == 0o755
    assert [p.name for p in tmp_path.iterdir()] == ["script.sh"]  # no temp file left behind


def test_write_creates_parents_when_asked(tmp_path: Path) -> None:
    provider.write_bytes(tmp_path / "a" / "b" / "c.txt", b"x", create_parents=True)
    assert (tmp_path / "a" / "b" / "c.txt").read_bytes() == b"x"


def test_resolve_follows_symlinks_and_dotdot(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    os.symlink(tmp_path / "real", tmp_path / "link")
    assert provider.resolve(tmp_path / "link" / ".." / "link" / "f") == (tmp_path / "real" / "f").resolve()


def test_move_copy_delete(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("x")
    provider.copy_file(src, tmp_path / "b.txt")
    provider.move(tmp_path / "b.txt", tmp_path / "c.txt")
    provider.delete_file(src)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["c.txt"]
