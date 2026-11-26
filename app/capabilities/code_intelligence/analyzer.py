"""Turns source files into :class:`FileAnalysis` objects.

The analyzer reads the project through the :class:`FilesystemService`, so it inherits every
filesystem safety rule (workspace confinement, secrets hidden, ignored folders such as
``.venv`` skipped, size limits), and delegates parsing to the parser registered for each
file's language. Parse results are cached by content hash: re-analyzing an unchanged file
costs one read, never a re-parse, and an edited file is never served stale.
"""

import hashlib
import threading

from app.capabilities.code_intelligence.exceptions import CodeIntelligenceError, InvalidProject
from app.capabilities.code_intelligence.parsers import LanguageParser, ParserRegistry
from app.capabilities.code_intelligence.schemas import AnalysisFailure, FileAnalysis, ProjectAnalysis
from app.capabilities.filesystem import FilesystemService
from app.capabilities.filesystem.exceptions import DirectoryNotFound, FilesystemError, NotADirectory


class CodeAnalyzer:
    def __init__(self, files: FilesystemService, parsers: ParserRegistry) -> None:
        self._files = files
        self._parsers = parsers
        self._cache: dict[str, tuple[str, FileAnalysis]] = {}  # path -> (content digest, analysis)
        self._lock = threading.Lock()  # tools may run concurrently in worker threads

    @property
    def languages(self) -> list[str]:
        return self._parsers.languages

    def analyze_file(self, path: str) -> FileAnalysis:
        """Analyze one source file. Raises ``UnsupportedLanguage``, ``ParserError`` or a filesystem error."""
        parser = self._parsers.for_path(path)  # fail before reading anything
        file = self._files.read_file(path)
        return self._parse(parser, file.path, file.content)

    def analyze_project(self, path: str = ".") -> ProjectAnalysis:
        """Analyze every supported source file below ``path``.

        A file that cannot be read or parsed is reported in ``failures`` instead of aborting
        the whole analysis.
        """
        try:
            listing = self._files.list_directory(path, recursive=True)
        except (DirectoryNotFound, NotADirectory) as exc:
            raise InvalidProject(f"{path!r} is not a project directory: {exc}") from exc

        sources = sorted(
            entry.path
            for entry in listing.entries
            if entry.type == "file" and self._parsers.supports(entry.path)
        )
        analyses: list[FileAnalysis] = []
        failures: list[AnalysisFailure] = []
        for source in sources:
            try:
                analyses.append(self.analyze_file(source))
            except (CodeIntelligenceError, FilesystemError) as exc:
                failures.append(AnalysisFailure(path=source, reason=str(exc)))

        if listing.path == ".":  # full scan: forget files that no longer exist
            self._forget_all_but({analysis.path for analysis in analyses})
        return ProjectAnalysis(
            path=listing.path, files=analyses, failures=failures, truncated=listing.truncated
        )

    def _parse(self, parser: LanguageParser, path: str, source: str) -> FileAnalysis:
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        with self._lock:
            cached = self._cache.get(path)
        if cached is not None and cached[0] == digest:
            return cached[1]
        analysis = parser.parse(path, source)
        with self._lock:
            self._cache[path] = (digest, analysis)
        return analysis

    def _forget_all_but(self, paths: set[str]) -> None:
        with self._lock:
            for stale in self._cache.keys() - paths:
                del self._cache[stale]
