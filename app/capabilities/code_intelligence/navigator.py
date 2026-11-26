"""Code navigation over the index: definitions, references, class hierarchy, dependencies.

The core is **name resolution**, the basis of "Go To Definition": a name used in a file is
resolved through that file's imports (``from app.tools import BaseTool`` binds ``BaseTool`` to
``app.tools.BaseTool``), its own top-level definitions and its star imports. The resulting
qualified name is then looked up, following re-exports (``app.tools`` re-exporting
``app.tools.base.BaseTool``). Everything is computed from parsed data; nothing is guessed from
text.

Resolution is static: an expression whose target is only known at run time (``self.x``,
``obj.method()``) cannot be resolved. References keep such uses with ``confirmed=False``
instead of silently dropping or wrongly confirming them.
"""

from app.capabilities.code_intelligence.exceptions import AmbiguousSymbol, SymbolNotFound
from app.capabilities.code_intelligence.indexer import SymbolIndex
from app.capabilities.code_intelligence.schemas import (
    BaseClass,
    ClassHierarchy,
    ImportInfo,
    ModuleDependencies,
    ModuleImport,
    Reference,
    ReferenceMatch,
    Symbol,
    SymbolKind,
)

_MAX_REEXPORT_HOPS = 8


class CodeNavigator:
    def __init__(self, index: SymbolIndex) -> None:
        self._index = index

    # -- Name resolution -------------------------------------------------------------------------

    def resolve(self, expression: str, path: str) -> str | None:
        """Qualified name that ``expression`` (e.g. ``"BaseTool"``, ``"fs.Service.run"``) denotes in
        ``path``; None when it is not statically known (builtins, ``self``, locals...)."""
        file = self._index.file(path)
        if file is None:
            return None
        head, _, rest = expression.partition(".")
        target = self._index.binding(path, head)
        if target is None and self._index.lookup(f"{file.module}.{head}"):
            target = f"{file.module}.{head}"
        if target is None:
            target = next(
                (f"{m}.{head}" for m in self._index.star_imports(path) if self.follow(f"{m}.{head}")),
                None,
            )
        if target is None:
            return None
        return f"{target}.{rest}" if rest else target

    def follow(self, qualified_name: str) -> list[Symbol]:
        """Definitions of ``qualified_name``, following re-exports through package imports."""
        for _ in range(_MAX_REEXPORT_HOPS):
            found = self._index.lookup(qualified_name)
            if found:
                return found
            redirected = self._reexport(qualified_name)
            if redirected is None or redirected == qualified_name:
                return []
            qualified_name = redirected
        return []

    # -- Definitions -----------------------------------------------------------------------------

    def definitions(self, name: str, path: str | None = None) -> list[Symbol]:
        """Go To Definition. With ``path``, ``name`` is resolved as it is used in that file;
        otherwise it is a qualified name, a dotted suffix (``ToolManager.execute``) or a name."""
        if path is not None:
            resolved = self.resolve(name, path)
            found = self.follow(resolved) if resolved else []
            if found:
                return found
        found = self.follow(name)
        if not found:
            if "." in name:
                found = [s for s in self._index.symbols() if s.qualified_name.endswith(f".{name}")]
            else:
                found = self._index.named(name)
        if not found:
            raise SymbolNotFound(
                f"No definition of {name!r} in the project. Use find_symbol to search for it."
            )
        return found

    def definition(self, name: str, path: str | None = None) -> Symbol:
        """Exactly one definition; raises ``AmbiguousSymbol`` when several match."""
        found = self.definitions(name, path)
        if len(found) > 1:
            candidates = ", ".join(sorted({s.qualified_name for s in found}))
            raise AmbiguousSymbol(
                f"{name!r} matches several definitions: {candidates}. Use a qualified name."
            )
        return found[0]

    # -- References ------------------------------------------------------------------------------

    def references(self, symbol: Symbol) -> list[ReferenceMatch]:
        """Uses of ``symbol``: confirmed ones first, then same-name uses that cannot be resolved."""
        matches: list[ReferenceMatch] = []
        for reference in self._candidate_references(symbol):
            resolved = self.resolve(reference.expression, reference.path) if reference.expression else None
            if resolved is None:
                confirmed = False
            elif any(s.qualified_name == symbol.qualified_name for s in self.follow(resolved)):
                confirmed = True
            elif self.follow(resolved) or not self._may_be_in_project(resolved):
                continue  # resolved to something else, e.g. another class's method or a library
            else:
                confirmed = False  # e.g. attribute of a project variable whose type is unknown
            matches.append(ReferenceMatch(reference=reference, confirmed=confirmed))
        return sorted(
            matches, key=lambda m: (not m.confirmed, m.reference.path, m.reference.line, m.reference.column)
        )

    # -- Class hierarchy -------------------------------------------------------------------------

    def parent_classes(self, cls: Symbol) -> list[BaseClass]:
        parents = []
        for base in cls.bases:
            resolved = self.resolve(base, cls.path)
            classes = [s for s in self.follow(resolved) if s.kind is SymbolKind.CLASS] if resolved else []
            parents.append(BaseClass(expression=base, resolved=classes[0] if classes else None))
        return parents

    def child_classes(self, cls: Symbol) -> list[Symbol]:
        """Classes of the project that directly inherit from ``cls``."""
        return [
            candidate
            for candidate in self._index.symbols(frozenset({SymbolKind.CLASS}))
            if any(
                parent.resolved is not None and parent.resolved.qualified_name == cls.qualified_name
                for parent in self.parent_classes(candidate)
            )
        ]

    def hierarchy(self, name: str, path: str | None = None) -> list[ClassHierarchy]:
        classes = [s for s in self.definitions(name, path) if s.kind is SymbolKind.CLASS]
        if not classes:
            raise SymbolNotFound(f"{name!r} is not a class of the project")
        return [
            ClassHierarchy(symbol=c, parents=self.parent_classes(c), children=self.child_classes(c))
            for c in classes
        ]

    # -- Module dependencies ---------------------------------------------------------------------

    def module_dependencies(self, path: str) -> ModuleDependencies:
        file = self._index.file(path)
        if file is None:
            raise SymbolNotFound(f"{path!r} is not an analyzed source file of the project")
        imports = [self._module_import(imported) for imported in file.imports]
        return ModuleDependencies(
            path=file.path,
            module=file.module,
            imports=imports,
            imported_by=self._importers(file.path, file.module),
        )

    # -- Internals -------------------------------------------------------------------------------

    def _reexport(self, qualified_name: str) -> str | None:
        """``pkg.Name.rest`` where module ``pkg`` imports ``Name`` -> what ``Name`` is bound to."""
        parts = qualified_name.split(".")
        for split in range(len(parts) - 1, 0, -1):  # longest module prefix first
            module = self._index.module(".".join(parts[:split]))
            if module is None:
                continue
            target = self._index.binding(module.path, parts[split])
            return ".".join([target, *parts[split + 1 :]]) if target else None
        return None

    def _candidate_references(self, symbol: Symbol) -> list[Reference]:
        """Uses of the symbol's name, plus uses of the local names it is imported under (aliases)."""
        aliases = {
            (imported.path, imported.local_name)
            for imported in self._index.imports()
            if imported.local_name != symbol.name
            and any(s.qualified_name == symbol.qualified_name for s in self.follow(imported.target))
        }
        candidates = self._index.references(symbol.name)
        for path, local_name in sorted(aliases):
            candidates += [r for r in self._index.references(local_name) if r.path == path]
        return candidates

    def _may_be_in_project(self, qualified_name: str) -> bool:
        parts = qualified_name.split(".")
        return any(self._index.module(".".join(parts[:end])) for end in range(1, len(parts) + 1))

    def _defining_file(self, qualified_name: str) -> str | None:
        module = self._index.module(qualified_name)
        if module is not None:
            return module.path
        found = self.follow(qualified_name)
        return found[0].path if found else None

    def _module_import(self, imported: ImportInfo) -> ModuleImport:
        resolved = self._defining_file(imported.target) or self._defining_file(imported.module)
        return ModuleImport(statement=imported, internal=resolved is not None, resolved_path=resolved)

    def _importers(self, path: str, module: str) -> list[ImportInfo]:
        prefix = f"{module}."
        return [
            imported
            for imported in self._index.imports()
            if imported.path != path
            and (
                imported.module == module
                or imported.target == module
                or imported.target.startswith(prefix)
                or self._defining_file(imported.target) == path
            )
        ]
