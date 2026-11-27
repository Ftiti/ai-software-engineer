"""GitValidator: operation policy, repository and paths, names, and the final argument guard."""

from pathlib import Path

import pytest

from app.capabilities.filesystem import FilesystemPolicy, PathValidator
from app.capabilities.filesystem.validator import ResolvedPath
from app.capabilities.git import GitOperation, GitPolicy, GitValidator
from app.capabilities.git.exceptions import (
    GitError,
    GitOperationNotAllowed,
    InvalidGitArgument,
    RepositoryOutsideWorkspace,
)
from app.providers.filesystem import LocalFilesystemProvider
from tests.unit.git.conftest import DENIED


def make_validator(workspace: Path, *, read_only: bool = False, **policy: object) -> GitValidator:
    paths = PathValidator(
        LocalFilesystemProvider(),
        FilesystemPolicy(
            workspace_root=workspace,
            read_only=read_only,
            denied_patterns=DENIED,
            protected_patterns=(".git",),
        ),
    )
    return GitValidator(paths, GitPolicy(read_only=read_only, **policy))  # type: ignore[arg-type]


@pytest.fixture
def validator(workspace: Path) -> GitValidator:
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("")
    return make_validator(workspace)


@pytest.fixture
def root(workspace: Path) -> ResolvedPath:
    return ResolvedPath(absolute=workspace.resolve(), relative=".")


# -- Operation policy -----------------------------------------------------------------------


def test_read_only_refuses_every_mutating_operation(workspace: Path) -> None:
    validator = make_validator(workspace, read_only=True, allow_push=True)
    for operation in GitOperation:
        if operation.mutating:
            with pytest.raises(GitOperationNotAllowed, match="read-only"):
                validator.check_allowed(operation)
        else:
            validator.check_allowed(operation)


def test_push_policy(workspace: Path) -> None:
    with pytest.raises(GitOperationNotAllowed, match=r"Push is disabled\. Set GIT_ALLOW_PUSH=true"):
        make_validator(workspace).check_allowed(GitOperation.PUSH, branch="feature")
    enabled = make_validator(workspace, allow_push=True, protected_branches=("main",))
    enabled.check_allowed(GitOperation.PUSH, branch="feature")
    with pytest.raises(GitOperationNotAllowed, match="'main' is not allowed \\(protected branch\\)"):
        enabled.check_allowed(GitOperation.PUSH, branch="main")


def test_operation_kinds() -> None:
    assert {o for o in GitOperation if o.network} == {
        GitOperation.FETCH,
        GitOperation.PULL,
        GitOperation.PUSH,
    }
    assert not GitOperation.FETCH.mutating  # only updates .git
    assert not GitOperation.STATUS.mutating and GitOperation.COMMIT.mutating


# -- Repository and paths -------------------------------------------------------------------


def test_repository_folder(validator: GitValidator, tmp_path: Path) -> None:
    assert validator.directory("src").relative == "src"
    for folder, error in [
        ("..", "outside the workspace"),
        ("missing", "does not exist"),
        ("src/app.py", "not a directory"),
    ]:
        with pytest.raises(GitError, match=error):
            validator.directory(folder)
    with pytest.raises(RepositoryOutsideWorkspace, match="outside the workspace"):
        validator.root(str(tmp_path))


def test_paths_are_normalised_relative_to_the_root(
    validator: GitValidator, root: ResolvedPath, workspace: Path
) -> None:
    assert validator.paths(root, ["src/app.py", "./src/../README.md", str(workspace / "src"), "-rf"]) == [
        "src/app.py",
        "README.md",
        "src",
        "-rf",  # given to git after '--', so it is a file name, never an option
    ]


@pytest.mark.parametrize(
    ("path", "error"),
    [
        ("../outside.txt", "outside the repository"),
        ("/etc/passwd", "outside the repository"),
        (".env", "protected secret"),
        ("config/server.pem", "protected secret"),
        ("", "Invalid path"),
    ],
)
def test_paths_refused(validator: GitValidator, root: ResolvedPath, path: str, error: str) -> None:
    with pytest.raises(GitError, match=error):
        validator.paths(root, [path])


def test_secrets_may_be_unstaged(validator: GitValidator, root: ResolvedPath) -> None:
    assert validator.paths(root, [".env"], allow_secrets=True) == [".env"]


def test_files_only(validator: GitValidator, root: ResolvedPath) -> None:
    assert validator.paths(root, ["src/app.py", "deleted.py"], files_only=True) == [
        "src/app.py",
        "deleted.py",
    ]
    with pytest.raises(InvalidGitArgument, match="whole repository"):
        validator.paths(root, ["."], files_only=True)
    with pytest.raises(InvalidGitArgument, match="is a directory"):
        validator.paths(root, ["src"], files_only=True)


