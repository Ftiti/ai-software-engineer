"""Typed requests and responses of the Git capability (see specs/001-git-capability/data-model.md).

Requests double as tool input models: their field descriptions end up in the JSON Schema the
LLM reads. Paths are relative to the repository root and use ``/``; ``repository`` is the
repository folder relative to the workspace root.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _paths(description: str) -> list[str]:
    return Field(default_factory=list, description=description)


# -- Requests -------------------------------------------------------------------------------


class GitTarget(_Model):
    repository: str = Field(default=".", description="Repository folder, relative to the workspace root.")


class GitStatusRequest(GitTarget):
    pass


class GitDiffRequest(GitTarget):
    staged: bool = Field(default=False, description="Show staged changes (what the next commit contains).")
    ref: str | None = Field(
        default=None, description="Compare with this commit/branch, or a range like 'main..feature'."
    )
    target: str | None = Field(default=None, description="Second commit/branch: compare ref with target.")
    paths: list[str] = _paths("Limit the diff to these files or folders.")
    stat_only: bool = Field(default=False, description="Only a per-file summary of changed lines.")


class GitLogRequest(GitTarget):
    limit: int = Field(default=20, ge=1, description="Number of commits, most recent first.")
    ref: str | None = Field(default=None, description="Branch, commit or range. Default: current branch.")
    paths: list[str] = _paths("Only commits touching these files or folders.")


class GitShowRequest(GitTarget):
    ref: str = Field(default="HEAD", description="Commit to show (hash, branch, 'HEAD~1'...).")
    path: str | None = Field(default=None, description="Show this file's content at that commit instead.")


class GitBranchRequest(GitTarget):
    create: str | None = Field(default=None, description="Create a branch with this name (no switch).")
    start_point: str | None = Field(default=None, description="Where the new branch starts. Default: HEAD.")
    include_remote: bool = Field(default=False, description="Also list remote-tracking branches.")


class GitCheckoutRequest(GitTarget):
    branch: str = Field(description="Branch to switch to.")
    create: bool = Field(default=False, description="Create the branch first.")
    start_point: str | None = Field(default=None, description="Start of the new branch (with create).")


class GitAddRequest(GitTarget):
    paths: list[str] = _paths("Files or folders to stage.")
    all: bool = Field(default=False, description="Stage every change (secret files are always skipped).")

    @model_validator(mode="after")
    def _paths_or_all(self) -> Self:
        if bool(self.paths) == self.all:
            raise ValueError("give either paths or all=true")
        return self


class GitCommitRequest(GitTarget):
    message: str = Field(
        description="Commit message: a short summary line, optionally a blank line and details."
    )


class GitRestoreRequest(GitTarget):
    paths: list[str] = Field(min_length=1, description="Files to restore, named explicitly.")
    staged: bool = Field(
        default=False,
        description="true: only unstage (changes kept). false: DISCARD the files' uncommitted changes.",
    )


class GitRemoteRequest(GitTarget):
    pass


class GitFetchRequest(GitTarget):
    remote: str | None = Field(default=None, description="Remote name. Default: 'origin' or the only remote.")


class GitPullRequest(GitTarget):
    remote: str | None = Field(default=None, description="Remote name. Default: the branch's upstream.")
    branch: str | None = Field(default=None, description="Remote branch. Default: the branch's upstream.")


class GitPushRequest(GitTarget):
    remote: str | None = Field(default=None, description="Remote name. Default: 'origin' or the only remote.")
    set_upstream: bool = Field(default=False, description="Make the remote branch the upstream.")


# -- Responses ------------------------------------------------------------------------------

ChangeType = Literal["added", "modified", "deleted", "renamed", "copied", "type_changed", "unmerged"]


class Repository(_Model):
    repository: str = Field(description="Repository root, relative to the workspace root.")
    branch: str | None = Field(description="Current branch; null when HEAD is detached.")
    detached: bool
    head: str | None = Field(description="Short hash of the current commit; null without commits.")
    has_commits: bool


class FileChange(_Model):
    path: str
    change: ChangeType
    original_path: str | None = None  # renamed / copied from


class RepositoryStatus(_Model):
    repository: Repository
    upstream: str | None
    ahead: int
    behind: int
    staged: list[FileChange]
    modified: list[FileChange] = Field(description="Changed in the working copy, not staged.")
    untracked: list[str]
    conflicted: list[str]
    clean: bool
    secrets_hidden: int = Field(description="Changed secret files (e.g. .env), not listed.")
    truncated: bool


class DiffResult(_Model):
    repository: str
    files: list[str]
    diff: str
    stat_only: bool
    omitted_secrets: list[str]
    truncated: bool


class Commit(_Model):
    hash: str
    short_hash: str
    author: str
    email: str
    date: str  # ISO 8601
    subject: str
    body: str


class LogResult(_Model):
    repository: str
    commits: list[Commit]
    limit: int


class ShowResult(_Model):
    repository: str
    commit: Commit
    path: str | None
    content: str = Field(description="The commit's changes, or the file content when path is given.")
    omitted_secrets: list[str]
    truncated: bool


class Branch(_Model):
    name: str
    current: bool
    remote: bool
    upstream: str | None
    commit: str
    subject: str


class BranchList(_Model):
    repository: str
    current: str | None
    branches: list[Branch]


class BranchCreated(_Model):
    repository: str
    branch: str
    start_point: str
    switched: bool


class CheckoutResult(_Model):
    repository: str
    branch: str
    created: bool
    previous: str | None


class AddResult(_Model):
    repository: str
    staged: list[str]
    skipped_secrets: list[str]


class CommitResult(_Model):
    repository: str
    commit: Commit
    branch: str | None
    detached: bool
    files_changed: int


class RestoreResult(_Model):
    repository: str
    paths: list[str]
    staged: bool = Field(description="true: unstaged only; false: working-copy changes discarded.")


class Remote(_Model):
    name: str
    fetch_url: str | None
    push_url: str | None


class RemoteList(_Model):
    repository: str
    remotes: list[Remote]


class RemoteOperationResult(_Model):
    repository: str
    operation: Literal["fetch", "pull", "push"]
    remote: str | None
    branch: str | None
    output: str
    truncated: bool
