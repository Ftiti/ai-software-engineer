"""Manual check of the tool pipeline: ToolRequest -> ToolManager -> registry -> adapter -> result.

Registers the demo ``echo`` tool plus the tools of every MCP server in MCP_CONFIG_PATH, lists
them, then runs a few requests (including failing ones) and prints the results.

Usage:
    uv run python scripts/test_tools.py
    uv run python scripts/test_tools.py "Bonjour"
"""

import argparse
import asyncio
import sys

from app.config import get_settings
from app.container import build_tool_manager
from app.tools import ToolRequest
from app.tools.local.echo import EchoTool


async def main(text: str) -> int:
    settings = get_settings()
    manager = await build_tool_manager(settings, local_tools=[EchoTool()])

    print(f"MCP config: {settings.mcp_config_path}")
    print("Registered tools:")
    for spec in manager.list_tools():
        print(f"  [{spec.source:5}] {spec.name:30} {spec.description}")

    requests = [
        ToolRequest(tool_name="echo", arguments={"text": text}, call_id="1"),
        ToolRequest(tool_name="echo", arguments={"wrong": text}, call_id="2"),
        ToolRequest(tool_name="does_not_exist", call_id="3"),
    ]
    print("\nResults:")
    for result in await manager.execute_many(requests):
        status = f"ok    -> {result.output!r}" if result.ok else f"error -> {result.error}"
        print(f"  #{result.call_id} {result.tool_name:16} {status}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("text", nargs="?", default="Hello")
    sys.exit(asyncio.run(main(parser.parse_args().text)))
