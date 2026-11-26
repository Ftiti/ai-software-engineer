"""Manual end-to-end check: send one message through the graph and stream the LLM reply.

Usage:
    uv run python scripts/test_agent.py
    uv run python scripts/test_agent.py "How would you structure a FastAPI project?"
"""

import argparse
import sys

from langchain_core.messages import AIMessageChunk, HumanMessage

from app.container import build_agent
from app.orchestration import build_graph
from app.orchestration.nodes import NodeName

DEFAULT_PROMPT = "Explain what you can do."


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT)
    args = parser.parse_args()

    agent = build_agent()
    info = agent.provider.model_info
    print(f"Provider: {info.provider} ({info.model}, temperature={info.temperature})")
    print(f"User:     {args.prompt}\n")

    graph = build_graph(agent)
    print("assistant: ", end="", flush=True)
    try:
        # stream_mode="messages" yields LLM tokens as they are generated, tagged with the node
        # that produced them.
        for chunk, metadata in graph.stream(
            {"messages": [HumanMessage(content=args.prompt)]}, stream_mode="messages"
        ):
            if isinstance(chunk, AIMessageChunk) and metadata.get("langgraph_node") == NodeName.AGENT:
                print(chunk.text, end="", flush=True)
    except Exception as exc:  # CLI boundary: report any provider failure without a traceback
        print(f"\nLLM call failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
