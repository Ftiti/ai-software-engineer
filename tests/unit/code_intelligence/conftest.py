"""A small Python project in a temporary workspace, and the code intelligence objects around it."""

from collections.abc import Callable
from pathlib import Path

import pytest

from app.capabilities.code_intelligence import (
    CodeAnalyzer,
    CodeIntelligenceService,
    CodeNavigator,
    ParserRegistry,
    SymbolIndex,
    SymbolIndexer,
    default_parsers,
)
from app.capabilities.filesystem import FilesystemPolicy, FilesystemService, PathValidator
from app.providers.filesystem import LocalFilesystemProvider

PROJECT = {
    "pkg/__init__.py": '''\
"""Demo package."""
from pkg.models import Animal
''',
    "pkg/models.py": '''\
"""Domain models."""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")
MAX_LEGS: int = 4


class Animal(ABC):
    """Base of every animal.

    Longer description.
    """

    sound = "..."

    @abstractmethod
    def speak(self) -> str: ...


class Dog(Animal):
    def speak(self) -> str:
        local_variable = "woof"
        return local_variable

    async def fetch(self, item: str = "ball") -> str:
        return item


class Box(Generic[T]):
    pass
''',
    "pkg/services/__init__.py": "",
    "pkg/services/zoo.py": """\
from .. import models
from ..models import Dog as Hound
import pkg
import json


class Puppy(Hound):
    def speak(self) -> str:
        return "yip"


def chorus(animals: list[models.Animal]) -> list[str]:
    def shout(animal):
        return animal.speak().upper()

    return [shout(a) for a in animals]


def adopt() -> pkg.Animal:
    dog = Hound()
    json.dumps({})
    return dog
""",
    "pkg/broken.py": "def oops(:\n",
    "secret_settings.py": "class Leaked: ...\n",  # denied by the policy below
    ".venv/lib/site.py": "class Vendored: ...\n",  # ignored folder
    "README.md": "# Demo\n",
}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    for relative, content in PROJECT.items():
        file = root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)
    return root


@pytest.fixture
def files(project: Path) -> FilesystemService:
    provider = LocalFilesystemProvider()
    policy = FilesystemPolicy(
        workspace_root=project, denied_patterns=("secret_*",), ignored_patterns=(".venv",)
    )
    return FilesystemService(provider, PathValidator(provider, policy))


MakeAnalyzer = Callable[..., CodeAnalyzer]


@pytest.fixture
def make_analyzer(files: FilesystemService) -> MakeAnalyzer:
    def make(parsers: ParserRegistry | None = None) -> CodeAnalyzer:
        return CodeAnalyzer(files, parsers or default_parsers())

    return make


@pytest.fixture
def analyzer(make_analyzer: MakeAnalyzer) -> CodeAnalyzer:
    return make_analyzer()


@pytest.fixture
def index(analyzer: CodeAnalyzer) -> SymbolIndex:
    return SymbolIndexer(analyzer).build()


@pytest.fixture
def navigator(index: SymbolIndex) -> CodeNavigator:
    return CodeNavigator(index)


@pytest.fixture
def service(analyzer: CodeAnalyzer) -> CodeIntelligenceService:
    return CodeIntelligenceService(analyzer, SymbolIndexer(analyzer), max_results=5)
