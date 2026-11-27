"""Parsers of git's machine-readable output, on recorded samples (no git needed)."""

import pytest

from app.capabilities.git.repository import (
    mask_url,
    parse_branches,
    parse_log,
    parse_remotes,
    parse_status,
    split_nul,
)
from app.capabilities.git.schemas import FileChange

HASH = "0123456789abcdef0123456789abcdef01234567"
MODES = "N... 100644 100644 100644"
OIDS = f"{HASH} {HASH}"


def nul(*records: str) -> str:
    return "".join(f"{r}\x00" for r in records)


def test_status_headers_and_every_record_type() -> None:
    text = nul(
        f"# branch.oid {HASH}",
        "# branch.head feature/x",
        "# branch.upstream origin/feature/x",
        "# branch.ab +2 -1",
        f"1 M. {MODES} {OIDS} staged file.py",
        f"1 .M {MODES} {OIDS} worktree.py",
        f"1 MM {MODES} {OIDS} both.py",
        f"1 A. {MODES} {OIDS} new.py",
        f"1 .D {MODES} {OIDS} gone.py",
        f"2 R. {MODES} {OIDS} R100 new name.py",
        "old name.py",
        f"u UU N... 100644 100644 100644 100644 {HASH} {HASH} {HASH} conflict.py",
        "? untracked dir/notes.txt",
    )
    status = parse_status(text)
    assert (status.oid, status.branch, status.upstream, status.ahead, status.behind) == (
        HASH,
        "feature/x",
        "origin/feature/x",
        2,
        1,
    )
    assert status.staged == [
        FileChange(path="staged file.py", change="modified"),
        FileChange(path="both.py", change="modified"),
        FileChange(path="new.py", change="added"),
        FileChange(path="new name.py", change="renamed", original_path="old name.py"),
    ]
    assert status.modified == [
        FileChange(path="worktree.py", change="modified"),
        FileChange(path="both.py", change="modified"),
        FileChange(path="gone.py", change="deleted"),
    ]
    assert status.conflicted == ["conflict.py"]
    assert status.untracked == ["untracked dir/notes.txt"]


def test_status_of_a_new_repository_and_a_detached_head() -> None:
    initial = parse_status(nul("# branch.oid (initial)", "# branch.head main"))
    assert (initial.oid, initial.branch) == (None, "main")
    detached = parse_status(nul(f"# branch.oid {HASH}", "# branch.head (detached)"))
    assert (detached.oid, detached.branch) == (HASH, None)


def test_log() -> None:
    first = "\x1f".join(
        [HASH, "0123456", "Ada", "ada@example.com", "2026-11-27T10:00:00+01:00", "Fix bug", "Details\n"]
    )
    second = "\x1f".join(
        [HASH, "0123456", "Bob", "bob@example.com", "2026-11-26T10:00:00+01:00", "Start", ""]
    )
    commits = parse_log(nul(first, "\n" + second))
    assert [(c.author, c.subject, c.body) for c in commits] == [
        ("Ada", "Fix bug", "Details"),
        ("Bob", "Start", ""),
    ]
    assert commits[0].date == "2026-11-27T10:00:00+01:00"


def test_branches_skip_symbolic_head() -> None:
    text = (
        "refs/heads/main\x00main\x00*\x00origin/main\x00abc1234\x00Add app\n"
        "refs/heads/dev\x00dev\x00 \x00\x00def5678\x00WIP\n"
        "refs/remotes/origin/HEAD\x00origin\x00 \x00\x00abc1234\x00Add app\n"
        "refs/remotes/origin/main\x00origin/main\x00 \x00\x00abc1234\x00Add app\n"
    )
    branches = parse_branches(text)
    assert [(b.name, b.current, b.remote, b.upstream) for b in branches] == [
        ("main", True, False, "origin/main"),
        ("dev", False, False, None),
        ("origin/main", False, True, None),
    ]


def test_remotes_are_masked() -> None:
    text = (
        "origin\thttps://user:ghp_secret@github.com/me/repo.git (fetch)\n"
        "origin\thttps://user:ghp_secret@github.com/me/repo.git (push)\n"
        "backup\tgit@example.com:me/repo.git (fetch)\n"
    )
    remotes = parse_remotes(text)
    assert remotes[0].fetch_url == remotes[0].push_url == "https://***@github.com/me/repo.git"
    assert (remotes[1].name, remotes[1].fetch_url, remotes[1].push_url) == (
        "backup",
        "git@example.com:me/repo.git",
        None,
    )


@pytest.mark.parametrize(
    ("url", "masked"),
    [
        ("https://token@host/x.git", "https://***@host/x.git"),
        ("ssh://git:pw@host:22/x", "ssh://***@host:22/x"),
        ("https://host/x.git", "https://host/x.git"),
        ("/srv/repos/x.git", "/srv/repos/x.git"),
        ("git@host:x.git", "git@host:x.git"),
    ],
)
def test_mask_url(url: str, masked: str) -> None:
    assert mask_url(url) == masked


def test_split_nul() -> None:
    assert split_nul("a\x00b c\x00\x00") == ["a", "b c"]
