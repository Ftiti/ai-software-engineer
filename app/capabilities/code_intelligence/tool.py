"""Code intelligence tools: thin wrappers exposing :class:`CodeIntelligenceService`.

Threading, error translation and serialisation come from
:class:`app.capabilities.base.CapabilityTool`.
"""

from typing import Any, TypeVar

from pydantic import BaseModel

from app.capabilities.base import CapabilityTool
from app.capabilities.code_intelligence.exceptions import CodeIntelligenceError
from app.capabilities.code_intelligence.schemas import (
    AnalyzeFileRequest,
    AnalyzeProjectRequest,
    FindNamedRequest,
    FindReferencesRequest,
    FindSymbolRequest,
    ModuleDependenciesRequest,
    NavigationRequest,
    SearchImportRequest,
)
from app.capabilities.code_intelligence.service import CodeIntelligenceService
from app.capabilities.filesystem.exceptions import FilesystemError
from app.tools import BaseTool

InputT = TypeVar("InputT", bound=BaseModel)


class CodeIntelligenceTool(CapabilityTool[InputT]):
    errors = (CodeIntelligenceError, FilesystemError)

    def __init__(self, service: CodeIntelligenceService) -> None:
        self._service = service


class AnalyzeProjectTool(CodeIntelligenceTool[AnalyzeProjectRequest]):
    name = "analyze_project"
    description = (
        "Overview of the project's source code: languages, number of classes/functions, and every "
        "module with its path. Start here to understand an unfamiliar project."
    )
    input_model = AnalyzeProjectRequest

    def _run(self, params: AnalyzeProjectRequest) -> BaseModel:
        return self._service.analyze_project(params.path)


class AnalyzeFileTool(CodeIntelligenceTool[AnalyzeFileRequest]):
    name = "analyze_file"
    description = (
        "Structure of one source file: imports, classes, functions, methods and variables with "
        "their signatures, docstrings and line numbers."
    )
    input_model = AnalyzeFileRequest

    def _run(self, params: AnalyzeFileRequest) -> BaseModel:
        return self._service.analyze_file(params.path)


class FindSymbolTool(CodeIntelligenceTool[FindSymbolRequest]):
    name = "find_symbol"
    description = (
        "Find definitions (modules, classes, functions, methods, variables) by name. Exact matches "
        "come first; a dotted query such as 'ToolManager.execute' matches qualified names."
    )
    input_model = FindSymbolRequest

    def _run(self, params: FindSymbolRequest) -> BaseModel:
        return self._service.find_symbol(params.query, params.kind, params.limit)


class FindClassTool(CodeIntelligenceTool[FindNamedRequest]):
    name = "find_class"
    description = "Find class definitions by name, with their base classes and location."
    input_model = FindNamedRequest

    def _run(self, params: FindNamedRequest) -> BaseModel:
        return self._service.find_class(params.query, params.limit)


class FindFunctionTool(CodeIntelligenceTool[FindNamedRequest]):
    name = "find_function"
    description = "Find function and method definitions by name, with their signature and location."
    input_model = FindNamedRequest

    def _run(self, params: FindNamedRequest) -> BaseModel:
        return self._service.find_function(params.query, params.limit)


class SearchImportTool(CodeIntelligenceTool[SearchImportRequest]):
    name = "search_import"
    description = "Find where a module (or one of its submodules) or an imported name is imported."
    input_model = SearchImportRequest

    def _run(self, params: SearchImportRequest) -> BaseModel:
        return self._service.search_import(params.module, params.limit)


class FindDefinitionTool(CodeIntelligenceTool[NavigationRequest]):
    name = "find_definition"
    description = (
        "Go to the definition of a name. Give 'path' (the file where the name is used) to resolve it "
        "through that file's imports, as an IDE would."
    )
    input_model = NavigationRequest

    def _run(self, params: NavigationRequest) -> BaseModel:
        return self._service.find_definition(params.name, params.path)


class FindReferencesTool(CodeIntelligenceTool[FindReferencesRequest]):
    name = "find_references"
    description = (
        "Find where a symbol is used. confirmed=true uses were resolved to this symbol; "
        "confirmed=false uses have the same name but a target unknown statically (e.g. self.method)."
    )
    input_model = FindReferencesRequest

    def _run(self, params: FindReferencesRequest) -> BaseModel:
        return self._service.find_references(params.name, params.path, params.limit)


class ClassHierarchyTool(CodeIntelligenceTool[NavigationRequest]):
    name = "class_hierarchy"
    description = "Parent classes and direct child classes of a class."
    input_model = NavigationRequest

    def _run(self, params: NavigationRequest) -> BaseModel:
        return self._service.class_hierarchy(params.name, params.path)


class ModuleDependenciesTool(CodeIntelligenceTool[ModuleDependenciesRequest]):
    name = "module_dependencies"
    description = (
        "What a source file imports (internal or external, with the file defining each import) and "
        "which project files import it. Check this before changing a module."
    )
    input_model = ModuleDependenciesRequest

    def _run(self, params: ModuleDependenciesRequest) -> BaseModel:
        return self._service.module_dependencies(params.path)


TOOL_CLASSES: tuple[type[CodeIntelligenceTool[Any]], ...] = (
    AnalyzeProjectTool,
    AnalyzeFileTool,
    FindSymbolTool,
    FindClassTool,
    FindFunctionTool,
    SearchImportTool,
    FindDefinitionTool,
    FindReferencesTool,
    ClassHierarchyTool,
    ModuleDependenciesTool,
)


def code_intelligence_tools(service: CodeIntelligenceService) -> list[BaseTool[Any]]:
    """One instance of every code intelligence tool, sharing ``service``."""
    return [tool_class(service) for tool_class in TOOL_CLASSES]
