"""A package ``__init__.py`` holds only a docstring (ADR 0002): its interface is its public modules.

Re-exports would give every name two spellings and cost import time on the hook
hot path. The root ``__init__`` is the one exception (the lazy ``__version__``,
tests/unit/test_package_init.py). The packages that hold code today are listed in
``_INITS_WITH_CODE``; the move or deepening PR that empties one removes its entry,
and test_inits_with_code_baseline_is_current fails until it does.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

_SRC: Final = Path(__file__).resolve().parents[2] / "src"
_ROOT_INIT: Final = "coding_agent_playbook/__init__.py"
_INITS_WITH_CODE: Final = frozenset(
    {
        "coding_agent_playbook/evals/__init__.py",
        "coding_agent_playbook/evaluators/__init__.py",
        "coding_agent_playbook/evaluators/builtins/__init__.py",
        "coding_agent_playbook/evaluators/checks/__init__.py",
        "coding_agent_playbook/evaluators/execution/__init__.py",
        "coding_agent_playbook/hook_policy/__init__.py",
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
        if name != _ROOT_INIT and not holds_only_a_docstring(path.read_text(encoding="utf-8"))
    }


def test_package_inits_hold_only_a_docstring() -> None:
    assert sorted(_inits_with_code() - _INITS_WITH_CODE) == []


def test_inits_with_code_baseline_is_current() -> None:
    assert sorted(_INITS_WITH_CODE - _inits_with_code()) == []


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
