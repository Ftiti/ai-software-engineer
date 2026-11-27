"""Git tools through the tool system: registration, push only when enabled, readable errors."""

from pathlib import Path

import pytest

from app.capabilities.filesystem import build_filesystem_service
from app.capabilities.git import GitService, build_git_capability, build_git_service
from app.capabilities.git.prompts import GIT_PROMPT
from app.capabilities.git.tool import git_tools
from app.container import build_capabilities, build_local_tools
from app.tools import ToolManager, ToolRegistry, ToolRequest
from app.tools.adapters import LocalToolAdapter
from tests.conftest import make_settings
from tests.unit.git.conftest import commit_file

TOOL_NAMES = [
    "git_add",
    "git_branch",
    "git_checkout",
    "git_commit",
    "git_diff",
    "git_fetch",
    "git_log",
    "git_pull",
    "git_remote",
    "git_restore",
    "git_show",
    "git_status",
]


@pytest.fixture
def manager(service: GitService) -> ToolManager:
    return ToolManager(ToolRegistry(LocalToolAdapter(t) for t in git_tools(service)))


def call(name: str, **arguments: object) -> ToolRequest:
    return ToolRequest(tool_name=name, arguments=arguments, call_id=name)


def test_tools_are_registered_and_push_only_when_enabled(service: GitService) -> None:
    assert sorted(t.name for t in git_tools(service)) == TOOL_NAMES
    assert sorted(t.name for t in git_tools(service, allow_push=True)) == sorted([*TOOL_NAMES, "git_push"])


def test_schemas_describe_the_arguments(manager: ToolManager) -> None:
    commit = manager.registry.get("git_commit").spec.input_schema
    assert commit["required"] == ["message"]
    restore = manager.registry.get("git_restore").spec.input_schema
    assert "DISCARD" in restore["properties"]["staged"]["description"]


async def test_edit_stage_commit_through_the_tool_manager(manager: ToolManager, repo: Path) -> None:
    (repo / "app.py").write_text("print('fixed')\n")
    status = await manager.execute(call("git_status"))
    assert status.ok and status.output["modified"][0]["path"] == "app.py"

    assert (await manager.execute(call("git_checkout", branch="fix/app", create=True))).ok
    assert (await manager.execute(call("git_add", paths=["app.py"]))).output["staged"] == ["app.py"]
    committed = await manager.execute(call("git_commit", message="Fix app"))
    assert committed.ok and committed.output["branch"] == "fix/app"
    log = await manager.execute(call("git_log", limit=1))
    assert log.output["commits"][0]["subject"] == "Fix app"


@pytest.mark.parametrize(
    ("request_", "error"),
    [
        (call("git_commit", message="x"), "Nothing to commit"),
        (call("git_add", paths=["a"], all=True), "give either paths or all=true"),
        (call("git_add"), "give either paths or all=true"),
        (call("git_restore", paths=["."]), "whole repository"),
        (call("git_restore", paths=[]), "at least 1 item"),
        (call("git_show", path=".env"), "protected secret"),
        (call("git_diff", ref="--output=/tmp/x"), "Invalid reference"),
        (call("git_checkout", branch="a..b"), "Invalid branch name"),
        (call("git_status", repository=".."), "outside the workspace"),
        (call("git_log", limit=0), "greater than or equal to 1"),
        (call("git_push"), "Unknown tool 'git_push'"),  # not registered while push is disabled
    ],
)
async def test_errors_are_readable_tool_results(
    manager: ToolManager, repo: Path, request_: ToolRequest, error: str
) -> None:
    result = await manager.execute(request_)
    assert not result.ok
    assert error in (result.error or "")


async def test_not_a_repository_through_the_tool(manager: ToolManager) -> None:
    result = await manager.execute(call("git_status"))
    assert not result.ok and "is not inside a Git repository" in (result.error or "")


def test_capability_bundles_tools_and_prompt(workspace: Path) -> None:
    settings = make_settings(fs_workspace_root=workspace)
    service = build_git_service(settings, build_filesystem_service(settings).validator)
    capability = build_git_capability(service)
    assert capability.name == "git"
    assert sorted(t.name for t in capability.tools) == TOOL_NAMES
    assert capability.prompt == GIT_PROMPT and "never with terminal" in GIT_PROMPT


def test_container_registers_git(workspace: Path) -> None:
    settings = make_settings(fs_workspace_root=workspace)
    assert [c.name for c in build_capabilities(settings)] == [
        "filesystem",
        "code_intelligence",
        "terminal",
        "git",
    ]
    names = {t.name for t in build_local_tools(settings)}
    assert set(TOOL_NAMES) <= names and "git_push" not in names
    assert "git_push" in {
        t.name for t in build_local_tools(make_settings(fs_workspace_root=workspace, git_allow_push=True))
    }
    assert "git" not in [
        c.name for c in build_capabilities(make_settings(fs_workspace_root=workspace, git_enabled=False))
    ]


async def test_container_git_tools_work_on_the_workspace(workspace: Path, repo: Path) -> None:
    commit_file(repo, "x.txt", "x\n", "Add x")
    manager = ToolManager(
        ToolRegistry(
            LocalToolAdapter(t) for t in build_local_tools(make_settings(fs_workspace_root=workspace))
        )
    )
    result = await manager.execute(call("git_log", limit=1))
    assert result.ok and result.output["commits"][0]["subject"] == "Add x"


def test_settings_reject_git_timeouts_above_the_tool_timeout() -> None:
    with pytest.raises(
        ValueError, match="GIT_TIMEOUT and GIT_NETWORK_TIMEOUT must be lower than TOOL_TIMEOUT"
    ):
        make_settings(git_network_timeout=60)
