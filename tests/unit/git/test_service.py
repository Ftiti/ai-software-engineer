"""GitService on real repositories: the acceptance scenarios of User Stories 1-5 (spec.md)."""

from pathlib import Path

import pytest

from app.capabilities.git import GitService
from app.capabilities.git.exceptions import (
    ConflictsPresent,
    GitCommandFailed,
    GitNotInstalled,
    GitOperationNotAllowed,
    GitTimeout,
    InvalidGitArgument,
    NotARepository,
    NothingToCommit,
    RepositoryOutsideWorkspace,
)
from app.providers.git import GitInvocation, GitOutput, GitProvider, LocalGitProvider
from app.providers.terminal import LocalTerminalProvider
from tests.unit.git.conftest import MakeService, commit_file, git
from tests.unit.git.test_validator import make_validator

# -- US1: understand the state of the repository --------------------------------------------


async def test_status_of_a_clean_repository(service: GitService, repo: Path) -> None:
    status = await service.status()
    assert status.clean
    assert status.repository.branch == "main"
    assert status.repository.has_commits and not status.repository.detached
    assert status.repository.head == git(repo, "rev-parse", "--short=7", "HEAD").strip()
    assert (status.upstream, status.ahead, status.behind) == (None, 0, 0)


async def test_status_groups_files_and_hides_secrets(service: GitService, repo: Path) -> None:
    (repo / "README.md").write_text("# Changed\n")
    (repo / "new.py").write_text("x = 1\n")
    git(repo, "add", "new.py")
    (repo / "notes.txt").write_text("todo\n")
    (repo / ".env").write_text("API_KEY=secret\n")

    status = await service.status()

    assert [(c.path, c.change) for c in status.staged] == [("new.py", "added")]
    assert [(c.path, c.change) for c in status.modified] == [("README.md", "modified")]
    assert status.untracked == ["notes.txt"]
    assert status.secrets_hidden == 1 and ".env" not in status.untracked
    assert not status.clean


async def test_status_reports_conflicts_and_commit_refuses_them(service: GitService, repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "feature")
    commit_file(repo, "README.md", "# Feature\n", "Feature title")
    git(repo, "switch", "-q", "main")
    commit_file(repo, "README.md", "# Main\n", "Main title")
    git(repo, "merge", "feature", check=False)  # conflict, done by the developer

    status = await service.status()
    assert status.conflicted == ["README.md"]
    with pytest.raises(ConflictsPresent, match=r"unresolved conflicts in README\.md"):
        await service.commit(message="Merge")


async def test_status_ahead_of_upstream(service: GitService, repo: Path, remote: Path) -> None:
    commit_file(repo, "a.txt", "a\n", "Local work")
    status = await service.status()
    assert (status.upstream, status.ahead, status.behind) == ("origin/main", 1, 0)


async def test_empty_repository(service: GitService, workspace: Path) -> None:
    git(workspace, "init", "-q", "-b", "main")
    status = await service.status()
    assert (status.repository.branch, status.repository.has_commits, status.repository.head) == (
        "main",
        False,
        None,
    )
    assert (await service.log()).commits == []


async def test_detached_head(service: GitService, repo: Path) -> None:
    git(repo, "switch", "-q", "--detach", "HEAD~1")
    status = await service.status()
    assert status.repository.detached and status.repository.branch is None
    (repo / "app.py").write_text("print('detached')\n")
    await service.add(paths=["app.py"])
    result = await service.commit(message="Work on a detached HEAD")
    assert result.detached and result.branch is None


async def test_not_a_repository(service: GitService) -> None:
    with pytest.raises(NotARepository, match="is not inside a Git repository"):
        await service.status()


async def test_repository_root_outside_the_workspace(tmp_path: Path, make_service: MakeService) -> None:
    """The workspace is a sub-folder of a bigger repository: operations would leave the workspace."""
    outer = tmp_path / "outer"
    outer.mkdir()
    git(outer, "init", "-q", "-b", "main")
    workspace = outer / "workspace"
    workspace.mkdir()
    service = GitService(
        make_validator(workspace), LocalGitProvider(LocalTerminalProvider(), inherited_env=("PATH", "HOME"))
    )
    with pytest.raises(RepositoryOutsideWorkspace, match="outside the workspace"):
        await service.status()


