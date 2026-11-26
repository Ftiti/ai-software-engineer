"""Errors of the code intelligence capability. Messages are written for the LLM: they say what
went wrong and, when possible, what to do instead."""


class CodeIntelligenceError(Exception):
    """Base class: an expected failure reported to the caller, never a crash."""


class UnsupportedLanguage(CodeIntelligenceError):
    """No parser is registered for the file's language."""


class ParserError(CodeIntelligenceError):
    """The source file could not be parsed (syntax error...)."""


class SymbolNotFound(CodeIntelligenceError):
    """A navigation target (class, function...) does not exist in the index."""


class InvalidProject(CodeIntelligenceError):
    """The path to analyze is not a project directory."""


class AmbiguousSymbol(CodeIntelligenceError):
    """A name matches several definitions where exactly one is needed."""
