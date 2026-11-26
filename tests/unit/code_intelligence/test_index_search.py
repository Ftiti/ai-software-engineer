"""SymbolIndex lookups and the SymbolSearch engine."""

from app.capabilities.code_intelligence import SymbolIndex, SymbolSearch
from app.capabilities.code_intelligence.schemas import FileAnalysis, ProjectAnalysis, Symbol, SymbolKind


def qualified(symbols: list[Symbol]) -> list[str]:
    return [s.qualified_name for s in symbols]


# -- Index --------------------------------------------------------------------------------------


def test_index_lookups(index: SymbolIndex) -> None:
    assert qualified(index.lookup("pkg.models.Dog")) == ["pkg.models.Dog"]
    assert index.lookup("pkg.models.Cat") == []
    assert sorted(qualified(index.named("speak"))) == [
        "pkg.models.Animal.speak",
        "pkg.models.Dog.speak",
        "pkg.services.zoo.Puppy.speak",
    ]
    assert index.module("pkg.services.zoo") is index.file("pkg/services/zoo.py")
    assert index.module("pkg.broken") is None  # failed to parse


def test_index_by_kind(index: SymbolIndex) -> None:
    assert sorted(qualified(index.symbols(frozenset({SymbolKind.CLASS})))) == [
        "pkg.models.Animal",
        "pkg.models.Box",
        "pkg.models.Dog",
        "pkg.services.zoo.Puppy",
    ]
    assert index.count(SymbolKind.MODULE) == 4
    assert index.count(SymbolKind.FUNCTION) == 3  # chorus, shout, adopt


def test_index_bindings_and_references(index: SymbolIndex) -> None:
    assert index.binding("pkg/services/zoo.py", "Hound") == "pkg.models.Dog"
    assert index.binding("pkg/services/zoo.py", "Dog") is None
    assert {r.path for r in index.references("Hound")} == {"pkg/services/zoo.py"}


# -- Search -------------------------------------------------------------------------------------


def test_results_are_ranked_exact_then_prefix_then_substring(index: SymbolIndex) -> None:
    search = SymbolSearch(index)
    assert qualified(search.symbols("dog"))[:1] == ["pkg.models.Dog"]  # case-insensitive exact
    assert qualified(search.symbols("Animal")) == ["pkg.models.Animal"]
    assert qualified(search.symbols("MAX")) == ["pkg.models.MAX_LEGS"]  # prefix
    assert qualified(search.symbols("upp")) == ["pkg.services.zoo.Puppy"]  # substring


def test_exact_matches_come_first() -> None:
    def sym(name: str) -> Symbol:
        return Symbol(
            name=name, qualified_name=f"m.{name}", kind=SymbolKind.CLASS, path="m.py", line=1, end_line=1
        )

    names = ["RunnerTool", "Tool", "ToolBox", "tool"]
    file = FileAnalysis(path="m.py", language="python", module="m", symbols=[sym(n) for n in names])
    search = SymbolSearch(SymbolIndex(ProjectAnalysis(path=".", files=[file])))

    assert [s.name for s in search.symbols("Tool")] == ["Tool", "tool", "ToolBox", "RunnerTool"]


def test_kind_filters(index: SymbolIndex) -> None:
    search = SymbolSearch(index)
    assert qualified(search.classes("speak")) == []
    assert len(search.functions("speak")) == 3
    assert qualified(search.functions("adopt")) == ["pkg.services.zoo.adopt"]
    assert qualified(search.symbols("models", frozenset({SymbolKind.MODULE}))) == ["pkg.models"]


def test_dotted_queries_match_qualified_names(index: SymbolIndex) -> None:
    search = SymbolSearch(index)
    assert qualified(search.symbols("Dog.speak")) == ["pkg.models.Dog.speak"]
    assert qualified(search.symbols("pkg.models.Dog")) == [
        "pkg.models.Dog",
        "pkg.models.Dog.fetch",
        "pkg.models.Dog.speak",
    ]


def test_search_imports(index: SymbolIndex) -> None:
    search = SymbolSearch(index)
    assert [(i.path, i.name) for i in search.imports("abc")] == [
        ("pkg/models.py", "ABC"),
        ("pkg/models.py", "abstractmethod"),
    ]
    assert {i.path for i in search.imports("pkg")} == {"pkg/__init__.py", "pkg/services/zoo.py"}
    assert [i.local_name for i in search.imports("pkg.models.Dog")] == ["Hound"]
    assert [i.local_name for i in search.imports("Dog")] == ["Hound"]  # by imported name
    assert search.imports("requests") == []
