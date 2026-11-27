"""Centralised safety rules of the Git capability.

Every Git operation is validated before git runs:

1. **Operation allowed** (:meth:`GitValidator.check_allowed`): modifying operations are refused
   in a read-only workspace (``FS_READ_ONLY``); push is refused unless enabled, on a detached
   HEAD and on protected branches.
2. **Repository inside the workspace**: the folder is resolved by the filesystem
   :class:`PathValidator`, then the repository *root* reported by git must be inside the
   workspace too, otherwise an operation could touch files outside it.
3. **Arguments well-formed**: paths (inside the workspace, never secrets), references, branch
   names (git's ref-format rules), remotes, messages, limits. Nothing the agent sends can start
   with ``-``, so it is never read as an option.
4. **Final guard** (:meth:`GitValidator.guard`): the argument vector the service built must use
   an allowed sub-command and no dangerous flag (force, hard reset, delete, amend...). The
   service never builds them; the guard proves it.
"""

import posixpath
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum

from app.capabilities.filesystem import Operation, PathValidator
from app.capabilities.filesystem.exceptions import AccessDenied, FilesystemError
from app.capabilities.filesystem.validator import ResolvedPath
from app.capabilities.git.exceptions import (
    GitOperationNotAllowed,
    InvalidGitArgument,
    RepositoryOutsideWorkspace,
)
from app.config import Settings

ALLOWED_SUBCOMMANDS = frozenset(
    {
        "status",
        "diff",
        "log",
        "show",
        "branch",
        "switch",
        "add",
        "commit",
        "restore",
        "remote",
        "fetch",
        "pull",
        "push",
        "rev-parse",
        "symbolic-ref",
        "for-each-ref",
    }
)
DANGEROUS_FLAGS = frozenset({"-f", "-d", "-D", "-M", "-C", "-c", "--hard", "--delete", "--mirror", "--amend"})
DANGEROUS_PREFIXES = ("--force", "--exec", "--upload-pack", "--receive-pack", "--no-verify", "--prune")
MAX_MESSAGE = 10_000
MAX_REF = 256
_REF = re.compile(r"^[A-Za-z0-9._/@{}~^+-]+$")
_REMOTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_BRANCH_FORBIDDEN = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]")


class GitOperation(StrEnum):
    STATUS = "status"
    DIFF = "diff"
    LOG = "log"
    SHOW = "show"
    BRANCH_LIST = "list branches"
    BRANCH_CREATE = "create a branch"
    CHECKOUT = "checkout"
    ADD = "add"
    COMMIT = "commit"
    RESTORE = "restore"
    REMOTE = "list remotes"
    FETCH = "fetch"
    PULL = "pull"
    PUSH = "push"

    @property
    def mutating(self) -> bool:
        """Changes the working copy, the staging area, branches or a remote."""
        return self in _MUTATING

    @property
    def network(self) -> bool:
        return self in (GitOperation.FETCH, GitOperation.PULL, GitOperation.PUSH)


_MUTATING = frozenset(
    {
        GitOperation.BRANCH_CREATE,
        GitOperation.CHECKOUT,
        GitOperation.ADD,
        GitOperation.COMMIT,
        GitOperation.RESTORE,
        GitOperation.PULL,
        GitOperation.PUSH,
    }
)


@dataclass(frozen=True, slots=True)
class GitPolicy:
    allow_push: bool = False
    protected_branches: tuple[str, ...] = ()
    read_only: bool = False
    timeout: float = 30.0
    network_timeout: float = 50.0
    max_output_bytes: int = 64_000
    max_log_entries: int = 100

    @classmethod
    def from_settings(cls, settings: Settings) -> "GitPolicy":
        return cls(
            allow_push=settings.git_allow_push,
            protected_branches=tuple(settings.git_protected_branches),
            read_only=settings.fs_read_only,
            timeout=settings.git_timeout,
            network_timeout=settings.git_network_timeout,
            max_output_bytes=settings.git_max_output_bytes,
            max_log_entries=settings.git_max_log_entries,
        )


