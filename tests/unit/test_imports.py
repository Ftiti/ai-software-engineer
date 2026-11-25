"""Every module under ``app`` must import cleanly."""

import importlib
import pkgutil

import pytest

import app

# Optional-provider modules import their vendor package lazily, so they are safe to include.
MODULES = sorted(m.name for m in pkgutil.walk_packages(app.__path__, prefix="app."))


def test_modules_discovered() -> None:
    assert "app.config.settings" in MODULES
    assert "app.providers.llm.base" in MODULES


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module: str) -> None:
    importlib.import_module(module)