async def test_diff_of_working_copy_staging_area_and_commits(service: GitService, repo: Path) -> None:
    (repo / "README.md").write_text("# Changed\n")
    (repo / "app.py").write_text("print('bye')\n")
    git(repo, "add", "app.py")

    working = await service.diff()
    assert working.files == ["README.md"] and "+# Changed" in working.diff
    staged = await service.diff(staged=True)
    assert staged.files == ["app.py"] and "+print('bye')" in staged.diff
    only = await service.diff(ref="HEAD", paths=["README.md"])
    assert only.files == ["README.md"]
    between = await service.diff(ref="HEAD~1", target="HEAD", stat_only=True)
    assert between.files == ["app.py"] and "1 file changed" in between.diff


async def test_diff_never_shows_secrets(service: GitService, repo: Path) -> None:
    commit_file(repo, ".env", "API_KEY=old\n", "Committed by mistake (outside the agent)")
    (repo / ".env").write_text("API_KEY=new-secret\n")
    (repo / "README.md").write_text("# Changed\n")

    result = await service.diff()
    assert result.files == ["README.md"] and result.omitted_secrets == [".env"]
    assert "secret" not in result.diff and "API_KEY" not in result.diff


async def test_log(service: GitService, repo: Path) -> None:
    commit_file(repo, "docs/guide.md", "guide\n", "Add guide")
    log = await service.log(limit=2)
    assert [c.subject for c in log.commits] == ["Add guide", "Add app"]
    assert log.commits[0].author == "Test User" and log.commits[0].email == "test@example.com"
    assert [c.subject for c in (await service.log(paths=["README.md"])).commits] == ["Initial commit"]
    assert [c.subject for c in (await service.log(ref="HEAD~2..HEAD")).commits] == ["Add guide", "Add app"]
    with pytest.raises(InvalidGitArgument, match="between 1 and 100"):
        await service.log(limit=500)


async def test_show_commit_and_file_at_commit(service: GitService, repo: Path) -> None:
    commit_file(repo, "app.py", "print('v2')\n", "Update app")
    shown = await service.show()
    assert shown.commit.subject == "Update app"
    assert "+print('v2')" in shown.content and "app.py" in shown.content
    old = await service.show(ref="HEAD~1", path="app.py")
    assert old.content == "print('hello')\n"


async def test_show_never_reveals_secrets(service: GitService, repo: Path) -> None:
    commit_file(repo, ".env", "API_KEY=secret\n", "Oops")
    shown = await service.show()
    assert shown.omitted_secrets == [".env"] and "secret" not in shown.content
    with pytest.raises(RepositoryOutsideWorkspace, match="protected secret"):
        await service.show(path=".env")


async def test_show_errors(service: GitService, repo: Path) -> None:
    with pytest.raises(GitCommandFailed, match="git log failed"):
        await service.show(ref="no-such-branch")
    with pytest.raises(InvalidGitArgument, match="Invalid reference"):
        await service.show(ref="--output=/tmp/x")


# -- US2: save work as commits --------------------------------------------------------------


async def test_add_paths_then_commit(service: GitService, repo: Path) -> None:
    (repo / "README.md").write_text("# Changed\n")
    (repo / "app.py").write_text("print('changed')\n")

    added = await service.add(paths=["app.py"])
    assert added.staged == ["app.py"]
    committed = await service.commit(message="Change app\n\nWith details.")
    assert committed.commit.subject == "Change app" and committed.commit.body == "With details."
    assert (committed.branch, committed.files_changed, committed.detached) == ("main", 1, False)
    assert [c.path for c in (await service.status()).modified] == ["README.md"]


@pytest.mark.parametrize("request_", [{"all": True}, {"paths": ["."]}, {"paths": ["config"]}])
async def test_add_never_stages_secrets(service: GitService, repo: Path, request_: dict[str, object]) -> None:
    (repo / "config").mkdir()
    (repo / "config" / "settings.py").write_text("DEBUG = True\n")
    (repo / "config" / ".env").write_text("API_KEY=secret\n")
    (repo / ".env").write_text("API_KEY=secret\n")

    added = await service.add(**request_)  # type: ignore[arg-type]

    assert added.staged == ["config/settings.py"]
    assert set(added.skipped_secrets) <= {".env", "config/.env"} and added.skipped_secrets
    assert ".env" not in git(repo, "diff", "--cached", "--name-only")


