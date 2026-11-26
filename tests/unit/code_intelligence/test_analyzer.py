"""CodeAnalyzer: reading through the filesystem capability, project scan, failures, caching."""

from pathlib import Path

import pytest

from app.capabilities.code_intelligence import CodeAnalyzer, ParserRegistry, PythonParser
from app.capabilities.code_intelligence.exceptions import InvalidProject, UnsupportedLanguage
from app.capabilities.code_intelligence.schemas import FileAnalysis
from app.capabilities.filesystem.exceptions import AccessDenied, FileNotFound
from tests.unit.code_intelligence.conftest import MakeAnalyzer
from tests.unit.code_intelligence.test_parser import ToyParser


class CountingParser(PythonParser):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def parse(self, path: str, source: str) -> FileAnalysis:
        self.calls.append(path)
        return super().parse(path, source)


def test_analyze_file_returns_normalised_paths(analyzer: CodeAnalyzer) -> None:
    analysis = analyzer.analyze_file("./pkg/services/../models.py")
    assert (analysis.path, analysis.module, analysis.language) == ("pkg/models.py", "pkg.models", "python")
    assert "pkg.models.Dog" in {s.qualified_name for s in analysis.symbols}


def test_analyze_file_errors(analyzer: CodeAnalyzer) -> None:
    with pytest.raises(UnsupportedLanguage):
        analyzer.analyze_file("README.md")
    with pytest.raises(FileNotFound):
        analyzer.analyze_file("pkg/missing.py")
    with pytest.raises(AccessDenied):  # filesystem safety rules apply
        analyzer.analyze_file("secret_settings.py")
    with pytest.raises(AccessDenied, match="outside the workspace"):
        analyzer.analyze_file("../elsewhere.py")


def test_analyze_project_scans_supported_files_only(analyzer: CodeAnalyzer) -> None:
    project = analyzer.analyze_project()

    assert [f.path for f in project.files] == [
        "pkg/__init__.py",
        "pkg/models.py",
        "pkg/services/__init__.py",
        "pkg/services/zoo.py",
    ]  # no README, no denied secret_settings.py, nothing from the ignored .venv
    assert [(f.path, "Syntax error" in f.reason) for f in project.failures] == [("pkg/broken.py", True)]
    assert not project.truncated


def test_analyze_project_on_a_subdirectory(analyzer: CodeAnalyzer) -> None:
    project = analyzer.analyze_project("pkg/services")
    assert project.path == "pkg/services"
    assert [f.module for f in project.files] == ["pkg.services", "pkg.services.zoo"]


@pytest.mark.parametrize("path", ["pkg/models.py", "does-not-exist"])
def test_analyze_project_requires_a_directory(analyzer: CodeAnalyzer, path: str) -> None:
    with pytest.raises(InvalidProject, match="not a project directory"):
        analyzer.analyze_project(path)


def test_unchanged_files_are_not_parsed_again(make_analyzer: MakeAnalyzer, project: Path) -> None:
    parser = CountingParser()
    analyzer = make_analyzer(ParserRegistry([parser]))

    first = analyzer.analyze_file("pkg/models.py")
    assert analyzer.analyze_file("pkg/models.py") is first
    assert parser.calls == ["pkg/models.py"]

    (project / "pkg" / "models.py").write_text("class Cat: ...\n")
    changed = analyzer.analyze_file("pkg/models.py")
    assert parser.calls == ["pkg/models.py", "pkg/models.py"]
    assert "pkg.models.Cat" in {s.qualified_name for s in changed.symbols}


def test_deleted_files_disappear_from_the_next_scan(analyzer: CodeAnalyzer, project: Path) -> None:
    analyzer.analyze_project()
    (project / "pkg" / "services" / "zoo.py").unlink()
    assert "pkg/services/zoo.py" not in {f.path for f in analyzer.analyze_project().files}


def test_new_languages_are_analyzed_with_the_same_code(make_analyzer: MakeAnalyzer, project: Path) -> None:
    (project / "games").mkdir()
    (project / "games" / "snake.toy").write_text("anything")
    analyzer = make_analyzer(ParserRegistry([PythonParser(), ToyParser()]))

    languages = {f.path: f.language for f in analyzer.analyze_project().files}

    assert languages["games/snake.toy"] == "toy"
    assert languages["pkg/models.py"] == "python"
    assert analyzer.languages == ["python", "toy"]
