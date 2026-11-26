"""Parser abstraction and the Python parser: symbols, imports, references, errors."""

import pytest

from app.capabilities.code_intelligence.exceptions import ParserError, UnsupportedLanguage
from app.capabilities.code_intelligence.parsers import (
    LanguageParser,
    ParserRegistry,
    PythonParser,
    default_parsers,
    file_extension,
)
from app.capabilities.code_intelligence.schemas import FileAnalysis, Symbol, SymbolKind
from tests.unit.code_intelligence.conftest import PROJECT

parser = PythonParser()


def symbols(path: str) -> dict[str, Symbol]:
    return {s.qualified_name: s for s in parser.parse(path, PROJECT[path]).symbols}


# -- Module names -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "module"),
    [
        ("app/tools/base.py", "app.tools.base"),
        ("app/tools/__init__.py", "app.tools"),
        ("main.py", "main"),
        ("__init__.py", "__init__"),
        ("stubs/types.pyi", "stubs.types"),
    ],
)
def test_module_name(path: str, module: str) -> None:
    assert parser.module_name(path) == module


# -- Symbols ------------------------------------------------------------------------------------


def test_extracts_every_kind_of_definition() -> None:
    found = symbols("pkg/models.py")
    kinds = {name.removeprefix("pkg.models."): s.kind for name, s in found.items()}
    assert kinds == {
        "pkg.models": SymbolKind.MODULE,
        "T": SymbolKind.VARIABLE,
        "MAX_LEGS": SymbolKind.VARIABLE,
        "Animal": SymbolKind.CLASS,
        "Animal.sound": SymbolKind.VARIABLE,
        "Animal.speak": SymbolKind.METHOD,
        "Dog": SymbolKind.CLASS,
        "Dog.speak": SymbolKind.METHOD,
        "Dog.fetch": SymbolKind.METHOD,
        "Box": SymbolKind.CLASS,
    }  # local variables of functions are not symbols


def test_symbol_details() -> None:
    found = symbols("pkg/models.py")
    animal, speak, fetch = (
        found["pkg.models.Animal"],
        found["pkg.models.Animal.speak"],
        found["pkg.models.Dog.fetch"],
    )

    assert (animal.line, animal.end_line, animal.parent) == (9, 18, "pkg.models")
    assert animal.docstring == "Base of every animal."
    assert animal.signature == "class Animal(ABC)"
    assert speak.parent == "pkg.models.Animal"
    assert speak.decorators == ["abstractmethod"]
    assert speak.signature == "def speak(self) -> str"
    assert fetch.signature == "async def fetch(self, item: str='ball') -> str"
    assert found["pkg.models.MAX_LEGS"].signature == "MAX_LEGS: int"
    assert found["pkg.models"].docstring == "Domain models."


def test_generic_bases_are_reduced_to_their_name() -> None:
    box = symbols("pkg/models.py")["pkg.models.Box"]
    assert box.bases == ["Generic"]
    assert box.signature == "class Box(Generic[T])"


def test_nested_functions_and_conditional_definitions() -> None:
    source = (
        "import sys\n"
        "if sys.version_info >= (3, 12):\n"
        "    def modern(): ...\n"
        "else:\n"
        "    def modern(): ...\n"
        "try:\n"
        "    import tomllib\n"
        "except ImportError:\n"
        "    tomllib = None\n"
        "a, (b, c) = 1, (2, 3)\n"
        "def outer():\n"
        "    def inner(): ...\n"
    )
    analysis = parser.parse("cond.py", source)
    names = [(s.qualified_name, s.kind) for s in analysis.symbols]

    assert ("cond.modern", SymbolKind.FUNCTION) in names
    assert ("cond.outer.inner", SymbolKind.FUNCTION) in names
    assert {"cond.tomllib", "cond.a", "cond.b", "cond.c"} <= {n for n, _ in names}
    assert "tomllib" in {i.module for i in analysis.imports}


# -- Imports ------------------------------------------------------------------------------------


