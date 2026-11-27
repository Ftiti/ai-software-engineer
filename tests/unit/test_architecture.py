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


OS_MODULES = ("os", "shutil", "tempfile", "io", "glob")
FILESYSTEM_PROVIDERS = APP / "providers" / "filesystem"
TERMINAL_PROVIDERS = APP / "providers" / "terminal"
OS_PROVIDERS = (FILESYSTEM_PROVIDERS, TERMINAL_PROVIDERS)
NON_PROVIDER_SOURCES = sorted(
    p for p in APP.rglob("*.py") if not any(provider in p.parents for provider in OS_PROVIDERS)
)


@pytest.mark.parametrize("path", NON_PROVIDER_SOURCES, ids=lambda p: str(p.relative_to(APP)))
def test_no_os_access_outside_os_providers(path: Path) -> None:
    used = {m for m in imported_modules(path) if m.split(".")[0] in OS_MODULES}
    assert not used, f"{path.relative_to(APP)} imports {used}; go through app.providers"


PROCESS_SOURCES = sorted(p for p in APP.rglob("*.py") if TERMINAL_PROVIDERS not in p.parents)


@pytest.mark.parametrize("path", PROCESS_SOURCES, ids=lambda p: str(p.relative_to(APP)))
def test_processes_are_started_only_by_the_terminal_provider(path: Path) -> None:
    """The agent and the services never reach subprocess: only app.providers.terminal does."""
    used = {m for m in imported_modules(path) if "subprocess" in m.split(".")}
    assert not used, f"{path.relative_to(APP)} imports {used}"
    assert "create_subprocess" not in path.read_text(), f"{path.relative_to(APP)} starts a process"


def test_filesystem_service_does_not_manipulate_paths() -> None:
    service = APP / "capabilities" / "filesystem" / "service.py"
    assert "pathlib" not in imported_modules(service)


CODE_INTELLIGENCE = APP / "capabilities" / "code_intelligence"
LANGUAGE_PARSERS = CODE_INTELLIGENCE / "parsers"


@pytest.mark.parametrize(
    "path", sorted(CODE_INTELLIGENCE.rglob("*.py")), ids=lambda p: str(p.relative_to(CODE_INTELLIGENCE))
)
def test_code_intelligence_is_language_independent_outside_parsers(path: Path) -> None:
    """Language-specific libraries (``ast`` for Python...) stay inside their parser module."""
    if LANGUAGE_PARSERS in path.parents:
        return
    assert "ast" not in imported_modules(path), f"{path.relative_to(APP)} parses code; move it to a parser"


@pytest.mark.parametrize(
    "path", sorted(CODE_INTELLIGENCE.rglob("*.py")), ids=lambda p: str(p.relative_to(CODE_INTELLIGENCE))
)
def test_code_intelligence_reads_files_through_the_filesystem_capability(path: Path) -> None:
    """Never the provider directly: the filesystem safety rules must apply to code analysis too."""
    used = {m for m in imported_modules(path) if m.startswith("app.providers.filesystem") or m == "pathlib"}
    assert not used, f"{path.relative_to(APP)} imports {used}; use FilesystemService"


GIT_CAPABILITY = APP / "capabilities" / "git"
GIT_PROVIDERS = APP / "providers" / "git"


@pytest.mark.parametrize("name", ["service.py", "tool.py", "validator.py", "repository.py", "schemas.py"])
def test_git_capability_reaches_processes_only_through_the_git_provider(name: str) -> None:
    """Only the assembly (capability.py) knows the terminal provider; the rest talks to GitProvider."""
    used = {m for m in imported_modules(GIT_CAPABILITY / name) if m.startswith("app.providers.terminal")}
    assert not used, f"capabilities/git/{name} imports {used}"


@pytest.mark.parametrize("path", sorted(APP.rglob("*.py")), ids=lambda p: str(p.relative_to(APP)))
def test_only_the_git_capability_uses_the_git_provider(path: Path) -> None:
    allowed = (GIT_CAPABILITY, GIT_PROVIDERS)
    if any(folder in path.parents for folder in allowed):
        return
    used = {m for m in imported_modules(path) if m.startswith("app.providers.git")}
    assert not used, f"{path.relative_to(APP)} imports {used}; go through the Git capability"


def test_git_provider_does_not_start_processes_itself() -> None:
    for path in GIT_PROVIDERS.rglob("*.py"):
        modules = imported_modules(path)
        assert not {m for m in modules if m.split(".")[0] in ("os", "subprocess", "asyncio")}, path.name
