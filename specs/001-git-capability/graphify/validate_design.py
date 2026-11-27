"""Validate the Git capability design against the Graphify knowledge graph of the code base.

Graphify extracts every import, call and inheritance edge from the real source (AST). This script
reads ``graphify-out/graph.json`` and:

1. prints the module dependency diagram (Mermaid) of the components the design reuses, as they are
   today (``--as-is``);
2. checks the design's assumptions:
   - EXISTING: dependencies the design relies on must exist now;
   - FORBIDDEN: dependency paths that must never exist (layering, OS isolation);
   - PLANNED: dependencies the implementation must create (checked with ``--phase implemented``).

Usage (from the repository root, after ``graphify update .``):
    PY=$(cat graphify-out/.graphify_python); SCRIPT=specs/001-git-capability/graphify/validate_design.py
    $PY $SCRIPT                        # design phase
    $PY $SCRIPT --as-is                # current dependency diagram (Mermaid)
    $PY $SCRIPT --phase implemented    # after implementation
"""

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

GRAPH = Path("graphify-out/graph.json")
DEPENDENCY_RELATIONS = {"imports", "imports_from", "calls", "inherits", "uses", "references", "re_exports"}

# (from, to, why): "from" depends on "to" (file or package prefix).
EXISTING = [
    ("app/capabilities/terminal/capability.py", "app/providers/terminal", "process provider to reuse"),
    ("app/capabilities/terminal/validator.py", "app/capabilities/filesystem", "PathValidator to reuse"),
    ("app/capabilities/terminal/executor.py", "app/providers/terminal", "executor builds ProcessRequest"),
    ("app/capabilities/base.py", "app/tools", "AsyncCapabilityTool extends BaseTool"),
    ("app/capabilities/terminal/tool.py", "app/capabilities/base.py", "tools extend AsyncCapabilityTool"),
    ("app/container.py", "app/capabilities/terminal", "composition root registers capabilities"),
    ("app/container.py", "app/capabilities/filesystem", "filesystem service shared by capabilities"),
    ("app/tools/manager.py", "app/tools/registry.py", "ToolManager looks tools up in the registry"),
    ("app/tools/adapters/local.py", "app/tools/base.py", "LocalToolAdapter wraps BaseTool"),
    ("app/orchestration", "app/agents", "graph nodes call the agent"),
]
PLANNED = [
    ("app/capabilities/git/capability.py", "app/providers/git", "assembly creates LocalGitProvider"),
    ("app/providers/git/local.py", "app/providers/terminal", "git runs through TerminalProvider"),
    ("app/capabilities/git/validator.py", "app/capabilities/filesystem", "workspace rules reused"),
    ("app/capabilities/git/capability.py", "app/providers/terminal", "assembly injects TerminalProvider"),
    ("app/capabilities/git/tool.py", "app/capabilities/base.py", "tools extend AsyncCapabilityTool"),
    ("app/capabilities/git/tool.py", "app/capabilities/git/service.py", "tools call the service"),
    ("app/capabilities/git/service.py", "app/capabilities/git/validator.py", "service validates first"),
    (
        "app/capabilities/git/service.py",
        "app/capabilities/git/repository.py",
        "service parses via repository",
    ),
    ("app/capabilities/git/service.py", "app/providers/git", "service runs git via GitProvider"),
    ("app/container.py", "app/capabilities/git", "composition root registers the git capability"),
]
# (from, to, why): no dependency path (direct or transitive) may exist.
FORBIDDEN = [
    ("app/agents", "app/capabilities", "agents act only through the Tool Manager"),
    ("app/agents", "app/providers/terminal", "agents never start processes"),
    ("app/agents", "app/providers/git", "agents never run git"),
    ("app/orchestration", "app/providers/terminal", "graph never starts processes"),
    ("app/orchestration", "app/providers/git", "graph never runs git"),
    ("app/tools", "app/capabilities", "tool system does not know capabilities"),
    ("app/providers", "app/capabilities", "providers depend on nothing above them"),
    ("app/capabilities/terminal", "app/capabilities/git", "capabilities stay independent"),
    (
        "app/capabilities/git",
        "app/capabilities/terminal",
        "git reuses the provider, not the terminal capability",
    ),
]
# Direct-only rule: inside the git capability only the assembly may know the terminal provider.
FORBIDDEN_DIRECT = [
    ("app/capabilities/git/service.py", "app/providers/terminal", "service talks to GitProvider only"),
    ("app/capabilities/git/tool.py", "app/providers", "tools talk to the service only"),
]
AS_IS_PACKAGES = [
    "app/agents",
    "app/orchestration",
    "app/tools",
    "app/capabilities/base.py",
    "app/capabilities/filesystem",
    "app/capabilities/terminal",
    "app/capabilities/git",
    "app/providers/filesystem",
    "app/providers/terminal",
    "app/providers/git",
    "app/config",
    "app/container.py",
]


