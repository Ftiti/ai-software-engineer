"""Business logic of the Git capability: repository analysis and Git workflows.

Every operation follows the same shape (see specs/001-git-capability/diagrams.md, diagram 5):

1. check the operation and validate the agent's arguments (:class:`GitValidator`);
2. find the repository and check its root is inside the workspace;
3. when needed, read the repository state first (secrets to skip, conflicts, staged files);
4. build the argument vector, pass it through the validator's final guard, run it through the
   :class:`GitProvider`, and parse the output into a result model.

The service never starts processes nor touches the OS itself.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.capabilities.filesystem.validator import ResolvedPath
from app.capabilities.git.exceptions import (
    ConflictsPresent,
    GitCommandFailed,
    GitError,
    GitNotInstalled,
    GitOperationNotAllowed,
    GitTimeout,
    InvalidGitArgument,
    NotARepository,
    NothingToCommit,
)
from app.capabilities.git.repository import (
    BRANCH_FORMAT,
    LOG_FORMAT,
    ParsedStatus,
    parse_branches,
    parse_log,
    parse_remotes,
    parse_status,
    split_nul,
)
from app.capabilities.git.schemas import (
    AddResult,
    BranchCreated,
    BranchList,
    CheckoutResult,
    Commit,
    CommitResult,
    DiffResult,
    LogResult,
    RemoteList,
    RemoteOperationResult,
    Repository,
    RepositoryStatus,
    RestoreResult,
    ShowResult,
)
from app.capabilities.git.validator import GitOperation, GitValidator
from app.providers.git import GitInvocation, GitOutput, GitProvider

# Output that is parsed (status, listings) may be large; text shown to the agent is capped by policy.
PARSE_LIMIT = 8_000_000
RemoteOperation = Literal["fetch", "pull", "push"]
STATUS_ARGS = ("status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all")


@dataclass(frozen=True, slots=True)
class _State:
    """Repository state read before an operation, secrets already separated."""

    status: ParsedStatus  # visible state: secret files removed
    secrets: list[str]  # changed secret files (never shown, staged or committed)
    staged_secrets: list[str]  # secret files already in the staging area (staged outside the agent)

    def changed(self) -> list[str]:
        """Every visible path with a change the next ``git add`` would stage."""
        s = self.status
        paths = [c.path for c in s.modified] + s.untracked + s.conflicted
        return list(dict.fromkeys(paths))


class GitService:
    def __init__(self, validator: GitValidator, provider: GitProvider) -> None:
        self._validator = validator
        self._provider = provider

    # -- Inspection (US1) --------------------------------------------------------------------

    async def status(self, repository: str = ".") -> RepositoryStatus:
        self._validator.check_allowed(GitOperation.STATUS)
        root = await self._root(repository)
        output = await self._git(root, *STATUS_ARGS)
        state = self._separate(parse_status(output.stdout))
        s = state.status
        return RepositoryStatus(
            repository=_repository(root, s),
            upstream=s.upstream,
            ahead=s.ahead,
            behind=s.behind,
            staged=s.staged,
            modified=s.modified,
            untracked=s.untracked,
            conflicted=s.conflicted,
            clean=not (s.staged or s.modified or s.untracked or s.conflicted or state.secrets),
            secrets_hidden=len(state.secrets),
            truncated=output.truncated,
        )

    async def diff(
        self,
        repository: str = ".",
        *,
        staged: bool = False,
        ref: str | None = None,
        target: str | None = None,
        paths: Sequence[str] = (),
        stat_only: bool = False,
    ) -> DiffResult:
        self._validator.check_allowed(GitOperation.DIFF)
        if target and not ref:
            raise InvalidGitArgument("'target' needs 'ref': the diff compares ref with target")
        if staged and target:
            raise InvalidGitArgument("'staged' compares the staging area with one reference, not two")
        revisions = [self._validator.reference(r, allow_range=True) for r in (ref, target) if r]
        root = await self._root(repository)
        pathspec = self._validator.paths(root, paths)
        base = ["diff", *(["--cached"] if staged else []), *revisions]

        changed = split_nul((await self._git(root, *base, "--name-only", "-z", "--", *pathspec)).stdout)
        files, omitted = self._without_secrets(changed)
        if not files:
            return DiffResult(
                repository=root.relative,
                files=[],
                diff="",
                stat_only=stat_only,
                omitted_secrets=omitted,
                truncated=False,
            )
        selection = files if omitted else pathspec  # only list files explicitly when something was removed
        output = await self._git(
            root, *base, *(["--stat"] if stat_only else []), "--", *selection, limit=self._text_limit
        )
        return DiffResult(
            repository=root.relative,
            files=files,
            diff=output.stdout,
            stat_only=stat_only,
            omitted_secrets=omitted,
            truncated=output.truncated,
        )

    async def log(
        self, repository: str = ".", *, limit: int = 20, ref: str | None = None, paths: Sequence[str] = ()
    ) -> LogResult:
        self._validator.check_allowed(GitOperation.LOG)
        limit = self._validator.log_limit(limit)
        revision = [self._validator.reference(ref, allow_range=True)] if ref else []
        root = await self._root(repository)
        pathspec = self._validator.paths(root, paths)
        if not revision and not await self._has_commits(root):
            return LogResult(repository=root.relative, commits=[], limit=limit)
        output = await self._git(
            root, "log", "-z", f"--max-count={limit}", f"--format={LOG_FORMAT}", *revision, "--", *pathspec
        )
        return LogResult(repository=root.relative, commits=parse_log(output.stdout), limit=limit)

    async def show(self, repository: str = ".", *, ref: str = "HEAD", path: str | None = None) -> ShowResult:
        self._validator.check_allowed(GitOperation.SHOW)
        ref = self._validator.reference(ref)
        root = await self._root(repository)
        file = self._validator.paths(root, [path])[0] if path else None
        commit = await self._commit(root, ref)

        if file is not None:
            output = await self._git(root, "show", f"{commit.hash}:{file}", limit=self._text_limit)
            return ShowResult(
                repository=root.relative,
                commit=commit,
                path=file,
                content=output.stdout,
                omitted_secrets=[],
                truncated=output.truncated,
            )
        names = split_nul(
            (await self._git(root, "show", "--name-only", "-z", "--format=", commit.hash)).stdout
        )
        files, omitted = self._without_secrets([n.strip("\n") for n in names if n.strip("\n")])
        content, truncated = "", False
        if files or not omitted:
            selection = files if omitted else []
            output = await self._git(
                root,
                "show",
                "--format=",
                "--stat",
                "--patch",
                commit.hash,
                "--",
                *selection,
                limit=self._text_limit,
            )
            content, truncated = output.stdout.lstrip("\n"), output.truncated
        return ShowResult(
            repository=root.relative,
            commit=commit,
            path=None,
            content=content,
            omitted_secrets=omitted,
            truncated=truncated,
        )

    # -- Branches (US3) ----------------------------------------------------------------------

    async def branches(self, repository: str = ".", *, include_remote: bool = False) -> BranchList:
        self._validator.check_allowed(GitOperation.BRANCH_LIST)
        root = await self._root(repository)
        refs = ["refs/heads", *(["refs/remotes"] if include_remote else [])]
        output = await self._git(root, "for-each-ref", f"--format={BRANCH_FORMAT}", *refs)
        branches = parse_branches(output.stdout)
        current = next((b.name for b in branches if b.current), None)
        return BranchList(repository=root.relative, current=current, branches=branches)

    async def create_branch(
        self, repository: str = ".", *, name: str, start_point: str | None = None
    ) -> BranchCreated:
        self._validator.check_allowed(GitOperation.BRANCH_CREATE)
        name = self._validator.branch_name(name)
        start = self._validator.reference(start_point) if start_point else None
        root = await self._root(repository)
        await self._git(root, "branch", name, *([start] if start else []))
        return BranchCreated(
            repository=root.relative, branch=name, start_point=start or "HEAD", switched=False
        )

    async def checkout(
        self, repository: str = ".", *, branch: str, create: bool = False, start_point: str | None = None
    ) -> CheckoutResult:
        """Switch branches with ``git switch``: it refuses to overwrite local changes, never forces."""
        self._validator.check_allowed(GitOperation.CHECKOUT)
        branch = self._validator.branch_name(branch)
        if start_point and not create:
            raise InvalidGitArgument("'start_point' is only used with create=true")
        start = self._validator.reference(start_point) if start_point else None
        root = await self._root(repository)
        previous = await self._current_branch(root)
        args = ["switch", "--create", branch, *([start] if start else [])] if create else ["switch", branch]
        await self._git(root, *args)
        return CheckoutResult(repository=root.relative, branch=branch, created=create, previous=previous)

    # -- Local changes (US2, US4) ------------------------------------------------------------

    async def add(self, repository: str = ".", *, paths: Sequence[str] = (), all: bool = False) -> AddResult:
        """Stage the changed files under ``paths`` (or every change), never a secret file.

        Folders are expanded to the changed files they contain, so ``.`` or ``src`` cannot
        stage a secret either.
        """
        self._validator.check_allowed(GitOperation.ADD)
        if bool(paths) == all:
            raise InvalidGitArgument("Give either paths or all=true")
        root = await self._root(repository)
        selected = ["."] if all else self._validator.paths(root, paths)
        state = await self._state(root)
        files = [f for f in state.changed() if any(_is_under(f, p) for p in selected)]
        skipped = [f for f in state.secrets if any(_is_under(f, p) for p in selected)]
        if files:
            await self._git(root, "add", "--", *files)
        return AddResult(repository=root.relative, staged=files, skipped_secrets=skipped)

    async def commit(self, repository: str = ".", *, message: str) -> CommitResult:
        self._validator.check_allowed(GitOperation.COMMIT)
        message = self._validator.message(message)
        root = await self._root(repository)
        state = await self._state(root)
        s = state.status
        if s.conflicted:
            raise ConflictsPresent(f"Cannot commit: unresolved conflicts in {', '.join(s.conflicted)}")
        if state.staged_secrets:
            raise GitOperationNotAllowed(
                f"Cannot commit: secret file(s) staged: {', '.join(state.staged_secrets)}. "
                "Unstage them with git_restore (staged=true)"
            )
        if not s.staged:
            raise NothingToCommit("Nothing to commit: no staged changes (use git_add first)")
        await self._git(root, "commit", "--cleanup=strip", f"--message={message}")
        commit = await self._commit(root, "HEAD")
        branch = await self._current_branch(root)
        return CommitResult(
            repository=root.relative,
            commit=commit,
            branch=branch,
            detached=branch is None,
            files_changed=len(s.staged),
        )

    async def restore(
        self, repository: str = ".", *, paths: Sequence[str], staged: bool = False
    ) -> RestoreResult:
        """``staged``: unstage only (changes kept). Otherwise discard the files' uncommitted changes."""
        self._validator.check_allowed(GitOperation.RESTORE)
        if not paths:
            raise InvalidGitArgument("Name the files to restore")
        root = await self._root(repository)
        if staged:  # unstaging never reveals or loses content, so secrets may be unstaged too
            files = self._validator.paths(root, paths, allow_secrets=True)
            await self._git(root, "restore", "--staged", "--", *files)
        else:
            files = self._validator.paths(root, paths, write=True, files_only=True)
            await self._git(root, "restore", "--worktree", "--", *files)
        return RestoreResult(repository=root.relative, paths=files, staged=staged)

    # -- Remotes (US5) -----------------------------------------------------------------------

    async def remotes(self, repository: str = ".") -> RemoteList:
        self._validator.check_allowed(GitOperation.REMOTE)
        root = await self._root(repository)
        output = await self._git(root, "remote", "-v")
        return RemoteList(repository=root.relative, remotes=parse_remotes(output.stdout))

    async def fetch(self, repository: str = ".", *, remote: str | None = None) -> RemoteOperationResult:
        self._validator.check_allowed(GitOperation.FETCH)
        root = await self._root(repository)
        name = await self._remote(root, remote)
        output = await self._git(root, "fetch", name, network=True)
        return _remote_result(root, "fetch", name, None, output)

    async def pull(
        self, repository: str = ".", *, remote: str | None = None, branch: str | None = None
    ) -> RemoteOperationResult:
        """Fast-forward only: a diverged history is reported, never merged or rebased."""
        self._validator.check_allowed(GitOperation.PULL)
        branch = self._validator.branch_name(branch) if branch else None
        root = await self._root(repository)
        name = await self._remote(root, remote) if remote or branch else None
        target = [name] if name else []
        output = await self._git(
            root, "pull", "--ff-only", "--no-rebase", *target, *([branch] if branch else []), network=True
        )
        return _remote_result(root, "pull", name, branch, output)

    async def push(
        self, repository: str = ".", *, remote: str | None = None, set_upstream: bool = False
    ) -> RemoteOperationResult:
        """Push the current branch: never forced, never deleting, never a protected branch."""
        self._validator.check_allowed(GitOperation.PUSH)
        root = await self._root(repository)
        branch = await self._current_branch(root)
        if branch is None:
            raise GitOperationNotAllowed("Cannot push: HEAD is detached (switch to a branch first)")
        self._validator.check_allowed(GitOperation.PUSH, branch=branch)
        name = await self._remote(root, remote)
        output = await self._git(
            root, "push", *(["--set-upstream"] if set_upstream else []), name, branch, network=True
        )
        return _remote_result(root, "push", name, branch, output)

    # -- Internals ---------------------------------------------------------------------------

    @property
    def _text_limit(self) -> int:
        return self._validator.policy.max_output_bytes

    async def _git(
        self,
        cwd: ResolvedPath,
        *args: str,
        network: bool = False,
        limit: int = PARSE_LIMIT,
        check: bool = True,
    ) -> GitOutput:
        self._validator.guard(args)
        policy = self._validator.policy
        timeout = policy.network_timeout if network else policy.timeout
        try:
            output = await self._provider.run(GitInvocation(cwd.absolute, tuple(args), timeout, limit))
        except FileNotFoundError as exc:
            raise GitNotInstalled("git is not installed or not on PATH") from exc
        except OSError as exc:
            raise GitError(f"Cannot run git: {exc.strerror or exc}") from exc
        if output.timed_out:
            raise GitTimeout(f"git {args[0]} did not finish within {timeout}s")
        if check and output.exit_code != 0:
            detail = output.stderr.strip() or output.stdout.strip() or f"exit code {output.exit_code}"
            raise GitCommandFailed(f"git {args[0]} failed: {detail}")
        return output

    async def _root(self, repository: str) -> ResolvedPath:
        folder = self._validator.directory(repository)
        output = await self._git(folder, "rev-parse", "--show-toplevel", check=False)
        if output.exit_code != 0:
            reason = output.stderr.strip().splitlines()[-1] if output.stderr.strip() else ""
            raise NotARepository(f"{repository!r} is not inside a Git repository. {reason}".strip())
        return self._validator.root(output.stdout.strip())

    async def _state(self, root: ResolvedPath) -> _State:
        return self._separate(parse_status((await self._git(root, *STATUS_ARGS)).stdout))

    def _separate(self, status: ParsedStatus) -> _State:
        """Remove secret files from the visible state (like the filesystem hides them)."""
        secret = self._validator.is_secret
        secrets = [c.path for c in status.staged + status.modified if secret(c.path)]
        secrets += [p for p in status.untracked + status.conflicted if secret(p)]
        visible = ParsedStatus(
            oid=status.oid,
            branch=status.branch,
            upstream=status.upstream,
            ahead=status.ahead,
            behind=status.behind,
            staged=[c for c in status.staged if not secret(c.path)],
            modified=[c for c in status.modified if not secret(c.path)],
            untracked=[p for p in status.untracked if not secret(p)],
            conflicted=[p for p in status.conflicted if not secret(p)],
        )
        return _State(
            status=visible,
            secrets=list(dict.fromkeys(secrets)),
            staged_secrets=[c.path for c in status.staged if secret(c.path)],
        )

    def _without_secrets(self, paths: Sequence[str]) -> tuple[list[str], list[str]]:
        files = [p for p in paths if not self._validator.is_secret(p)]
        return files, [p for p in paths if self._validator.is_secret(p)]

    async def _has_commits(self, root: ResolvedPath) -> bool:
        return (await self._git(root, "rev-parse", "--verify", "--quiet", "HEAD", check=False)).exit_code == 0

    async def _commit(self, root: ResolvedPath, ref: str) -> Commit:
        output = await self._git(root, "log", "-z", "--max-count=1", f"--format={LOG_FORMAT}", ref, "--")
        commits = parse_log(output.stdout)
        if not commits:
            raise GitCommandFailed(f"No commit found for {ref!r}")
        return commits[0]

    async def _current_branch(self, root: ResolvedPath) -> str | None:
        output = await self._git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
        return (output.stdout.strip() or None) if output.exit_code == 0 else None

    async def _remote(self, root: ResolvedPath, remote: str | None) -> str:
        known = [r.name for r in parse_remotes((await self._git(root, "remote", "-v")).stdout)]
        if remote is not None:
            name = self._validator.remote(remote)
            if name not in known:
                raise InvalidGitArgument(f"Unknown remote {name!r}. Remotes: {', '.join(known) or 'none'}")
            return name
        if "origin" in known:
            return "origin"
        if len(known) == 1:
            return known[0]
        raise InvalidGitArgument(
            f"Choose a remote: {', '.join(known)}" if known else "The repository has no remote"
        )


def _repository(root: ResolvedPath, status: ParsedStatus) -> Repository:
    return Repository(
        repository=root.relative,
        branch=status.branch,
        detached=status.branch is None,
        head=status.oid[:7] if status.oid else None,
        has_commits=status.oid is not None,
    )


def _remote_result(
    root: ResolvedPath, operation: RemoteOperation, remote: str | None, branch: str | None, output: GitOutput
) -> RemoteOperationResult:
    text = "\n".join(part.strip() for part in (output.stdout, output.stderr) if part.strip())
    return RemoteOperationResult(
        repository=root.relative,
        operation=operation,
        remote=remote,
        branch=branch,
        output=text,
        truncated=output.truncated,
    )


def _is_under(path: str, prefix: str) -> bool:
    return prefix == "." or path == prefix or path.startswith(prefix.rstrip("/") + "/")
