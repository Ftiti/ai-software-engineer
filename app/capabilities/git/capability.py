"""Assembles the Git capability: terminal provider -> git provider -> validator -> service -> tools."""

from app.capabilities.base import Capability
from app.capabilities.filesystem import PathValidator
from app.capabilities.git.prompts import GIT_PROMPT
from app.capabilities.git.service import GitService
from app.capabilities.git.tool import git_tools
from app.capabilities.git.validator import GitPolicy, GitValidator
from app.config import Settings
from app.providers.git import GitProvider, LocalGitProvider
from app.providers.terminal import LocalTerminalProvider, TerminalProvider


def build_git_service(
    settings: Settings,
    paths: PathValidator,
    *,
    provider: GitProvider | None = None,
    terminal: TerminalProvider | None = None,
) -> GitService:
    """``paths`` is the filesystem validator: repositories are confined to the same workspace.

    Git runs through ``terminal`` (default: a local terminal provider), which starts the processes.
    """
    git = provider or LocalGitProvider(
        terminal or LocalTerminalProvider(),
        executable=settings.git_executable,
        inherited_env=[*settings.terminal_inherited_env, *settings.git_extra_inherited_env],
        hooks=settings.git_allow_hooks,
    )
    return GitService(GitValidator(paths, GitPolicy.from_settings(settings)), git)


def build_git_capability(service: GitService, *, allow_push: bool = False) -> Capability:
    return Capability(name="git", tools=git_tools(service, allow_push=allow_push), prompt=GIT_PROMPT)