def load_module_graph() -> dict[str, set[str]]:
    """file -> files it depends on (app/ only, self-loops removed)."""
    data = json.loads(GRAPH.read_text(encoding="utf-8"))
    file_of = {n["id"]: n.get("source_file") for n in data["nodes"]}
    graph: dict[str, set[str]] = defaultdict(set)
    for edge in data["links"]:
        if edge.get("relation") not in DEPENDENCY_RELATIONS:
            continue
        source = edge.get("source_file") or file_of.get(edge["source"])
        target = file_of.get(edge["target"])
        if source and target and source != target and source.startswith("app/") and target.startswith("app/"):
            graph[source].add(target)
    return graph


def under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def direct(graph: dict[str, set[str]], src: str, dst: str) -> list[tuple[str, str]]:
    return [(a, b) for a, targets in graph.items() if under(a, src) for b in targets if under(b, dst)]


def path_between(graph: dict[str, set[str]], src: str, dst: str) -> list[str] | None:
    starts = [f for f in graph if under(f, src)]
    parent: dict[str, str | None] = dict.fromkeys(starts)
    queue = deque(starts)
    while queue:
        current = queue.popleft()
        if under(current, dst) and not under(current, src):
            chain = [current]
            while (previous := parent[chain[-1]]) is not None:
                chain.append(previous)
            return chain[::-1]
        for nxt in graph.get(current, ()):
            if nxt not in parent:
                parent[nxt] = current
                queue.append(nxt)
    return None


def as_is(graph: dict[str, set[str]]) -> str:
    def group(path: str) -> str | None:
        return next((p for p in AS_IS_PACKAGES if under(path, p)), None)

    edges = sorted(
        {
            (g1, g2)
            for a, ts in graph.items()
            for b in ts
            if (g1 := group(a)) and (g2 := group(b)) and g1 != g2
        }
    )
    ids = {p: p.removeprefix("app/").replace("/", "_").replace(".", "_") for p in AS_IS_PACKAGES}
    lines = ["flowchart TD"] + [f'    {ids[p]}["{p}"]' for p in AS_IS_PACKAGES]
    lines += [f"    {ids[a]} --> {ids[b]}" for a, b in edges]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["design", "implemented"], default="design")
    parser.add_argument("--as-is", action="store_true", help="print the current dependency diagram")
    args = parser.parse_args()
    graph = load_module_graph()
    if args.as_is:
        print(as_is(graph))
        return 0

    failures = 0
    checks = [("EXISTING", EXISTING)] + ([("PLANNED", PLANNED)] if args.phase == "implemented" else [])
    for title, rules in checks:
        print(f"## {title}: dependency must exist")
        for src, dst, why in rules:
            found = direct(graph, src, dst)
            failures += not found
            print(
                f"- [{'x' if found else ' '}] {src} -> {dst} ({why})"
                + (f": {found[0][0]} -> {found[0][1]}" if found else ": MISSING")
            )
    print("## FORBIDDEN: no dependency path may exist")
    for src, dst, why in FORBIDDEN:
        chain = path_between(graph, src, dst)
        failures += chain is not None
        print(
            f"- [{' ' if chain else 'x'}] {src} -/-> {dst} ({why})"
            + (f": VIOLATION {' -> '.join(chain)}" if chain else "")
        )
    if args.phase == "implemented":
        print("## FORBIDDEN (direct)")
        for src, dst, why in FORBIDDEN_DIRECT:
            found = direct(graph, src, dst)
            failures += bool(found)
            print(
                f"- [{' ' if found else 'x'}] {src} -/-> {dst} ({why})"
                + (f": VIOLATION {found[0]}" if found else "")
            )
    verdict = "OK" if not failures else f"{failures} FAILED"
    edges = sum(len(targets) for targets in graph.values())
    print(f"\n{verdict} ({edges} module edges, {len(graph)} modules)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
