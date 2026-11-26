"""Python support, based on the standard library :mod:`ast` (exact, no regular expressions).

Extracted:

* **symbols**: the module, classes, functions, methods (functions defined directly in a class)
  and variables assigned at module or class level. Definitions under ``if``/``try``/``with``...
  blocks are included; local variables of functions are not.
* **imports**: every ``import``/``from ... import`` (also inside functions), with relative
  imports converted to absolute module names.
* **references**: every name read in the file (``Name``) and every attribute access, with its
  full dotted expression when it is a plain chain (``tools.manager.execute``).
"""

import ast
from collections.abc import Iterator

from app.capabilities.code_intelligence.exceptions import ParserError
from app.capabilities.code_intelligence.parsers.base import LanguageParser, file_extension
from app.capabilities.code_intelligence.schemas import (
    FileAnalysis,
    ImportInfo,
    Reference,
    Symbol,
    SymbolKind,
)

_PACKAGE_FILES = ("__init__.py", "__init__.pyi")
FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


class PythonParser(LanguageParser):
    language = "python"
    extensions = (".py", ".pyi")

    def module_name(self, path: str) -> str:
        extension = file_extension(path)
        stem = path[: -len(extension)] if extension else path
        parts = [part for part in stem.split("/") if part not in ("", ".")]
        if len(parts) > 1 and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    def parse(self, path: str, source: str) -> FileAnalysis:
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            raise ParserError(f"Syntax error in {path!r} at line {exc.lineno}: {exc.msg}") from exc
        except ValueError as exc:  # e.g. NUL bytes
            raise ParserError(f"Cannot parse {path!r}: {exc}") from exc

        module = self.module_name(path)
        collector = _Collector(path, module, is_package=path.rsplit("/", 1)[-1] in _PACKAGE_FILES)
        collector.collect_module(tree, line_count=max(1, source.count("\n") + 1))
        return FileAnalysis(
            path=path,
            language=self.language,
            module=module,
            symbols=collector.symbols,
            imports=collector.imports,
            references=list(_references(tree, path)),
        )


