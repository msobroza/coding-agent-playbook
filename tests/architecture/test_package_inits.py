"""A package ``__init__.py`` holds only a docstring (ADR 0002): its interface is its public modules.

Re-exports would give every name two spellings and cost import time on the hook
hot path. The root ``__init__`` is the one exception (the lazy ``__version__``,
tests/unit/test_package_init.py). ``cli/__init__.py`` is the second, permanent one: L2
freezes the console-script target ``coding_agent_playbook.cli:main``, so that init
defines ``main`` and its private error mapping and nothing else
(test_cli_init_defines_main_only). The packages that hold code today are listed in
``_INITS_WITH_CODE``; the move or deepening PR that empties one removes its entry,
and test_inits_with_code_baseline_is_current fails until it does.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

from tests.engine_modules import ENGINE, engine_module

_SRC: Final = Path(__file__).resolve().parents[2] / "src"
_ROOT_INIT: Final = "coding_agent_playbook/__init__.py"
#: L2 (specs/prT-package-layout.md H7): ``coding_agent_playbook.cli:main`` is the
#: frozen console-script target, so ``cli/__init__.py`` holds ``main``; permanent.
_CLI_INIT: Final = "coding_agent_playbook/cli/__init__.py"
_PERMANENT_INITS: Final = frozenset({_ROOT_INIT, _CLI_INIT})
_INITS_WITH_CODE: Final = frozenset(
    {
        "coding_agent_playbook/hook_registrations/__init__.py",
        "coding_agent_playbook/hook_runtime/harness/__init__.py",
    }
)


def holds_only_a_docstring(source: str) -> bool:
    """Whether ``source`` is at most a docstring plus ``from __future__`` imports.

    Example::

        >>> holds_only_a_docstring("'The adapters.'"), holds_only_a_docstring("x = 1")
        (True, False)
    """
    body = ast.parse(source).body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return all(isinstance(s, ast.ImportFrom) and s.module == "__future__" for s in body)


def _inits_with_code() -> set[str]:
    inits = sorted(_SRC.joinpath("coding_agent_playbook").rglob("__init__.py"))
    relative = {path.relative_to(_SRC).as_posix(): path for path in inits}
    return {
        name
        for name, path in relative.items()
        if name not in _PERMANENT_INITS
        and not holds_only_a_docstring(path.read_text(encoding="utf-8"))
    }


def test_package_inits_hold_only_a_docstring() -> None:
    assert sorted(_inits_with_code() - _INITS_WITH_CODE) == []


def test_inits_with_code_baseline_is_current() -> None:
    assert sorted(_INITS_WITH_CODE - _inits_with_code()) == []


def public_definitions(source: str) -> list[str]:
    r"""The non-underscore names ``source`` defines at top level (imports excluded).

    Example::

        >>> public_definitions("import sys\ndef main(): ...\ndef _helper(): ...\nX = 1")
        ['X', 'main']
    """
    names: list[str] = []
    for statement in ast.parse(source).body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.append(statement.name)
        elif isinstance(statement, ast.Assign | ast.AnnAssign):
            names.extend(_bound_names(statement))
    return sorted(name for name in names if not name.startswith("_"))


def _bound_names(statement: ast.Assign | ast.AnnAssign) -> list[str]:
    # Only plain names (and tuple/list unpacking) bind a module attribute;
    # ``x.y = 1`` and ``x[k] = 1`` mutate an existing object.
    targets: list[ast.expr] = (
        list(statement.targets) if isinstance(statement, ast.Assign) else [statement.target]
    )
    names: list[str] = []
    while targets:
        target = targets.pop()
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, ast.Tuple | ast.List):
            targets.extend(target.elts)
    return names


def test_cli_init_defines_main_only() -> None:
    # The L2 exception must not grow into a second parser module (H7).
    source = _SRC.joinpath(_CLI_INIT).read_text(encoding="utf-8")

    assert public_definitions(source) == ["main"]


_CLI_PARSER_MODULE: Final = engine_module(f"{ENGINE}.cli.parser")


def public_imports_from(source: str, module: str) -> list[str]:
    r"""The names ``source`` imports from ``module`` under a non-underscore binding.

    A public binding would make ``cli.<name>`` a second spelling of a
    ``cli.parser`` name, i.e. a re-export (L2/L5), so the cli init must alias
    every parser import private.

    Example::

        >>> public_imports_from("from m import a, b as _b\n", "m")
        ['a']
    """
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            names.extend(alias.asname or alias.name for alias in node.names)
    return sorted(name for name in names if not name.startswith("_"))


def test_cli_init_imports_parser_names_private_only() -> None:
    # public_definitions skips imports, so a re-export of build_parser would pass it.
    source = _SRC.joinpath(_CLI_INIT).read_text(encoding="utf-8")

    assert public_imports_from(source, _CLI_PARSER_MODULE) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from coding_agent_playbook.cli.parser import build_parser\n", ["build_parser"]),
        ("from coding_agent_playbook.cli.parser import build_parser as bp\n", ["bp"]),
        ("from coding_agent_playbook.cli.parser import build_parser as _bp\n", []),
        ("if True:\n    from coding_agent_playbook.cli.parser import _SUBCOMMANDS as s\n", ["s"]),
        ("from coding_agent_playbook.config import ConfigError\n", []),
    ],
)
def test_public_imports_from(source: str, expected: list[str]) -> None:
    assert public_imports_from(source, _CLI_PARSER_MODULE) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import sys\nfrom x import y\n", []),
        ("def main(): ...\ndef _helper(): ...\n", ["main"]),
        ("class Parser: ...\nX: int = 1\n_Y = 2\na, b = 1, 2\n", ["Parser", "X", "a", "b"]),
        ("import os\nos.environ['K'] = 'v'\nos.sep = '/'\n", []),
    ],
)
def test_public_definitions(source: str, expected: list[str]) -> None:
    assert public_definitions(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("", True),
        ('"""Doc."""\nfrom __future__ import annotations\n', True),
        ('"""Doc."""\nfrom .base import Adapter\n', False),
        ("__all__ = []\n", False),
    ],
)
def test_holds_only_a_docstring(source: str, expected: bool) -> None:
    assert holds_only_a_docstring(source) is expected
