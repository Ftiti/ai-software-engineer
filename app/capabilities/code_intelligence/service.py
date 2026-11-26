"""Business API of the code intelligence capability.

Every query works on a fresh :class:`SymbolIndex` of the whole workspace, so results always
reflect the files as they are now (unchanged files are not re-parsed, see the analyzer).
Search and navigation are delegated to :class:`SymbolSearch` and :class:`CodeNavigator`;
the service only chooses what to run and applies result limits.
"""

from collections import Counter

from app.capabilities.code_intelligence.analyzer import CodeAnalyzer
from app.capabilities.code_intelligence.indexer import SymbolIndex, SymbolIndexer
from app.capabilities.code_intelligence.navigator import CodeNavigator
from app.capabilities.code_intelligence.schemas import (
    ClassHierarchies,
    Definitions,
    FileAnalysis,
    FileSummary,
    ImportMatches,
    ModuleDependencies,
    ProjectSummary,
    References,
    Symbol,
    SymbolKind,
    SymbolMatches,
)
from app.capabilities.code_intelligence.search import CLASS_KINDS, FUNCTION_KINDS, SymbolSearch


class CodeIntelligenceService:
    def __init__(self, analyzer: CodeAnalyzer, indexer: SymbolIndexer, *, max_results: int = 50) -> None:
        self._analyzer = analyzer
        self._indexer = indexer
        self._max_results = max_results

    # -- Analysis --------------------------------------------------------------------------------

    def analyze_project(self, path: str = ".") -> ProjectSummary:
        index = self._indexer.build(path)
        project = index.project
        return ProjectSummary(
            path=project.path,
            files=len(project.files),
            languages=dict(Counter(f.language for f in project.files)),
            symbols={kind: index.count(kind) for kind in SymbolKind},
            modules=[_summarize(f) for f in project.files],
            failures=project.failures,
            truncated=project.truncated,
        )

    def analyze_file(self, path: str) -> FileAnalysis:
        return self._analyzer.analyze_file(path)

    # -- Search ----------------------------------------------------------------------------------

    def find_symbol(
        self, query: str, kind: SymbolKind | None = None, limit: int | None = None
    ) -> SymbolMatches:
        kinds = frozenset({kind}) if kind is not None else None
        return self._symbol_matches(query, SymbolSearch(self._index()).symbols(query, kinds), limit)

    def find_class(self, query: str, limit: int | None = None) -> SymbolMatches:
        return self._symbol_matches(query, SymbolSearch(self._index()).symbols(query, CLASS_KINDS), limit)

    def find_function(self, query: str, limit: int | None = None) -> SymbolMatches:
        return self._symbol_matches(query, SymbolSearch(self._index()).symbols(query, FUNCTION_KINDS), limit)

    def search_import(self, module: str, limit: int | None = None) -> ImportMatches:
        matches = SymbolSearch(self._index()).imports(module)
        return ImportMatches(module=module, matches=matches[: self._limit(limit)], total=len(matches))

    # -- Navigation ------------------------------------------------------------------------------

    def find_definition(self, name: str, path: str | None = None) -> Definitions:
        return Definitions(name=name, definitions=self._navigator().definitions(name, self._normalise(path)))

    def find_references(self, name: str, path: str | None = None, limit: int | None = None) -> References:
        navigator = self._navigator()
        symbol = navigator.definition(name, self._normalise(path))
        matches = navigator.references(symbol)
        return References(symbol=symbol, references=matches[: self._limit(limit)], total=len(matches))

    def class_hierarchy(self, name: str, path: str | None = None) -> ClassHierarchies:
        return ClassHierarchies(
            name=name, hierarchies=self._navigator().hierarchy(name, self._normalise(path))
        )

    def module_dependencies(self, path: str) -> ModuleDependencies:
        return self._navigator().module_dependencies(self._analyzer.analyze_file(path).path)

    # -- Internals -------------------------------------------------------------------------------

    def _index(self) -> SymbolIndex:
        return self._indexer.build()

    def _navigator(self) -> CodeNavigator:
        return CodeNavigator(self._index())

    def _normalise(self, path: str | None) -> str | None:
        """Validated, workspace-relative form of a file path given by the caller."""
        return None if path is None else self._analyzer.analyze_file(path).path

    def _limit(self, requested: int | None) -> int:
        return min(requested or self._max_results, self._max_results)

    def _symbol_matches(self, query: str, matches: list[Symbol], limit: int | None) -> SymbolMatches:
        return SymbolMatches(query=query, matches=matches[: self._limit(limit)], total=len(matches))


def _summarize(file: FileAnalysis) -> FileSummary:
    kinds = Counter(symbol.kind for symbol in file.symbols)
    return FileSummary(
        path=file.path,
        module=file.module,
        language=file.language,
        classes=kinds[SymbolKind.CLASS],
        functions=kinds[SymbolKind.FUNCTION] + kinds[SymbolKind.METHOD],
        imports=len(file.imports),
    )
