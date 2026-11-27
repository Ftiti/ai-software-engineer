"""Shared fixtures: real Git repositories in a temporary workspace, and a local bare remote.

The developer's own Git configuration never applies: ``HOME`` points to a temporary folder with
a minimal ``.gitconfig`` (identity, default branch), for both the tests and the capability.
"""

import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.capabilities.filesystem import FilesystemPolicy, PathValidator
from app.capabilities.git import GitPolicy, GitService, GitValidator
from app.providers.filesystem import LocalFilesystemProvider
from app.providers.git import GitProvider, LocalGitProvider
from app.providers.terminal import LocalTerminalProvider

DENIED = (".env", "*.pem")


@pytest.fixture(autouse=True)
def git_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path_factory.mktemp("home")
    (home / ".gitconfig").write_text(
        "[user]\n\tname = Test User\n\temail = test@example.com\n"
        "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n"
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return home


def git(cwd: Path, *args: str, check: bool = True) -> str:
    """Run git directly, as the developer would (test setup only)."""
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, env=os.environ, check=False
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def commit_file(repo: Path, name: str, content: str, message: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    git(repo, "add", "-f", name)
    git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def repo(workspace: Path) -> Path:
    """A repository at the workspace root with two commits: README.md and app.py."""
    git(workspace, "init", "-q", "-b", "main")
    commit_file(workspace, "README.md", "# Demo\n", "Initial commit")
    commit_file(workspace, "app.py", "print('hello')\n", "Add app")
    return workspace


@pytest.fixture
def remote(tmp_path: Path, repo: Path) -> Path:
    """A bare repository registered as 'origin', with main pushed and tracked."""
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")
    return bare


@pytest.fixture
def other_clone(tmp_path: Path, remote: Path) -> Path:
    """Another developer's clone of the remote, to create upstream commits."""
    clone = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(remote), str(clone))
    return clone


MakeService = Callable[..., GitService]


@pytest.fixture
def make_service(workspace: Path) -> MakeService:
    def make(*, read_only: bool = False, provider: GitProvider | None = None, **policy: Any) -> GitService:
        paths = PathValidator(
            LocalFilesystemProvider(),
            FilesystemPolicy(
                workspace_root=workspace,
                read_only=read_only,
                denied_patterns=DENIED,
                protected_patterns=(".git",),
            ),
        )
        git_provider = provider or LocalGitProvider(LocalTerminalProvider(), inherited_env=("PATH", "HOME"))
        return GitService(GitValidator(paths, GitPolicy(read_only=read_only, **policy)), git_provider)

    return make


@pytest.fixture
def service(make_service: MakeService) -> GitService:
    return make_service()
