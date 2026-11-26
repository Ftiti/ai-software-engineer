"""Parser abstraction: the only language-specific part of code intelligence.

A :class:`LanguageParser` turns one source file into a :class:`FileAnalysis` (symbols, imports,
references). Supporting a new language (PHP, JavaScript, TypeScript, Java, Go...) means writing
one subclass and registering it; the analyzer, index, search engine and navigator stay unchanged.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable

from app.capabilities.code_intelligence.exceptions import UnsupportedLanguage
from app.capabilities.code_intelligence.schemas import FileAnalysis


class LanguageParser(ABC):
    language: str
    extensions: tuple[str, ...]  # lowercase, with the dot: (".py",)

    @abstractmethod
    def module_name(self, path: str) -> str:
        """Dotted module name of a workspace-relative file: ``app/tools/base.py`` -> ``app.tools.base``."""

    @abstractmethod
    def parse(self, path: str, source: str) -> FileAnalysis:
        """Analyze ``source`` (the content of ``path``).

        Raise :class:`~app.capabilities.code_intelligence.exceptions.ParserError` when the
        source is not valid for the language.
        """


def file_extension(path: str) -> str:
    """``"src/App.Test.PY"`` -> ``".py"``; ``""`` when the file name has no extension."""
    name = path.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    return name[dot:].lower() if dot > 0 else ""


class ParserRegistry:
    """Chooses the parser of a file from its extension."""

    def __init__(self, parsers: Iterable[LanguageParser] = ()) -> None:
        self._by_extension: dict[str, LanguageParser] = {}
        for parser in parsers:
            self.register(parser)

    def register(self, parser: LanguageParser) -> None:
        for extension in parser.extensions:
            current = self._by_extension.get(extension)
            if current is not None and current is not parser:
                raise ValueError(
                    f"Extension {extension!r} is already handled by the {current.language} parser"
                )
            self._by_extension[extension] = parser

    def supports(self, path: str) -> bool:
        return file_extension(path) in self._by_extension

    def for_path(self, path: str) -> LanguageParser:
        parser = self._by_extension.get(file_extension(path))
        if parser is None:
            raise UnsupportedLanguage(
                f"No parser for {path!r}. Supported languages: {', '.join(self.languages) or 'none'}"
            )
        return parser

    @property
    def languages(self) -> list[str]:
        return sorted({parser.language for parser in self._by_extension.values()})
