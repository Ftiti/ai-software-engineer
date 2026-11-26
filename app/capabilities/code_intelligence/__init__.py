"""Code intelligence capability: understand a project's source code, not only read its files.

tool.py ─► service.py ─► indexer.py ─► analyzer.py ─► parsers/ (one per language)
                    └──► search.py / navigator.py (queries over the index)

The analyzer reads files through the filesystem capability, so the same safety rules apply.
"""

from app.capabilities.code_intelligence.analyzer import CodeAnalyzer
from app.capabilities.code_intelligence.capability import (
    build_code_intelligence_capability,
    build_code_intelligence_service,
)
from app.capabilities.code_intelligence.indexer import SymbolIndex, SymbolIndexer
from app.capabilities.code_intelligence.navigator import CodeNavigator
from app.capabilities.code_intelligence.parsers import (
    LanguageParser,
    ParserRegistry,
    PythonParser,
    default_parsers,
)
from app.capabilities.code_intelligence.search import SymbolSearch
from app.capabilities.code_intelligence.service import CodeIntelligenceService

__all__ = [
    "CodeAnalyzer",
    "CodeIntelligenceService",
    "CodeNavigator",
    "LanguageParser",
    "ParserRegistry",
    "PythonParser",
    "SymbolIndex",
    "SymbolIndexer",
    "SymbolSearch",
    "build_code_intelligence_capability",
    "build_code_intelligence_service",
    "default_parsers",
]
