"""Dependency rules: only ``app/providers/llm/`` may import an LLM vendor SDK."""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
VENDOR_PACKAGES = (
    "langchain_ollama",
    "langchain_openai",
    "langchain_google_genai",
    "langchain_groq",
    "ollama",
    "openai",
    "groq",
    "google",
)
ALLOWED = APP / "providers" / "llm"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


SOURCES = sorted(p for p in APP.rglob("*.py") if ALLOWED not in p.parents)


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(APP)))
def test_no_vendor_sdk_outside_llm_providers(path: Path) -> None:
    vendors = {m for m in imported_modules(path) if m.split(".")[0] in VENDOR_PACKAGES}
    assert not vendors, f"{path.relative_to(APP)} imports {vendors}; go through app.providers.llm"
