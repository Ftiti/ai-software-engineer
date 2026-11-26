"""Filesystem tools through the tool system: registry, manager and the composition root."""

from pathlib import Path

import pytest

from app.capabilities.filesystem import (
    FilesystemService,
    build_filesystem_capability,
    build_filesystem_service,
)
from app.capabilities.filesystem.prompts import FILESYSTEM_PROMPT
from app.capabilities.filesystem.tool import filesystem_tools
from app.container import build_capabilities, build_local_tools
from app.tools import ToolManager, ToolRegistry, ToolRequest
from app.tools.adapters import LocalToolAdapter
from tests.conftest import make_settings

TOOL_NAMES = ["create_file", "delete_file", "list_files", "read_file", "write_file"]


@pytest.fixture
def manager(service: FilesystemService) -> ToolManager:
    return ToolManager(ToolRegistry(LocalToolAdapter(t) for t in filesystem_tools(service)))


def call(name: str, **arguments: object) -> ToolRequest:
    return ToolRequest(tool_name=name, arguments=arguments, call_id=name)


def test_all_tools_are_registered(manager: ToolManager) -> None:
    specs = manager.list_tools()
    assert [s.name for s in specs] == TOOL_NAMES
    assert all(s.source == "local" and s.description for s in specs)


def test_input_schema_describes_arguments(manager: ToolManager) -> None:
    schema = manager.registry.get("read_file").spec.input_schema
    assert schema["required"] == ["path"]
    assert "relative to the workspace root" in schema["properties"]["path"]["description"]


async def test_list_files(manager: ToolManager) -> None:
    result = await manager.execute(call("list_files", path="src"))
    assert result.ok
    assert [e["path"] for e in result.output["entries"]] == ["src/app.py", "src/utils"]


async def test_read_write_create_delete_round_trip(manager: ToolManager, workspace: Path) -> None:
    created = await manager.execute(call("create_file", path="notes.md", content="v1"))
    assert created.ok and created.output["created"]

    written = await manager.execute(call("write_file", path="notes.md", content="v2"))
    assert written.ok and not written.output["created"]

    read = await manager.execute(call("read_file", path="notes.md"))
    assert read.output["content"] == "v2"

    deleted = await manager.execute(call("delete_file", path="notes.md"))
    assert deleted.ok
    assert not (workspace / "notes.md").exists()


@pytest.mark.parametrize(
    ("request_", "error"),
    [
        (call("read_file", path="../../etc/passwd"), "outside the workspace"),
        (call("read_file", path=".env"), "protected secret"),
        (call("read_file", path="missing.txt"), "does not exist"),
        (call("write_file", path=".git/config", content="x"), "protected"),
        (call("create_file", path="README.md"), "already exists"),
        (call("read_file"), "path: Field required"),
    ],
)
async def test_errors_become_readable_tool_results(
    manager: ToolManager, request_: ToolRequest, error: str
) -> None:
    result = await manager.execute(request_)
    assert not result.ok
    assert error in (result.error or "")


def test_capability_bundles_tools_and_prompt(workspace: Path) -> None:
    capability = build_filesystem_capability(
        build_filesystem_service(make_settings(fs_workspace_root=workspace))
    )
    assert capability.name == "filesystem"
    assert sorted(t.name for t in capability.tools) == TOOL_NAMES
    assert capability.prompt == FILESYSTEM_PROMPT
    assert "Never guess file contents" in capability.prompt


def test_container_registers_filesystem_tools_automatically(workspace: Path) -> None:
    settings = make_settings(fs_workspace_root=workspace)
    assert build_capabilities(settings)[0].name == "filesystem"
    assert set(TOOL_NAMES) <= {t.name for t in build_local_tools(settings)}