class GitValidator:
    def __init__(self, paths: PathValidator, policy: GitPolicy) -> None:
        self._paths = paths
        self._policy = policy

    @property
    def policy(self) -> GitPolicy:
        return self._policy

    # -- Operation ---------------------------------------------------------------------------

    def check_allowed(self, operation: GitOperation, *, branch: str | None = None) -> None:
        if operation.mutating and self._policy.read_only:
            raise GitOperationNotAllowed(f"Cannot {operation}: the workspace is read-only")
        if operation is not GitOperation.PUSH:
            return
        if not self._policy.allow_push:
            raise GitOperationNotAllowed("Push is disabled. Set GIT_ALLOW_PUSH=true to enable it")
        if branch in self._policy.protected_branches:
            raise GitOperationNotAllowed(f"Pushing {branch!r} is not allowed (protected branch)")

    # -- Repository --------------------------------------------------------------------------

    def directory(self, repository: str) -> ResolvedPath:
        """The folder the agent named: an existing directory inside the workspace."""
        with _workspace_errors():
            folder = self._paths.resolve(repository, Operation.LIST)
            self._paths.require_directory(folder)
        return folder

    def root(self, toplevel: str) -> ResolvedPath:
        """The repository root reported by git: it must be inside the workspace."""
        try:
            return self._paths.resolve(toplevel, Operation.LIST)
        except AccessDenied as exc:
            raise RepositoryOutsideWorkspace(
                f"The repository root {toplevel!r} is outside the workspace (or protected)"
            ) from exc

    # -- Paths -------------------------------------------------------------------------------

    def paths(
        self,
        root: ResolvedPath,
        paths: Sequence[str],
        *,
        write: bool = False,
        allow_secrets: bool = False,
        files_only: bool = False,
    ) -> list[str]:
        """Validate paths given relative to the repository root; return them normalised.

        The returned (lexical) paths are what git receives, so a symlink is staged as a link;
        the resolved real path is what the workspace and secret rules are checked against.
        """
        return [
            self._path(root, p, write=write, allow_secrets=allow_secrets, files_only=files_only)
            for p in paths
        ]

    def is_secret(self, path: str) -> bool:
        return self._paths.is_denied(path)

    def _path(
        self, root: ResolvedPath, path: str, *, write: bool, allow_secrets: bool, files_only: bool
    ) -> str:
        raw = path.strip()
        if not raw or "\x00" in raw:
            raise InvalidGitArgument(f"Invalid path {path!r}")
        base = root.absolute.as_posix()
        normalised = posixpath.normpath(raw if raw.startswith("/") else posixpath.join(base, raw))
        relative = posixpath.relpath(normalised, base)
        if relative == ".." or relative.startswith("../"):
            raise RepositoryOutsideWorkspace(f"{path!r} is outside the repository")
        if files_only and relative == ".":
            raise InvalidGitArgument("The whole repository cannot be restored: name the files explicitly")
        if self.is_secret(relative):
            if not allow_secrets:
                raise RepositoryOutsideWorkspace(f"Access to {path!r} is not allowed (protected secret)")
            return relative
        with _workspace_errors():
            real = self._paths.resolve(normalised, Operation.WRITE if write else Operation.READ)
        if files_only and self._paths.is_directory(real):
            raise InvalidGitArgument(f"{path!r} is a directory: name the files explicitly")
        return relative

    # -- Names -------------------------------------------------------------------------------

    def reference(self, ref: str, *, allow_range: bool = False) -> str:
        value = ref.strip()
        if allow_range and ".." in value:
            sides = value.split("...") if "..." in value else value.split("..")
            if len(sides) != 2 or not any(sides):
                raise InvalidGitArgument(f"Invalid range {ref!r}: use 'a..b' or 'a...b'")
            for side in sides:
                if side:
                    self.reference(side)
            return value
        if not value or len(value) > MAX_REF:
            raise InvalidGitArgument(f"Invalid reference {ref!r}")
        if value.startswith("-") or ".." in value or not _REF.fullmatch(value):
            raise InvalidGitArgument(
                f"Invalid reference {ref!r}: use a commit hash, branch or tag name (e.g. 'main', 'HEAD~1')"
            )
        return value

    def branch_name(self, name: str) -> str:
        """Git's ref-format rules for branch names (``git check-ref-format --branch``)."""
        value = name.strip()
        problem = _branch_problem(value)
        if problem:
            raise InvalidGitArgument(f"Invalid branch name {name!r}: {problem}")
        return value

    def remote(self, name: str) -> str:
        value = name.strip()
        if not _REMOTE.fullmatch(value):
            raise InvalidGitArgument(f"Invalid remote name {name!r}")
        return value

    def message(self, text: str) -> str:
        if "\x00" in text:
            raise InvalidGitArgument("The commit message contains a NUL byte")
        if not text.strip():
            raise InvalidGitArgument("The commit message is empty")
        if len(text) > MAX_MESSAGE:
            raise InvalidGitArgument(f"The commit message is longer than {MAX_MESSAGE} characters")
        return text.strip()

    def log_limit(self, limit: int) -> int:
        maximum = self._policy.max_log_entries
        if not 1 <= limit <= maximum:
            raise InvalidGitArgument(f"limit must be between 1 and {maximum}")
        return limit

    # -- Final guard -------------------------------------------------------------------------

    def guard(self, args: Sequence[str]) -> None:
        """Defence in depth: refuse any argument vector using a forbidden sub-command or flag."""
        if not args or args[0] not in ALLOWED_SUBCOMMANDS:
            raise GitOperationNotAllowed(f"git {args[0] if args else ''!s} is not allowed")
        options = args[: args.index("--")] if "--" in args else args
        for arg in options[1:]:
            if arg in DANGEROUS_FLAGS or arg.startswith(DANGEROUS_PREFIXES):
                raise GitOperationNotAllowed(f"The git option {arg!r} is not allowed")
            if args[0] == "push" and arg.startswith(("+", ":")):
                raise GitOperationNotAllowed(f"The push refspec {arg!r} is not allowed (force or delete)")


def _branch_problem(name: str) -> str | None:
    rules = (
        (not name, "it is empty"),
        (name.startswith("-"), "it may not start with '-'"),
        (name in ("HEAD", "@"), "it is reserved"),
        (".." in name, "it may not contain '..'"),
        ("@{" in name, "it may not contain '@{'"),
        ("//" in name, "it may not contain '//'"),
        (bool(_BRANCH_FORBIDDEN.search(name)), "it may not contain spaces or any of ~ ^ : ? * [ \\"),
        (name.endswith(("/", ".", ".lock")), "it may not end with '/', '.' or '.lock'"),
        (
            any(part.startswith(".") or part.endswith(".lock") for part in name.split("/")),
            "a part starts with '.'",
        ),
        (len(name) > MAX_REF, f"it is longer than {MAX_REF} characters"),
    )
    return next((problem for broken, problem in rules if broken), None)


@contextmanager
def _workspace_errors() -> Iterator[None]:
    """Report filesystem rule violations as Git errors."""
    try:
        yield
    except AccessDenied as exc:
        raise RepositoryOutsideWorkspace(str(exc)) from exc
    except FilesystemError as exc:
        raise InvalidGitArgument(str(exc)) from exc
