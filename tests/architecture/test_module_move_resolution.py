"""Resolution preserves module scopes, destination spellings and source boundaries."""

from pathlib import Path

import pytest

from tests.architecture._module_move_resolve import Resolver, compose
from tests.architecture.module_moves import ModuleMove, MoveMap, NameMove
from tests.architecture.test_module_moves import write


@pytest.mark.parametrize("reverse", [False, True])
def test_same_name_conversion_composes_with_later_leaf_move(reverse: bool, tmp_path: Path) -> None:
    entries = (
        ModuleMove("first", "sample.config", "sample.config.schema"),
        ModuleMove("second", "sample.config.schema", "sample.config.model"),
    )
    moves = MoveMap(tuple(reversed(entries)) if reverse else entries, ())
    assert moves.resolve("sample.config.Config", tmp_path) == "sample.config.model.Config"
    assert moves.resolve("sample.config.schema.Config", tmp_path) == "sample.config.model.Config"
    assert moves.resolve("sample.config.model.Config", tmp_path) is None
    assert compose("sample.config", moves) == "sample.config.model"


def test_conversion_follows_a_leaf_outside_and_back_into_the_package(tmp_path: Path) -> None:
    moves = MoveMap(
        (
            ModuleMove("one", "sample.config", "sample.config.schema"),
            ModuleMove("two", "sample.config.schema", "sample.shared_schema"),
            ModuleMove("three", "sample.shared_schema", "sample.config.model"),
        ),
        (),
    )
    assert moves.resolve("sample.config.Config", tmp_path) == "sample.config.model.Config"
    assert moves.resolve("sample.config.model.Config", tmp_path) is None


def test_most_specific_module_and_name_moves_override_package_moves(tmp_path: Path) -> None:
    moves = MoveMap(
        (
            ModuleMove("package", "sample.old", "sample.new", True),
            ModuleMove("leaf", "sample.old.leaf", "sample.special"),
        ),
        (NameMove("split", "sample.old.leaf", "sample.split", ("Special",)),),
    )
    assert moves.resolve("sample.old.other.Value", tmp_path) == "sample.new.other.Value"
    assert moves.resolve("sample.old.leaf.Value", tmp_path) == "sample.special.Value"
    assert (
        moves.resolve("sample.old.leaf.Special.method", tmp_path) == "sample.split.Special.method"
    )
    assert moves.resolve("sample.oldish.Value", tmp_path) is None


@pytest.mark.parametrize(
    "source",
    [
        "try:\n    import missing\nexcept ImportError:\n    from fallback import Value\n",
        "try:\n    pass\nexcept Exception:\n    pass\nelse:\n    Value = 1\n",
        "try:\n    pass\nfinally:\n    Value: int = 1\n",
        "match setting:\n    case 'enabled':\n        from optional import Value\n",
        "match setting:\n    case {'value': Value}:\n        pass\n",
        "match setting:\n    case {'value': first, **Value}:\n        pass\n",
        "match setting:\n    case [*Value]:\n        pass\n",
        "if enabled:\n    First, *Value = choices\n",
        "with opened as Value:\n    pass\n",
        "for Value in choices:\n    pass\n",
        "import elsewhere as Value\n",
    ],
)
def test_control_flow_and_import_bindings_are_current(tmp_path: Path, source: str) -> None:
    write(tmp_path, "src/sample/old.py", source)
    moves = MoveMap((ModuleMove("one", "sample.old", "sample.new"),), ())
    assert moves.resolve("sample.old.Value", tmp_path) is None


@pytest.mark.parametrize(
    "source",
    [
        "def factory():\n    Value = 1\n",
        "class Container:\n    Value = 1\n",
        "items = [Value for Value in choices]\n",
        "items = {Value for Value in choices}\n",
        "items = {Value: 1 for Value in choices}\n",
        "items = (Value for Value in choices)\n",
        "factory = lambda Value: Value\n",
        "Value.attribute = 1\n",
        "Value[0] = 1\n",
    ],
)
def test_nested_or_unbound_names_are_not_current(tmp_path: Path, source: str) -> None:
    write(tmp_path, "src/sample/old.py", source)
    moves = MoveMap((ModuleMove("one", "sample.old", "sample.new"),), ())
    assert moves.resolve("sample.old.Value", tmp_path) == "sample.new.Value"


def test_current_module_and_attribute_use_longest_module_prefix(tmp_path: Path) -> None:
    write(tmp_path, "src/sample/old/__init__.py", '"""The surviving package."""\n')
    write(tmp_path, "src/sample/old/current.py", "class Value:\n    member = 1\n")
    moves = MoveMap((ModuleMove("package", "sample.old", "sample.new", True),), ())
    assert moves.resolve("sample.old.current", tmp_path) is None
    assert moves.resolve("sample.old.current.Value.member", tmp_path) is None
    assert moves.resolve("sample.old.current.Missing", tmp_path) == "sample.new.current.Missing"


@pytest.mark.parametrize(
    "entries",
    [
        (ModuleMove("one", "sample.a", "sample.a"),),
        (ModuleMove("one", "sample.a", "sample.a.child", True),),
        (ModuleMove("one", "sample.a", "sample.b"), ModuleMove("two", "sample.b", "sample.a")),
        (
            ModuleMove("one", "sample.a", "sample.b.child", True),
            ModuleMove("two", "sample.b", "sample.a.child", True),
        ),
        (
            ModuleMove("one", "sample.a", "sample.a.impl"),
            ModuleMove("two", "sample.a.impl", "sample.a"),
        ),
    ],
)
def test_direct_maps_reject_cycles_and_package_growth(entries: tuple[ModuleMove, ...]) -> None:
    with pytest.raises(ValueError, match="Non-idempotent"):
        compose("sample.a", MoveMap(entries, ()))


@pytest.mark.parametrize("link", ["src", "src/sample", "src/sample/old.py", "tests"])
def test_currentness_never_reads_through_symlinks(tmp_path: Path, link: str) -> None:
    root, outside = tmp_path / "repo", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    # Invalid source makes an accidental read fail before an assertion can hide it.
    write(outside, "sample/old.py", "not valid Python !\n")
    write(outside, "old.py", "not valid Python !\n")
    symlink = root / link
    symlink.parent.mkdir(parents=True, exist_ok=True)
    symlink.symlink_to(outside / "old.py" if link.endswith(".py") else outside)
    module = "tests.old" if link == "tests" else "sample.old"
    resolver = Resolver(MoveMap((), ()), root)
    assert resolver.module_file(module) is None
    assert not resolver.current(module + ".Value")


@pytest.mark.parametrize(
    "module",
    [
        "tests.fixtures.old",
        "tests.shared_skills.old",
        "tests.build.old",
        "catalog.old",
        "docs.adr.old",
    ],
)
def test_currentness_never_reads_excluded_directories(tmp_path: Path, module: str) -> None:
    write(tmp_path, module.replace(".", "/") + ".py", "not valid Python !\n")
    resolver = Resolver(MoveMap((), ()), tmp_path)
    assert resolver.module_file(module) is None
    assert not resolver.current(module + ".Value")


@pytest.mark.parametrize("module", ["../outside", "/absolute/module", "sample..old"])
def test_module_lookup_refuses_non_module_paths(tmp_path: Path, module: str) -> None:
    assert Resolver(MoveMap((), ()), tmp_path).module_file(module) is None