async def test_add_refuses_an_explicit_secret_and_reads_patterns_literally(
    service: GitService, repo: Path
) -> None:
    (repo / ".env").write_text("API_KEY=secret\n")
    with pytest.raises(RepositoryOutsideWorkspace, match="protected secret"):
        await service.add(paths=[".env"])
    (repo / "a.py").write_text("")
    assert (await service.add(paths=["*.py"])).staged == []  # '*' is a character, not a pattern


async def test_add_stages_deletions(service: GitService, repo: Path) -> None:
    (repo / "app.py").unlink()
    assert (await service.add(all=True)).staged == ["app.py"]
    assert [(c.path, c.change) for c in (await service.status()).staged] == [("app.py", "deleted")]


async def test_commit_refusals(service: GitService, repo: Path) -> None:
    with pytest.raises(NothingToCommit, match="use git_add first"):
        await service.commit(message="Nothing")
    with pytest.raises(InvalidGitArgument, match="empty"):
        await service.commit(message="   ")
    (repo / ".env").write_text("API_KEY=secret\n")
    git(repo, "add", "-f", ".env")  # staged outside the agent
    with pytest.raises(GitOperationNotAllowed, match=r"secret file\(s\) staged: \.env"):
        await service.commit(message="Leak")
    await service.restore(paths=[".env"], staged=True)  # the way out
    assert (await service.status()).staged == []


async def test_read_only_workspace(make_service: MakeService, repo: Path) -> None:
    service = make_service(read_only=True)
    (repo / "README.md").write_text("# Changed\n")
    assert (await service.status()).modified  # inspection still works
    for call in (
        service.add(all=True),
        service.commit(message="x"),
        service.checkout(branch="x", create=True),
        service.restore(paths=["README.md"]),
        service.create_branch(name="x"),
    ):
        with pytest.raises(GitOperationNotAllowed, match="read-only"):
            await call


# -- US3: work on branches ------------------------------------------------------------------


async def test_branches_create_and_switch(service: GitService, repo: Path) -> None:
    created = await service.create_branch(name="dev")
    assert (created.branch, created.start_point, created.switched) == ("dev", "HEAD", False)
    listing = await service.branches()
    assert listing.current == "main" and [b.name for b in listing.branches] == ["dev", "main"]

    switched = await service.checkout(branch="fix/login", create=True, start_point="HEAD~1")
    assert (switched.branch, switched.created, switched.previous) == ("fix/login", True, "main")
    assert git(repo, "branch", "--show-current").strip() == "fix/login"
    assert not (repo / "app.py").exists()  # started from the first commit
    back = await service.checkout(branch="main")
    assert (back.previous, back.created) == ("fix/login", False)


async def test_remote_branches_on_request(service: GitService, repo: Path, remote: Path) -> None:
    names = [b.name for b in (await service.branches(include_remote=True)).branches]
    assert names == ["main", "origin/main"]
    assert next(b for b in (await service.branches()).branches if b.name == "main").upstream == "origin/main"


async def test_checkout_never_overwrites_local_changes(service: GitService, repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "other")
    commit_file(repo, "README.md", "# Other\n", "Other title")
    git(repo, "switch", "-q", "main")
    (repo / "README.md").write_text("# My uncommitted work\n")

    with pytest.raises(GitCommandFailed, match="git switch failed"):
        await service.checkout(branch="other")
    assert (repo / "README.md").read_text() == "# My uncommitted work\n"


@pytest.mark.parametrize("name", ["-x", "a..b", "bad name"])
async def test_invalid_branch_names(service: GitService, repo: Path, name: str) -> None:
    with pytest.raises(InvalidGitArgument, match="Invalid branch name"):
        await service.checkout(branch=name, create=True)


# -- US4: undo local changes safely ---------------------------------------------------------


async def test_unstage_keeps_changes_and_discard_restores(service: GitService, repo: Path) -> None:
    (repo / "app.py").write_text("print('changed')\n")
    (repo / "README.md").write_text("# Keep me\n")
    git(repo, "add", "app.py")

    unstaged = await service.restore(paths=["app.py"], staged=True)
    assert unstaged.staged and (repo / "app.py").read_text() == "print('changed')\n"
    discarded = await service.restore(paths=["app.py"])
    assert not discarded.staged and (repo / "app.py").read_text() == "print('hello')\n"
    assert (repo / "README.md").read_text() == "# Keep me\n"  # untouched


