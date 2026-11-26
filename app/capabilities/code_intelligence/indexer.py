"""Symbol index: the analyses of a project reorganised for fast lookups.

Every lookup (by qualified name, by name, by kind, by imported module, by referenced name, by
file binding) is a dictionary access built once per index. The index is language-neutral: it
only knows the models of :mod:`schemas`.
"""

from collections import defaultdict

from app.capabilities.code_intelligence.analyzer import CodeAnalyzer
from app.capabilities.code_intelligence.schemas import (
    FileAnalysis,
    ImportInfo,
    ProjectAnalysis,
    Reference,
    Symbol,
    SymbolKind,
)


class SymbolIndex:
    def __init__(self, project: ProjectAnalysis) -> None:
        self.project = project
        self._files = {f.path: f for f in project.files}
        self._modules = {f.module: f for f in project.files}
        self._by_qualified: dict[str, list[Symbol]] = defaultdict(list)
        self._by_name: dict[str, list[Symbol]] = defaultdict(list)
        self._by_kind: dict[SymbolKind, list[Symbol]] = defaultdict(list)
        self._references: dict[str, list[Reference]] = defaultdict(list)
        self._bindings: dict[str, dict[str, str]] = defaultdict(dict)  # path -> local name -> target
        self._star_imports: dict[str, list[str]] = defaultdict(list)  # path -> modules

        for file in project.files:
            for symbol in file.symbols:
                self._by_qualified[symbol.qualified_name].append(symbol)
                self._by_name[symbol.name].append(symbol)
                self._by_kind[symbol.kind].append(symbol)
            for reference in file.references:
                self._references[reference.name].append(reference)
            for imported in file.imports:
                if imported.name == "*":
                    self._star_imports[file.path].append(imported.module)
                else:
                    self._bindings[file.path].setdefault(imported.local_name, imported.target)

    # -- Files and modules -----------------------------------------------------------------------

    @property
    def files(self) -> list[FileAnalysis]:
        return self.project.files

    def file(self, path: str) -> FileAnalysis | None:
        return self._files.get(path)

    def module(self, name: str) -> FileAnalysis | None:
        return self._modules.get(name)

    # -- Symbols ---------------------------------------------------------------------------------

    def lookup(self, qualified_name: str) -> list[Symbol]:
        """Definitions with exactly this qualified name (usually one)."""
        return list(self._by_qualified.get(qualified_name, ()))

    def named(self, name: str) -> list[Symbol]:
        return list(self._by_name.get(name, ()))

    def symbols(self, kinds: frozenset[SymbolKind] | None = None) -> list[Symbol]:
        selected = kinds if kinds is not None else frozenset(SymbolKind)
        return [s for kind in SymbolKind if kind in selected for s in self._by_kind.get(kind, ())]

    def count(self, kind: SymbolKind) -> int:
        return len(self._by_kind.get(kind, ()))

    # -- Imports and references ------------------------------------------------------------------

    def imports(self) -> list[ImportInfo]:
        return [imported for file in self.project.files for imported in file.imports]

    def binding(self, path: str, local_name: str) -> str | None:
        """What ``local_name`` refers to in ``path`` through an import, if anything."""
        return self._bindings.get(path, {}).get(local_name)

    def star_imports(self, path: str) -> list[str]:
        return list(self._star_imports.get(path, ()))

    def references(self, name: str) -> list[Reference]:
        return list(self._references.get(name, ()))


class SymbolIndexer:
    """Builds an up-to-date :class:`SymbolIndex` of the project on demand."""

    def __init__(self, analyzer: CodeAnalyzer) -> None:
        self._analyzer = analyzer

    def build(self, path: str = ".") -> SymbolIndex:
        return SymbolIndex(self._analyzer.analyze_project(path))
