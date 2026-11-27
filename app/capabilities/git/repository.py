"""Repository analysis: pure parsers for git's machine-readable output (no git, no I/O).

Formats (stable across git versions, see research R3):

- ``status --porcelain=v2 --branch -z``: headers ``# branch.*`` then one record per file;
- ``log -z --format=LOG_FORMAT``: commits separated by NUL, fields by 0x1F;
- ``for-each-ref --format=BRANCH_FORMAT``: one line per ref, fields separated by NUL;
- ``remote -v``: ``name<TAB>url (fetch|push)``.
"""

import re
from dataclasses import dataclass, field

from app.capabilities.git.schemas import Branch, ChangeType, Commit, FileChange, Remote

FIELD = "\x1f"
LOG_FORMAT = "%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b"
BRANCH_FORMAT = (
    "%(refname)%00%(refname:short)%00%(HEAD)%00%(upstream:short)%00%(objectname:short)%00%(contents:subject)"
)

_CHANGES: dict[str, ChangeType] = {
    "A": "added",
    "M": "modified",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "T": "type_changed",
    "U": "unmerged",
}
_CREDENTIALS = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)[^/@]+@")


@dataclass
class ParsedStatus:
    oid: str | None = None  # None: no commit yet
    branch: str | None = None  # None: detached HEAD
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    staged: list[FileChange] = field(default_factory=list)
    modified: list[FileChange] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    conflicted: list[str] = field(default_factory=list)


def split_nul(text: str) -> list[str]:
    return [item for item in text.split("\x00") if item]


def parse_status(text: str) -> ParsedStatus:
    status = ParsedStatus()
    records = iter(text.split("\x00"))
    for record in records:
        if not record:
            continue
        kind = record[0]
        if kind == "#":
            _parse_header(status, record)
        elif kind == "1":  # 1 XY sub mH mI mW hH hI path
            parts = record.split(" ", 8)
            _add_change(status, parts[1], parts[8])
        elif kind == "2":  # 2 XY sub mH mI mW hH hI Xscore path NUL origPath
            parts = record.split(" ", 9)
            _add_change(status, parts[1], parts[9], original=next(records, None))
        elif kind == "u":  # u XY sub m1 m2 m3 mW h1 h2 h3 path
            status.conflicted.append(record.split(" ", 10)[10])
        elif kind == "?":
            status.untracked.append(record[2:])
    return status


def parse_log(text: str) -> list[Commit]:
    commits = []
    for record in split_nul(text):
        fields = record.lstrip("\n").split(FIELD)
        if len(fields) < 7:
            continue
        commits.append(
            Commit(
                hash=fields[0],
                short_hash=fields[1],
                author=fields[2],
                email=fields[3],
                date=fields[4],
                subject=fields[5],
                body=FIELD.join(fields[6:]).strip(),
            )
        )
    return commits


def parse_branches(text: str) -> list[Branch]:
    branches = []
    for line in text.splitlines():
        fields = line.split("\x00")
        if len(fields) < 6 or fields[0].endswith("/HEAD"):  # refs/remotes/origin/HEAD is an alias
            continue
        refname, name, head, upstream, commit, subject = fields[:6]
        branches.append(
            Branch(
                name=name,
                current=head == "*",
                remote=refname.startswith("refs/remotes/"),
                upstream=upstream or None,
                commit=commit,
                subject=subject,
            )
        )
    return branches


def parse_remotes(text: str) -> list[Remote]:
    urls: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        name, _, rest = line.partition("\t")
        url, _, kind = rest.rpartition(" ")
        if name and url:
            urls.setdefault(name, {})[kind.strip("()")] = mask_url(url)
    return [Remote(name=n, fetch_url=u.get("fetch"), push_url=u.get("push")) for n, u in urls.items()]


def mask_url(url: str) -> str:
    """``https://user:token@host/x`` -> ``https://***@host/x``; other URLs unchanged."""
    return _CREDENTIALS.sub(r"\g<scheme>***@", url)


def _parse_header(status: ParsedStatus, record: str) -> None:
    key, _, value = record[2:].partition(" ")
    if key == "branch.oid":
        status.oid = None if value == "(initial)" else value
    elif key == "branch.head":
        status.branch = None if value == "(detached)" else value
    elif key == "branch.upstream":
        status.upstream = value
    elif key == "branch.ab":
        ahead, _, behind = value.partition(" ")
        status.ahead, status.behind = int(ahead.lstrip("+")), int(behind.lstrip("-"))


def _add_change(status: ParsedStatus, xy: str, path: str, original: str | None = None) -> None:
    index, worktree = xy[0], xy[1]
    if index != ".":
        status.staged.append(_change(index, path, original))
    if worktree != ".":
        status.modified.append(_change(worktree, path, original if index == "." else None))


def _change(code: str, path: str, original: str | None) -> FileChange:
    change = _CHANGES.get(code, "modified")
    keep_original = change in ("renamed", "copied")
    return FileChange(path=path, change=change, original_path=original if keep_original else None)
