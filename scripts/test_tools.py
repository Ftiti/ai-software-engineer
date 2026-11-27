"""Manual check of the tool pipeline on the real workspace (FS_WORKSPACE_ROOT, default: here).

Builds the tool manager exactly like the application (capability tools + MCP tools), lists
the tools, then runs safe requests (files, code intelligence, terminal), including ones that must be refused.

Usage:
    uv run python scripts/test_tools.py
"""

import asyncio
import json
import sys

from app.config import get_settings
from app.container import build_tool_manager
from app.tools import ToolRequest

DEMO_REQUESTS = [
    ToolRequest(tool_name="list_files", arguments={"path": "."}),
    ToolRequest(tool_name="read_file", arguments={"path": "pyproject.toml"}),
    ToolRequest(tool_name="read_file", arguments={"path": ".env"}),  # secret: refused
    ToolRequest(tool_name="read_file", arguments={"path": "../../etc/passwd"}),  # outside: refused
    ToolRequest(tool_name="write_file", arguments={"path": ".git/HEAD", "content": "x"}),  # protected
    ToolRequest(tool_name="read_file", arguments={"path": "does/not/exist.py"}),
    ToolRequest(tool_name="analyze_project", arguments={}),
    ToolRequest(tool_name="find_class", arguments={"query": "ToolManager"}),
    ToolRequest(
        tool_name="find_definition", arguments={"name": "BaseTool", "path": "app/capabilities/base.py"}
    ),
    ToolRequest(tool_name="class_hierarchy", arguments={"name": "LLMProvider"}),
    ToolRequest(tool_name="module_dependencies", arguments={"path": "app/tools/manager.py"}),
    ToolRequest(tool_name="analyze_file", arguments={"path": "README.md"}),  # unsupported language
    ToolRequest(tool_name="execute_command", arguments={"command": "python3 --version"}),
    ToolRequest(tool_name="run_git_command", arguments={"args": ["log", "--oneline", "-3"]}),
    ToolRequest(tool_name="run_pytest", arguments={"args": ["-q", "tests/unit/test_settings.py"]}),
    ToolRequest(tool_name="execute_command", arguments={"command": "rm -rf app"}),  # blacklist: refused
    ToolRequest(tool_name="execute_command", arguments={"command": "cat .env"}),  # not whitelisted
    ToolRequest(tool_name="execute_command", arguments={"command": "ls ../.."}),  # outside: refused
    ToolRequest(tool_name="run_git_command", arguments={"args": ["push"]}),  # read-only git only
]


def summarize(output: object, limit: int = 160) -> str:
    text = json.dumps(output, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "…"


async def main() -> int:
    settings = get_settings()
    manager = await build_tool_manager(settings)

    print(f"Workspace: {settings.fs_workspace_root.resolve()}  (read-only: {settings.fs_read_only})")
    print("Registered tools:")
    for spec in manager.list_tools():
        print(f"  [{spec.source:5}] {spec.name:17} {spec.description}")

    print("\nResults:")
    for request, result in zip(DEMO_REQUESTS, await manager.execute_many(DEMO_REQUESTS), strict=True):
        arguments = ", ".join(f"{key}={value!r}" for key, value in request.arguments.items())
        status = f"ok    {summarize(result.output)}" if result.ok else f"ERROR {result.error}"
        print(f"  {request.tool_name}({arguments})\n      {status}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