@pytest.mark.parametrize(("paths", "error"), [(["."], "whole repository"), (["docs"], "is a directory")])
async def test_discard_needs_explicit_files(
    service: GitService, repo: Path, paths: list[str], error: str
) -> None:
    (repo / "docs").mkdir()
    with pytest.raises(InvalidGitArgument, match=error):
        await service.restore(paths=paths)


# -- US5: synchronise with remotes ----------------------------------------------------------


async def test_remotes_are_listed_with_masked_credentials(service: GitService, repo: Path) -> None:
    git(repo, "remote", "add", "origin", "https://user:ghp_secret@example.com/me/repo.git")
    remotes = (await service.remotes()).remotes
    assert [(r.name, r.fetch_url) for r in remotes] == [("origin", "https://***@example.com/me/repo.git")]


async def test_fetch_then_fast_forward_pull(service: GitService, repo: Path, other_clone: Path) -> None:
    commit_file(other_clone, "upstream.txt", "new\n", "Upstream work")
    git(other_clone, "push", "-q")

    fetched = await service.fetch()
    assert (fetched.operation, fetched.remote) == ("fetch", "origin")
    assert (await service.status()).behind == 1
    await service.pull()
    assert (repo / "upstream.txt").read_text() == "new\n"


async def test_diverged_pull_is_refused(service: GitService, repo: Path, other_clone: Path) -> None:
    commit_file(other_clone, "upstream.txt", "new\n", "Upstream work")
    git(other_clone, "push", "-q")
    commit_file(repo, "local.txt", "mine\n", "Local work")

    with pytest.raises(GitCommandFailed, match="git pull failed"):
        await service.pull()
    assert git(repo, "log", "-1", "--format=%s").strip() == "Local work"  # nothing merged


async def test_push_disabled_by_default(service: GitService, repo: Path, remote: Path) -> None:
    with pytest.raises(GitOperationNotAllowed, match="Push is disabled"):
        await service.push()


async def test_push_when_enabled(make_service: MakeService, repo: Path, remote: Path) -> None:
    service = make_service(allow_push=True, protected_branches=("release",))
    await service.checkout(branch="feature", create=True)
    commit_file(repo, "f.txt", "f\n", "Feature work")

    pushed = await service.push(set_upstream=True)
    assert (pushed.remote, pushed.branch) == ("origin", "feature")
    assert git(remote, "log", "-1", "--format=%s", "feature").strip() == "Feature work"
    assert (await service.status()).upstream == "origin/feature"


async def test_push_refusals(make_service: MakeService, repo: Path, remote: Path) -> None:
    service = make_service(allow_push=True, protected_branches=("main",))
    with pytest.raises(GitOperationNotAllowed, match="'main' is not allowed \\(protected branch\\)"):
        await service.push()
    with pytest.raises(InvalidGitArgument, match=r"Unknown remote 'upstream'\. Remotes: origin"):
        await make_service(allow_push=True).push(remote="upstream")
    git(repo, "switch", "-q", "--detach")
    with pytest.raises(GitOperationNotAllowed, match="detached"):
        await service.push()


async def test_no_remote(service: GitService, repo: Path) -> None:
    with pytest.raises(InvalidGitArgument, match="has no remote"):
        await service.fetch()


# -- Failures of git itself -----------------------------------------------------------------


class _FakeProvider(GitProvider):
    def __init__(self, output: GitOutput | None = None, error: Exception | None = None) -> None:
        self.output, self.error = output, error

    async def run(self, invocation: GitInvocation) -> GitOutput:
        if self.error:
            raise self.error
        assert self.output is not None
        return self.output


async def test_git_not_installed(make_service: MakeService, repo: Path) -> None:
    with pytest.raises(GitNotInstalled, match="not installed"):
        await make_service(provider=_FakeProvider(error=FileNotFoundError())).status()


async def test_git_timeout(make_service: MakeService, repo: Path) -> None:
    timed_out = GitOutput(exit_code=-9, stdout="", stderr="", timed_out=True, truncated=False)
    with pytest.raises(GitTimeout, match=r"did not finish within 30\.0s"):
        await make_service(provider=_FakeProvider(timed_out)).status()
