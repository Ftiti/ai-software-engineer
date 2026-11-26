"""Language parsers. To support a language, implement :class:`LanguageParser` in a new module
and add it to :func:`default_parsers`."""

from app.capabilities.code_intelligence.parsers.base import LanguageParser, ParserRegistry, file_extension
from app.capabilities.code_intelligence.parsers.python import PythonParser


def default_parsers() -> ParserRegistry:
    """Registry of every built-in language parser."""
    return ParserRegistry([PythonParser()])


__all__ = ["LanguageParser", "ParserRegistry", "PythonParser", "default_parsers", "file_extension"]
