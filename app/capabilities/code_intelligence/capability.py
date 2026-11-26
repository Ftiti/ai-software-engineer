"""Assembles the code intelligence capability:
filesystem service -> analyzer (+ parsers) -> indexer -> service -> tools."""

from app.capabilities.base import Capability
from app.capabilities.code_intelligence.analyzer import CodeAnalyzer
from app.capabilities.code_intelligence.indexer import SymbolIndexer
from app.capabilities.code_intelligence.parsers import ParserRegistry, default_parsers
from app.capabilities.code_intelligence.prompts import CODE_INTELLIGENCE_PROMPT
from app.capabilities.code_intelligence.service import CodeIntelligenceService
from app.capabilities.code_intelligence.tool import code_intelligence_tools
from app.capabilities.filesystem import FilesystemService
from app.config import Settings


def build_code_intelligence_service(
    settings: Settings, files: FilesystemService, parsers: ParserRegistry | None = None
) -> CodeIntelligenceService:
    """``files`` gives safe read access to the project; ``parsers`` defaults to every built-in language."""
    analyzer = CodeAnalyzer(files, parsers or default_parsers())
    return CodeIntelligenceService(analyzer, SymbolIndexer(analyzer), max_results=settings.code_max_results)


def build_code_intelligence_capability(service: CodeIntelligenceService) -> Capability:
    return Capability(
        name="code_intelligence", tools=code_intelligence_tools(service), prompt=CODE_INTELLIGENCE_PROMPT
    )