def test_write_paths_respect_protection(validator: GitValidator, root: ResolvedPath) -> None:
    with pytest.raises(RepositoryOutsideWorkspace, match="protected"):
        validator.paths(root, [".git/config"], write=True)


# -- Names ----------------------------------------------------------------------------------


@pytest.mark.parametrize("ref", ["main", "HEAD~2", "HEAD^", "origin/main", "v1.0", "a1b2c3d", "main@{1}"])
def test_valid_references(validator: GitValidator, ref: str) -> None:
    assert validator.reference(ref) == ref


@pytest.mark.parametrize(
    "ref", ["", "--output=/tmp/x", "-n", "main..dev", "a b", "HEAD:secret", "x" * 300, "ma$in"]
)
def test_invalid_references(validator: GitValidator, ref: str) -> None:
    with pytest.raises(InvalidGitArgument):
        validator.reference(ref)


def test_ranges(validator: GitValidator) -> None:
    assert validator.reference("main..dev", allow_range=True) == "main..dev"
    assert validator.reference("main...dev", allow_range=True) == "main...dev"
    assert validator.reference("main..", allow_range=True) == "main.."
    for bad in ["..", "a..b..c", "-x..main"]:
        with pytest.raises(InvalidGitArgument):
            validator.reference(bad, allow_range=True)


@pytest.mark.parametrize("name", ["feature", "fix/login-bug", "release-1.2", "user/x_y"])
def test_valid_branch_names(validator: GitValidator, name: str) -> None:
    assert validator.branch_name(name) == name


@pytest.mark.parametrize(
    ("name", "error"),
    [
        ("-x", "may not start with '-'"),
        ("a..b", "may not contain '..'"),
        ("bad name", "spaces"),
        ("a:b", "spaces or any of"),
        ("x.lock", "may not end"),
        ("x/", "may not end"),
        (".hidden", "starts with '.'"),
        ("a/.b", "starts with '.'"),
        ("HEAD", "reserved"),
        ("a@{b", "'@{'"),
        ("a//b", "'//'"),
        ("", "empty"),
    ],
)
def test_invalid_branch_names(validator: GitValidator, name: str, error: str) -> None:
    with pytest.raises(InvalidGitArgument, match=error.replace("(", "\\(")):
        validator.branch_name(name)


def test_remote_message_and_limit(validator: GitValidator) -> None:
    assert validator.remote("origin") == "origin"
    for bad in ["-origin", "a b", "", "../x"]:
        with pytest.raises(InvalidGitArgument):
            validator.remote(bad)
    assert validator.message("  Fix bug\n\nDetails  ") == "Fix bug\n\nDetails"
    for bad, error in [("   ", "empty"), ("a\x00b", "NUL"), ("x" * 10_001, "longer")]:
        with pytest.raises(InvalidGitArgument, match=error):
            validator.message(bad)
    assert validator.log_limit(100) == 100
    with pytest.raises(InvalidGitArgument, match="between 1 and 100"):
        validator.log_limit(101)


# -- Final guard ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ("status", "--porcelain=v2"),
        ("commit", "--cleanup=strip", "--message=--force everything"),
        ("push", "--set-upstream", "origin", "main"),
        ("add", "--", "-f", "--hard"),  # after '--' these are file names
    ],
)
def test_guard_accepts_what_the_service_builds(validator: GitValidator, args: tuple[str, ...]) -> None:
    validator.guard(args)


@pytest.mark.parametrize(
    "args",
    [
        ("reset", "--hard"),
        ("clean", "-fdx"),
        ("rebase", "main"),
        ("config", "core.hooksPath", "/tmp"),
        ("init",),
        ("rm", "-r", "."),
        ("filter-branch",),
        ("gc", "--prune=now"),
        ("checkout", "--", "."),
        ("push", "--force", "origin", "main"),
        ("push", "-f", "origin", "main"),
        ("push", "--force-with-lease", "origin"),
        ("push", "origin", "+main"),
        ("push", "origin", ":main"),
        ("push", "--delete", "origin", "main"),
        ("push", "--mirror", "origin"),
        ("branch", "-D", "main"),
        ("branch", "-d", "main"),
        ("commit", "--amend", "--message=x"),
        ("commit", "--no-verify", "--message=x"),
        ("fetch", "--upload-pack=evil", "origin"),
        ("switch", "-c", "x"),
        (),
    ],
)
def test_guard_refuses_dangerous_operations(validator: GitValidator, args: tuple[str, ...]) -> None:
    with pytest.raises(GitOperationNotAllowed):
        validator.guard(args)