def test_imports_are_resolved_to_absolute_names() -> None:
    imports = {
        i.local_name: i for i in parser.parse("pkg/services/zoo.py", PROJECT["pkg/services/zoo.py"]).imports
    }

    assert (imports["models"].module, imports["models"].target) == ("pkg", "pkg.models")
    assert (imports["Hound"].module, imports["Hound"].name, imports["Hound"].alias) == (
        "pkg.models",
        "Dog",
        "Hound",
    )
    assert imports["Hound"].target == "pkg.models.Dog"
    assert (imports["pkg"].module, imports["pkg"].target) == ("pkg", "pkg")
    assert imports["json"].line == 4


@pytest.mark.parametrize(
    ("path", "statement", "local", "target"),
    [
        ("a/b/c.py", "import os.path", "os", "os"),
        ("a/b/c.py", "import os.path as osp", "osp", "os.path"),
        ("a/b/c.py", "from . import d", "d", "a.b.d"),
        ("a/b/__init__.py", "from . import d", "d", "a.b.d"),
        ("a/b/c.py", "from ...x import y", "y", "x.y"),
        ("a/b/c.py", "from .... import y", "y", "....y"),
        ("a/b/c.py", "from m import *", "*", "m"),
    ],
)
def test_import_forms(path: str, statement: str, local: str, target: str) -> None:
    (imported,) = parser.parse(path, statement).imports
    assert (imported.local_name, imported.target) == (local, target)


def test_imports_inside_functions_are_dependencies_too() -> None:
    analysis = parser.parse("lazy.py", "def load():\n    import yaml\n")
    assert [i.module for i in analysis.imports] == ["yaml"]


# -- References ---------------------------------------------------------------------------------


def test_references_record_names_and_dotted_expressions() -> None:
    analysis = parser.parse("pkg/services/zoo.py", PROJECT["pkg/services/zoo.py"])
    refs = {(r.name, r.expression) for r in analysis.references}

    assert ("Hound", "Hound") in refs  # base class and call
    assert ("dumps", "json.dumps") in refs
    assert ("Animal", "models.Animal") in refs  # annotation
    assert ("upper", None) in refs  # animal.speak().upper(): not a plain chain
    assert "Puppy" not in {name for name, _ in refs}  # definitions are not references


def test_references_are_not_sent_to_the_llm() -> None:
    analysis = parser.parse("pkg/services/zoo.py", PROJECT["pkg/services/zoo.py"])
    assert analysis.references
    assert "references" not in analysis.model_dump()


# -- Errors -------------------------------------------------------------------------------------


def test_syntax_error_becomes_parser_error() -> None:
    with pytest.raises(ParserError, match=r"Syntax error in 'pkg/broken.py' at line 1"):
        parser.parse("pkg/broken.py", PROJECT["pkg/broken.py"])


def test_nul_byte_becomes_parser_error() -> None:
    with pytest.raises(ParserError):
        parser.parse("x.py", "a = 1\x00")


# -- Registry: extensibility --------------------------------------------------------------------


class ToyParser(LanguageParser):
    """A second language, to prove new parsers plug in without changing existing code."""

    language = "toy"
    extensions = (".toy",)

    def module_name(self, path: str) -> str:
        return path.removesuffix(".toy").replace("/", ".")

    def parse(self, path: str, source: str) -> FileAnalysis:
        module = self.module_name(path)
        return FileAnalysis(path=path, language=self.language, module=module)


@pytest.mark.parametrize(
    ("path", "extension"),
    [("a/b.py", ".py"), ("A.PY", ".py"), ("a.b/c", ""), (".bashrc", ""), ("x.tar.gz", ".gz")],
)
def test_file_extension(path: str, extension: str) -> None:
    assert file_extension(path) == extension


def test_registry_selects_parser_by_extension() -> None:
    registry = ParserRegistry([PythonParser(), ToyParser()])
    assert registry.languages == ["python", "toy"]
    assert isinstance(registry.for_path("src/main.py"), PythonParser)
    assert isinstance(registry.for_path("src/game.toy"), ToyParser)
    assert registry.supports("x.pyi") and not registry.supports("README.md")


def test_unsupported_language_lists_the_supported_ones() -> None:
    with pytest.raises(UnsupportedLanguage, match="Supported languages: python"):
        default_parsers().for_path("index.php")


def test_two_parsers_cannot_claim_the_same_extension() -> None:
    class OtherPython(ToyParser):
        language = "other"
        extensions = (".py",)

    with pytest.raises(ValueError, match="already handled by the python parser"):
        ParserRegistry([PythonParser(), OtherPython()])
