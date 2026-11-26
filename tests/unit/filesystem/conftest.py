"""Shared fixtures: a small project in a temporary workspace."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.capabilities.filesystem import FilesystemPolicy, FilesystemService, PathValidator
from app.providers.filesystem import LocalFilesystemProvider

DEFAULT_POLICY = {
    "denied_patterns": (".env", "*.pem"),
    "protected_patterns": (".git",),
    "ignored_patterns": (".git", "node_modules"),
}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """
    workspace/
        README.md
        .env                 (secret)
        .git/config          (protected)
        src/app.py
        src/utils/helpers.py
        node_modules/lib.js  (ignored by recursive listings)
    """
    root = tmp_path / "workspace"
    (root / "src" / "utils").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "node_modules").mkdir()
    (root / "README.md").write_text("# Demo\n")
    (root / ".env").write_text("API_KEY=secret\n")
    (root / ".git" / "config").write_text("[core]\n")
    (root / "src" / "app.py").write_text("print('hi')\n")
    (root / "src" / "utils" / "helpers.py").write_text("def help(): ...\n")
    (root / "node_modules" / "lib.js").write_text("//\n")
    return root


MakePolicy = Callable[..., FilesystemPolicy]
MakeService = Callable[..., FilesystemService]


@pytest.fixture
def make_policy(workspace: Path) -> MakePolicy:
    def make(**overrides: Any) -> FilesystemPolicy:
        return FilesystemPolicy(**{"workspace_root": workspace, **DEFAULT_POLICY, **overrides})

    return make


@pytest.fixture
def make_service(make_policy: MakePolicy) -> MakeService:
    def make(**overrides: Any) -> FilesystemService:
        provider = LocalFilesystemProvider()
        return FilesystemService(provider, PathValidator(provider, make_policy(**overrides)))

    return make


@pytest.fixture
def service(make_service: MakeService) -> FilesystemService:
    return make_service()
