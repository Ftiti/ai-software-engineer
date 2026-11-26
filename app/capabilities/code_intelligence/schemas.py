"""Language-neutral data model of the code intelligence capability.

Parsers translate a language into these models; the indexer, search engine and navigator only
ever see them, so they work unchanged for every language. Qualified names always use ``.`` as
separator (``package.module.Class.method``), whatever the language's own notation.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class SymbolKind(StrEnum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"


class Symbol(BaseModel):
    """A named definition."""

    name: str
    qualified_name: str
    kind: SymbolKind
    path: str
    line: int
    end_line: int
    parent: str | None = Field(default=None, description="Qualified name of the enclosing symbol")
    signature: str | None = None
    bases: list[str] = Field(default_factory=list, description="Base classes, as written in the source")
    decorators: list[str] = Field(default_factory=list)
    docstring: str | None = Field(default=None, description="First line of the documentation")


class ImportInfo(BaseModel):
    """One imported name and the local name it is bound to.

    ``import a.b`` binds ``a`` to ``a``; ``from a import b as c`` binds ``c`` to ``a.b``.
    """

    path: str
    line: int
    module: str = Field(description="Absolute module the import reads from")
    name: str | None = Field(default=None, description="Imported member, None for a whole module")
    alias: str | None = None
    local_name: str = Field(description="Name visible in the importing file")
    target: str = Field(description="Qualified name the local name refers to")


class Reference(BaseModel):
    """A use of a name (call, attribute access, base class, annotation...)."""

    name: str = Field(description="The identifier used, e.g. 'execute'")
    expression: str | None = Field(
        default=None, description="Full dotted expression when statically known, e.g. 'tools.execute'"
    )
    path: str
    line: int
    column: int


class FileAnalysis(BaseModel):
    path: str
    language: str
    module: str
    symbols: list[Symbol] = Field(default_factory=list)
    imports: list[ImportInfo] = Field(default_factory=list)
    # Used by navigation; too verbose to send to the LLM with every analysis.
    references: list[Reference] = Field(default_factory=list, exclude=True)


class AnalysisFailure(BaseModel):
    path: str
    reason: str


class ProjectAnalysis(BaseModel):
    """Every supported source file below ``path`` that could be analyzed, plus the failures."""

    path: str
    files: list[FileAnalysis] = Field(default_factory=list)
    failures: list[AnalysisFailure] = Field(default_factory=list)
    truncated: bool = Field(default=False, description="The file listing hit its size limit")


# -- Tool requests ------------------------------------------------------------------------------


class AnalyzeProjectRequest(BaseModel):
    path: str = Field(default=".", description="Project directory, relative to the workspace")


class AnalyzeFileRequest(BaseModel):
    path: str = Field(description="Source file, relative to the workspace")


class FindSymbolRequest(BaseModel):
    query: str = Field(min_length=1, description="Name or dotted qualified name, e.g. 'ToolManager'")
    kind: SymbolKind | None = Field(default=None, description="Restrict to one kind of symbol")
    limit: int | None = Field(default=None, gt=0, description="Maximum number of results")


class FindNamedRequest(BaseModel):
    query: str = Field(min_length=1, description="Name or dotted qualified name")
    limit: int | None = Field(default=None, gt=0, description="Maximum number of results")


class SearchImportRequest(BaseModel):
    module: str = Field(min_length=1, description="Module or imported name, e.g. 'pydantic' or 'app.tools'")
    limit: int | None = Field(default=None, gt=0, description="Maximum number of results")


class NavigationRequest(BaseModel):
    name: str = Field(min_length=1, description="Symbol name or qualified name, e.g. 'BaseTool.execute'")
    path: str | None = Field(
        default=None, description="File where the name is used: resolves it through that file's imports"
    )


class FindReferencesRequest(NavigationRequest):
    limit: int | None = Field(default=None, gt=0, description="Maximum number of results")


class ModuleDependenciesRequest(BaseModel):
    path: str = Field(description="Source file, relative to the workspace")


# -- Tool responses -----------------------------------------------------------------------------


class FileSummary(BaseModel):
    path: str
    module: str
    language: str
    classes: int
    functions: int
    imports: int


class ProjectSummary(BaseModel):
    path: str
    files: int
    languages: dict[str, int]
    symbols: dict[SymbolKind, int]
    modules: list[FileSummary]
    failures: list[AnalysisFailure]
    truncated: bool


class SymbolMatches(BaseModel):
    query: str
    matches: list[Symbol]
    total: int = Field(description="Matches before applying the limit")


class ImportMatches(BaseModel):
    module: str
    matches: list[ImportInfo]
    total: int


class Definitions(BaseModel):
    name: str
    definitions: list[Symbol]


class ReferenceMatch(BaseModel):
    reference: Reference
    confirmed: bool = Field(
        description="True when the name was resolved to the symbol; False when it only has the same "
        "name and its target is unknown statically (e.g. 'self.method')"
    )


class References(BaseModel):
    symbol: Symbol
    references: list[ReferenceMatch]
    total: int = Field(description="References before applying the limit")


class BaseClass(BaseModel):
    expression: str = Field(description="Base class as written in the source")
    resolved: Symbol | None = Field(default=None, description="None for classes outside the project")


class ClassHierarchy(BaseModel):
    symbol: Symbol
    parents: list[BaseClass]
    children: list[Symbol]


class ClassHierarchies(BaseModel):
    name: str
    hierarchies: list[ClassHierarchy]


class ModuleImport(BaseModel):
    statement: ImportInfo
    internal: bool = Field(description="The module belongs to the project")
    resolved_path: str | None = None


class ModuleDependencies(BaseModel):
    path: str
    module: str
    imports: list[ModuleImport]
    imported_by: list[ImportInfo] = Field(description="Imports of this module in other project files")
