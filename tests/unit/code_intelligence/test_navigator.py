"""CodeNavigator: name resolution, definitions, references, class hierarchy, dependencies."""

import pytest

from app.capabilities.code_intelligence import CodeNavigator, PythonParser, SymbolIndex
from app.capabilities.code_intelligence.exceptions import AmbiguousSymbol, SymbolNotFound
from app.capabilities.code_intelligence.schemas import ProjectAnalysis, Symbol, SymbolKind

ZOO = "pkg/services/zoo.py"


# -- Resolution and definitions -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "qualified"),
    [
        ("Hound", "pkg.models.Dog"),  # aliased import
        ("models.Animal", "pkg.models.Animal"),  # relative module import
        ("Puppy.speak", "pkg.services.zoo.Puppy.speak"),  # local definition
        ("json.dumps", "json.dumps"),  # external
        ("self.speak", None),  # dynamic
        ("print", None),  # builtin
    ],
)
def test_resolve(navigator: CodeNavigator, expression: str, qualified: str | None) -> None:
    assert navigator.resolve(expression, ZOO) == qualified


def test_go_to_definition_through_the_file_imports(navigator: CodeNavigator) -> None:
    (dog,) = navigator.definitions("Hound", ZOO)
    assert (dog.qualified_name, dog.path, dog.line) == ("pkg.models.Dog", "pkg/models.py", 21)


def test_reexports_are_followed(navigator: CodeNavigator) -> None:
    (animal,) = navigator.definitions("pkg.Animal")  # pkg/__init__.py re-exports it
    assert animal.qualified_name == "pkg.models.Animal"
    assert navigator.resolve("pkg.Animal", ZOO) == "pkg.Animal"
    assert [s.qualified_name for s in navigator.definitions("pkg.Animal", ZOO)] == ["pkg.models.Animal"]


def test_definitions_by_name_or_suffix(navigator: CodeNavigator) -> None:
    assert [s.qualified_name for s in navigator.definitions("Dog.speak")] == ["pkg.models.Dog.speak"]
    assert len(navigator.definitions("speak")) == 3


def test_star_imports_are_resolved(index: SymbolIndex) -> None:
    star = PythonParser().parse("pkg/star.py", "from pkg.models import *\nBox()\n")
    navigator = CodeNavigator(SymbolIndex(ProjectAnalysis(path=".", files=[*index.files, star])))
    assert navigator.resolve("Box", "pkg/star.py") == "pkg.models.Box"


def test_unknown_and_ambiguous_names(navigator: CodeNavigator) -> None:
    with pytest.raises(SymbolNotFound, match="find_symbol"):
        navigator.definitions("Unicorn")
    with pytest.raises(AmbiguousSymbol, match=r"Animal\.speak, pkg\.models\.Dog\.speak"):
        navigator.definition("speak")


# -- References ---------------------------------------------------------------------------------


def test_references_follow_import_aliases(navigator: CodeNavigator) -> None:
    dog = navigator.definition("pkg.models.Dog")
    refs = [
        (m.reference.path, m.reference.line, m.reference.name, m.confirmed) for m in navigator.references(dog)
    ]
    assert refs == [(ZOO, 7, "Hound", True), (ZOO, 20, "Hound", True)]  # class Puppy(Hound), Hound()


def test_references_are_resolved_not_matched_by_text(navigator: CodeNavigator) -> None:
    animal = navigator.definition("pkg.models.Animal")
    matches = navigator.references(animal)

    confirmed = {(m.reference.path, m.reference.line) for m in matches if m.confirmed}
    assert confirmed == {
        ("pkg/models.py", 21),
        (ZOO, 12),
        (ZOO, 19),
    }  # Dog(Animal), models.Animal, pkg.Animal
    assert all(m.confirmed for m in matches)


def test_method_references_keep_unresolvable_uses_as_unconfirmed(navigator: CodeNavigator) -> None:
    speak = navigator.definition("Animal.speak")
    matches = navigator.references(speak)
    assert [(m.reference.expression, m.confirmed) for m in matches] == [("animal.speak", False)]


def test_references_to_external_names_are_excluded(navigator: CodeNavigator) -> None:
    fake = Symbol(
        name="dumps",
        qualified_name="pkg.models.dumps",
        kind=SymbolKind.FUNCTION,
        path="x",
        line=1,
        end_line=1,
    )
    assert navigator.references(fake) == []  # json.dumps resolves to the json library


# -- Class hierarchy ----------------------------------------------------------------------------


def test_parents_and_children(navigator: CodeNavigator) -> None:
    (animal,) = navigator.hierarchy("Animal")
    assert [(p.expression, p.resolved) for p in animal.parents] == [("ABC", None)]  # outside the project
    assert [c.qualified_name for c in animal.children] == ["pkg.models.Dog"]

    (puppy,) = navigator.hierarchy("Puppy")
    assert puppy.parents[0].expression == "Hound"
    assert puppy.parents[0].resolved is not None
    assert puppy.parents[0].resolved.qualified_name == "pkg.models.Dog"

    (dog,) = navigator.hierarchy("Dog")
    assert [c.qualified_name for c in dog.children] == ["pkg.services.zoo.Puppy"]


def test_hierarchy_requires_a_class(navigator: CodeNavigator) -> None:
    with pytest.raises(SymbolNotFound, match="is not a class"):
        navigator.hierarchy("adopt")


# -- Module dependencies ------------------------------------------------------------------------


def test_module_dependencies(navigator: CodeNavigator) -> None:
    deps = navigator.module_dependencies(ZOO)
    imports = {i.statement.local_name: (i.internal, i.resolved_path) for i in deps.imports}

    assert deps.module == "pkg.services.zoo"
    assert imports == {
        "models": (True, "pkg/models.py"),
        "Hound": (True, "pkg/models.py"),
        "pkg": (True, "pkg/__init__.py"),
        "json": (False, None),
    }


def test_imported_by_includes_imports_through_reexports(navigator: CodeNavigator) -> None:
    importers = {(i.path, i.local_name) for i in navigator.module_dependencies("pkg/models.py").imported_by}
    assert importers == {("pkg/__init__.py", "Animal"), (ZOO, "models"), (ZOO, "Hound")}


def test_module_dependencies_of_an_unknown_file(navigator: CodeNavigator) -> None:
    with pytest.raises(SymbolNotFound):
        navigator.module_dependencies("pkg/broken.py")
