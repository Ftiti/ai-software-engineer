"""Errors of the Git capability. Messages are written to be shown to the LLM."""


class GitError(Exception):
    """Base class. Any Git failure the caller should see."""


class NotARepository(GitError):
    pass


class RepositoryOutsideWorkspace(GitError):
    """The repository root or a path is outside the workspace, or is a protected secret."""


class InvalidGitArgument(GitError):
    """Malformed path, reference, branch name, remote, commit message or limit."""


class GitOperationNotAllowed(GitError):
    """Refused by the policy: read-only workspace, push disabled, protected branch, dangerous flag."""


class NothingToCommit(GitError):
    pass


class ConflictsPresent(GitError):
    pass


class GitCommandFailed(GitError):
    """Git ran and failed; the message carries Git's own explanation."""


class GitNotInstalled(GitError):
    pass


class GitTimeout(GitError):
    pass
