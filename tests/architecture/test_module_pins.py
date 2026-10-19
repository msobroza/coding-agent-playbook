"""Engine module names a test asserts on go through ``tests.engine_modules.engine_module``.

``assert "coding_agent_playbook.x" not in loaded`` stays true forever once ``x``
moves, and so does a module-level constant, a set display or a ``startswith``
prefix spelled as a raw string. ``engine_module`` resolves the name with
``importlib.util.find_spec`` and fails when it is stale, so this scan rejects those
raw spellings in every test file. A list, tuple or set of expected names compared
with ``==`` fails loudly on its own and is not flagged.
"""

from __future__ import annotations

import ast
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator, Set

_TESTS_ROOT: Final = Path(__file__).resolve().parents[1]
_ENGINE_NAME: Final = re.compile(r"^coding_agent_playbook(\.[A-Za-z_][A-Za-z0-9_]*)+$")
#: Engine-prefixed strings that are not modules: bundled-plugin overlay ids, and
#: (exact names only, read from pyproject.toml) the entry-point group names, one of
#: which is also a package (``coding_agent_playbook.adapters``).
_OVERLAY_NAMESPACES: Final = ("coding_agent_playbook.plugins", "coding_agent_playbook.packs")


@dataclass(frozen=True, order=True)
class RawPin:
    """One raw engine module name in a test file."""

    path: str
    line: int
    name: str


def _entry_point_groups() -> frozenset[str]:
    pyproject = tomllib.loads((_TESTS_ROOT.parent / "pyproject.toml").read_text(encoding="utf-8"))
    return frozenset(pyproject["project"]["entry-points"])


def _is_module_name(value: str, not_modules: Set[str]) -> bool:
    # A trailing dot is a ``startswith`` prefix for a package's submodules
    # (``"coding_agent_playbook.x."``): it goes stale just like the bare name.
    value = value.removesuffix(".")
    if not _ENGINE_NAME.match(value) or value in not_modules:
        return False
    return not any(value == ns or value.startswith(f"{ns}.") for ns in _OVERLAY_NAMESPACES)


def _equality_sets(tree: ast.Module) -> set[int]:
    compared: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.Eq) for op in node.ops):
            operands = (node.left, *node.comparators)
            compared.update(id(operand) for operand in operands if isinstance(operand, ast.Set))
    return compared


def _startswith_prefix(node: ast.AST) -> ast.AST | None:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return None
    return node.args[0] if node.func.attr == "startswith" and node.args else None


def _positions(tree: ast.Module) -> Iterator[ast.AST | None]:
    """Every expression whose raw engine name would pass vacuously after a move."""
    compared = _equality_sets(tree)
    for statement in tree.body:
        if isinstance(statement, ast.Assign | ast.AnnAssign):
            yield statement.value
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.NotIn) for op in node.ops):
            yield node.left
        if isinstance(node, ast.Set) and id(node) not in compared:
            yield from node.elts
        yield _startswith_prefix(node)


def raw_pins(source: str, path: str, *, not_modules: Set[str] = frozenset()) -> list[RawPin]:
    """The raw engine module names in ``source`` at a position that can pass vacuously.

    Example::

        >>> raw_pins('assert "coding_agent_playbook.hook_runtime.judges.gate_weakening" not in loaded', "t.py")
        [RawPin(path='t.py', line=1, name='coding_agent_playbook.hook_runtime.judges.gate_weakening')]
    """
    strings = [
        (node.lineno, node.value)
        for node in _positions(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    pins = {
        RawPin(path, line, value) for line, value in strings if _is_module_name(value, not_modules)
    }
    return sorted(pins)


def _scan_tests() -> list[RawPin]:
    not_modules = _entry_point_groups()
    found = []
    for path in sorted(_TESTS_ROOT.rglob("*.py")):
        relative = path.relative_to(_TESTS_ROOT).as_posix()
        if relative.startswith("fixtures/") or path == Path(__file__).resolve():
            continue
        source = path.read_text(encoding="utf-8")
        found.extend(raw_pins(source, relative, not_modules=not_modules))
    return found


def test_tests_pin_engine_modules_through_engine_module() -> None:
    assert _scan_tests() == [], "wrap each name in tests.engine_modules.engine_module(...)"


@pytest.mark.parametrize(
    "source",
    [
        'assert "coding_agent_playbook.hook_runtime.judges.gate_weakening" not in loaded',
        '_GATE_SCAN = "coding_agent_playbook.hook_runtime.judges.gate_weakening"',
        'assert not {"yaml", "coding_agent_playbook.hook_runtime.judges.gate_weakening"} & loaded',
        'assert not [m for m in loaded if m.startswith("coding_agent_playbook.hook_runtime.judges.gate_weakening")]',
        '_H = "coding_agent_playbook.hook_runtime.judges.gate_weakening."',
    ],
    ids=["not-in", "module-constant", "set-display", "startswith", "startswith-dotted-prefix"],
)
def test_raw_pins_flags_each_vacuous_spelling(source: str) -> None:
    names = [pin.name.removesuffix(".") for pin in raw_pins(source, "t.py")]

    assert names == ["coding_agent_playbook.hook_runtime.judges.gate_weakening"]


@pytest.mark.parametrize(
    "source",
    [
        '_GATE_SCAN = engine_module("coding_agent_playbook.hook_runtime.judges.gate_weakening")',
        'assert loaded == ["coding_agent_playbook.security", "coding_agent_playbook.security.pii"]',
        'assert engine == {"coding_agent_playbook.hook_runtime"}',
        'assert "coding_agent_playbook.hook_runtime.judges.gate_weakening" in loaded',
        'run_python_probe("import coding_agent_playbook.hook_runtime.judges.gate_weakening")',
    ],
    ids=["wrapped", "equality-list", "equality-set", "positive-in", "probe-code"],
)
def test_raw_pins_accepts_loud_spellings(source: str) -> None:
    assert raw_pins(source, "t.py") == []


def test_raw_pins_skips_names_that_are_not_modules() -> None:
    source = '_GROUP = "coding_agent_playbook.hook_handlers"'

    assert raw_pins(source, "t.py", not_modules={"coding_agent_playbook.hook_handlers"}) == []