class _Collector:
    """Walks the statements of a module, keeping track of the enclosing scope."""

    def __init__(self, path: str, module: str, *, is_package: bool) -> None:
        self._path = path
        self._module = module
        self._is_package = is_package
        self.symbols: list[Symbol] = []
        self.imports: list[ImportInfo] = []
        self._seen_variables: set[str] = set()

    def collect_module(self, tree: ast.Module, *, line_count: int) -> None:
        self.symbols.append(
            Symbol(
                name=self._module.rsplit(".", 1)[-1],
                qualified_name=self._module,
                kind=SymbolKind.MODULE,
                path=self._path,
                line=1,
                end_line=line_count,
                docstring=_summary(ast.get_docstring(tree)),
            )
        )
        self._statements(tree.body, scope=self._module, scope_kind=SymbolKind.MODULE)

    # -- Statements ------------------------------------------------------------------------------

    def _statements(self, body: list[ast.stmt], *, scope: str, scope_kind: SymbolKind) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                self._class(node, scope)
            elif isinstance(node, FunctionNode):
                self._function(node, scope, scope_kind)
            elif isinstance(node, ast.Import | ast.ImportFrom):
                self._import(node)
            elif isinstance(node, ast.Assign | ast.AnnAssign):
                if scope_kind in (SymbolKind.MODULE, SymbolKind.CLASS):
                    self._variables(node, scope)
            else:
                for nested in _nested_bodies(node):  # if / try / with / for / while / match
                    self._statements(nested, scope=scope, scope_kind=scope_kind)

    def _class(self, node: ast.ClassDef, scope: str) -> None:
        qualified = f"{scope}.{node.name}"
        written = [ast.unparse(base) for base in node.bases]
        written += [ast.unparse(keyword) for keyword in node.keywords]
        self._add(
            node,
            name=node.name,
            qualified=qualified,
            kind=SymbolKind.CLASS,
            parent=scope,
            signature=f"class {node.name}({', '.join(written)})" if written else f"class {node.name}",
            bases=[_base_name(base) for base in node.bases],
            decorators=[ast.unparse(d) for d in node.decorator_list],
            docstring=_summary(ast.get_docstring(node)),
        )
        self._statements(node.body, scope=qualified, scope_kind=SymbolKind.CLASS)

    def _function(self, node: FunctionNode, scope: str, scope_kind: SymbolKind) -> None:
        qualified = f"{scope}.{node.name}"
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        signature = f"{prefix} {node.name}({ast.unparse(node.args)})"
        if node.returns is not None:
            signature += f" -> {ast.unparse(node.returns)}"
        self._add(
            node,
            name=node.name,
            qualified=qualified,
            kind=SymbolKind.METHOD if scope_kind is SymbolKind.CLASS else SymbolKind.FUNCTION,
            parent=scope,
            signature=signature,
            decorators=[ast.unparse(d) for d in node.decorator_list],
            docstring=_summary(ast.get_docstring(node)),
        )
        self._statements(node.body, scope=qualified, scope_kind=SymbolKind.FUNCTION)

    def _variables(self, node: ast.Assign | ast.AnnAssign, scope: str) -> None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for name in (n for target in targets for n in _assigned_names(target)):
            qualified = f"{scope}.{name}"
            if qualified in self._seen_variables:  # reassignment: keep the first definition
                continue
            self._seen_variables.add(qualified)
            annotation = node.annotation if isinstance(node, ast.AnnAssign) else None
            self._add(
                node,
                name=name,
                qualified=qualified,
                kind=SymbolKind.VARIABLE,
                parent=scope,
                signature=f"{name}: {ast.unparse(annotation)}" if annotation is not None else None,
            )

    def _import(self, node: ast.Import | ast.ImportFrom) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                target = alias.name if alias.asname else local
                self._add_import(
                    node, module=alias.name, name=None, alias=alias.asname, local=local, target=target
                )
            return

        module = self._absolute_module(node.module, node.level)
        for alias in node.names:
            local = alias.asname or alias.name
            target = module if alias.name == "*" else _join(module, alias.name)
            self._add_import(
                node, module=module, name=alias.name, alias=alias.asname, local=local, target=target
            )

    # -- Helpers ---------------------------------------------------------------------------------

    def _absolute_module(self, module: str | None, level: int) -> str:
        """Resolve ``from ..x import y`` against the current module."""
        if level == 0:
            return module or ""
        package = self._module.split(".") if self._is_package else self._module.split(".")[:-1]
        if level - 1 > len(package):  # goes above the workspace: keep it as written
            return "." * level + (module or "")
        base = package[: len(package) - (level - 1)]
        return ".".join([*base, module] if module else base)

    def _add(self, node: ast.stmt, *, name: str, qualified: str, kind: SymbolKind, **fields: object) -> None:
        self.symbols.append(
            Symbol.model_validate(
                {
                    "name": name,
                    "qualified_name": qualified,
                    "kind": kind,
                    "path": self._path,
                    "line": node.lineno,
                    "end_line": node.end_lineno or node.lineno,
                    **fields,
                }
            )
        )

    def _add_import(
        self, node: ast.stmt, *, module: str, name: str | None, alias: str | None, local: str, target: str
    ) -> None:
        self.imports.append(
            ImportInfo(
                path=self._path,
                line=node.lineno,
                module=module,
                name=name,
                alias=alias,
                local_name=local,
                target=target,
            )
        )


def _join(module: str, name: str) -> str:
    if not module:
        return name
    return f"{module}{name}" if module.endswith(".") else f"{module}.{name}"


def _nested_bodies(node: ast.stmt) -> Iterator[list[ast.stmt]]:
    for field in ("body", "orelse", "finalbody"):
        body = getattr(node, field, None)
        if isinstance(body, list):
            yield body
    for handler in getattr(node, "handlers", []):
        yield handler.body
    for case in getattr(node, "cases", []):
        yield case.body


def _assigned_names(target: ast.expr) -> Iterator[str]:
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, ast.Tuple | ast.List):
        for element in target.elts:
            yield from _assigned_names(element)


def _dotted(node: ast.expr) -> str | None:
    """``a.b.c`` -> ``"a.b.c"``; None when the chain does not start from a plain name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _dotted(node.value)
        return f"{owner}.{node.attr}" if owner else None
    return None


def _base_name(base: ast.expr) -> str:
    """Resolvable name of a base class: ``BaseTool[InputT]`` -> ``BaseTool``."""
    if isinstance(base, ast.Subscript):
        base = base.value
    return _dotted(base) or ast.unparse(base)


def _references(tree: ast.Module, path: str) -> Iterator[Reference]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            yield Reference(
                name=node.id, expression=node.id, path=path, line=node.lineno, column=node.col_offset
            )
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            yield Reference(
                name=node.attr, expression=_dotted(node), path=path, line=node.lineno, column=node.col_offset
            )


def _summary(docstring: str | None) -> str | None:
    if not docstring:
        return None
    return docstring.strip().splitlines()[0]
