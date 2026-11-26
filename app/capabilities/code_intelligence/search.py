"""Search over parsed information (the index), never over raw file text.

Symbols are ranked: exact name, case-insensitive name, prefix, then substring. A query
containing a dot matches qualified names instead (``ToolManager.execute``,
``app.tools.manager``).
"""

from app.capabilities.code_intelligence.indexer import SymbolIndex
from app.capabilities.code_intelligence.schemas import ImportInfo, Symbol, SymbolKind

CLASS_KINDS = frozenset({SymbolKind.CLASS})
FUNCTION_KINDS = frozenset({SymbolKind.FUNCTION, SymbolKind.METHOD})


class SymbolSearch:
    def __init__(self, index: SymbolIndex) -> None:
        self._index = index

    def symbols(self, query: str, kinds: frozenset[SymbolKind] | None = None) -> list[Symbol]:
        query = query.strip()
        scored = [
            (score, symbol.qualified_name, symbol)
            for symbol in self._index.symbols(kinds)
            if (score := _score(symbol, query)) is not None
        ]
        return [symbol for *_, symbol in sorted(scored, key=lambda item: (item[0], item[1]))]

    def classes(self, query: str) -> list[Symbol]:
        return self.symbols(query, CLASS_KINDS)

    def functions(self, query: str) -> list[Symbol]:
        """Functions and methods."""
        return self.symbols(query, FUNCTION_KINDS)

    def imports(self, module: str) -> list[ImportInfo]:
        """Imports of ``module`` (or of its submodules), or of a member named ``module``."""
        module = module.strip()
        prefix = f"{module}."
        return sorted(
            (
                imported
                for imported in self._index.imports()
                if imported.module == module
                or imported.module.startswith(prefix)
                or imported.target == module
                or module in (imported.name, imported.local_name)
            ),
            key=lambda imported: (imported.path, imported.line),
        )


def _score(symbol: Symbol, query: str) -> int | None:
    """Lower is better; None means no match."""
    lowered = query.lower()
    if "." in query:
        qualified = symbol.qualified_name
        if qualified == query:
            return 0
        if qualified.endswith(f".{query}"):
            return 1
        return 4 if lowered in qualified.lower() else None

    name = symbol.name
    if name == query:
        return 0
    if name.lower() == lowered:
        return 1
    if name.lower().startswith(lowered):
        return 2
    return 3 if lowered in name.lower() else None
