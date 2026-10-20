"""The AST passes of the rule-linked lint hooks (specs/prK-hook-pack.md §E.3).

One ``ast.parse`` of the post-edit file per event (memoized by the caller),
never an import or an execution of the edited module (principle 8):

- :func:`public_def_lines`: the signature lines of public functions, so
  typing-lint-feedback reports ``ANN001``/``ANN201`` on the public API only
  (house style: ``_``-prefixed and nested helpers may skip annotations);
- :func:`pytest_ast_heuristics`: pytest-conventions-feedback's opt-in checks
  that no ruff code covers.

``ast`` loads on the Python-edit branch alone (§D.1).
"""

from __future__ import annotations

import ast
from typing import Final

from coding_agent_playbook.hook_runtime.ruff import RuffDiagnostic

__all__ = [
    "ASYNCIO_MARK",
    "LOOP_ASSERT",
    "UNITTEST_CLASS",
    "parse_module",
    "public_def_lines",
    "pytest_ast_heuristics",
]

#: Pseudo-codes of the heuristics: no ruff rule has them, so they never reach D1.
UNITTEST_CLASS: Final = "pytest-unittest-class"
LOOP_ASSERT: Final = "pytest-loop-assert"
ASYNCIO_MARK: Final = "pytest-asyncio-mark"
_FUNCTIONS: Final = (ast.FunctionDef, ast.AsyncFunctionDef)
_TEST_PREFIX: Final = "test_"


def parse_module(text: str) -> ast.Module | None:
    """``text`` parsed, or ``None`` when it does not parse (ruff reports that itself).

    Example::

        >>> parse_module("def f(:") is None
        True
    """
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):  # ValueError: a NUL byte in the source
        return None


def public_def_lines(tree: ast.Module) -> frozenset[int]:
    """The signature lines (``def`` through the line before its body) of every public def.

    Public: a module-level function, or a method of a public class nested only
    in classes, whose name has no leading ``_`` (dunders such as ``__init__``
    are public API). Functions nested in functions are internal.

    Example::

        >>> sorted(public_def_lines(ast.parse("def f(\\n  x):\\n  pass\\ndef _g(y): pass\\n")))
        [1, 2]
    """
    lines: set[int] = set()
    _collect(tree.body, lines)
    return frozenset(lines)


def _collect(body: list[ast.stmt], lines: set[int]) -> None:
    for node in body:
        if isinstance(node, _FUNCTIONS) and _is_public(node.name):
            last = max(node.lineno, node.body[0].lineno - 1)
            lines.update(range(node.lineno, last + 1))
        elif isinstance(node, ast.ClassDef) and _is_public(node.name):
            _collect(node.body, lines)


def _is_public(name: str) -> bool:
    return not name.startswith("_") or (name.startswith("__") and name.endswith("__"))


def pytest_ast_heuristics(
    tree: ast.Module, *, created_this_session: bool, asyncio_marks: bool = False
) -> list[RuffDiagnostic]:
    """pytest-conventions-feedback's opt-in findings, as diagnostics on their own lines.

    (a) a ``unittest.TestCase`` subclass in a file created this session; (b) an
    ``assert`` inside a ``for`` loop of a ``test_*`` function (the caller
    reports it once per file per session); (c) an ``async def test_*`` without
    ``@pytest.mark.asyncio`` when ``asyncio_marks`` (pytest-asyncio installed,
    ``asyncio_mode`` not ``auto``; resolved at sync).

    Example::

        >>> pytest_ast_heuristics(ast.parse("def test_a():\\n  assert 1\\n"),
        ...     created_this_session=False)
        []
    """
    found: list[RuffDiagnostic] = []
    if created_this_session:
        found.extend(_unittest_classes(tree))
    for node in ast.walk(tree):
        if not isinstance(node, _FUNCTIONS) or not node.name.startswith(_TEST_PREFIX):
            continue
        found.extend(_loop_asserts(node))
        if asyncio_marks and isinstance(node, ast.AsyncFunctionDef) and not _marked(node):
            found.append(
                RuffDiagnostic(
                    ASYNCIO_MARK,
                    node.lineno,
                    f"`async def {node.name}` needs `@pytest.mark.asyncio` (pytest-asyncio, "
                    "asyncio_mode is not auto)",
                )
            )
    return sorted(found, key=lambda d: d.row)


def _unittest_classes(tree: ast.Module) -> list[RuffDiagnostic]:
    return [
        RuffDiagnostic(
            UNITTEST_CLASS,
            node.lineno,
            f"`{node.name}` subclasses `unittest.TestCase`; write plain pytest tests instead",
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and any(_is_test_case(base) for base in node.bases)
    ]


def _is_test_case(base: ast.expr) -> bool:
    if isinstance(base, ast.Attribute):
        return base.attr == "TestCase"
    return isinstance(base, ast.Name) and base.id == "TestCase"


def _loop_asserts(test: ast.FunctionDef | ast.AsyncFunctionDef) -> list[RuffDiagnostic]:
    """The first ``assert`` inside a ``for`` loop of ``test``, as one finding."""
    for loop in ast.walk(test):
        if not isinstance(loop, ast.For | ast.AsyncFor):
            continue
        check = next((n for n in ast.walk(loop) if isinstance(n, ast.Assert)), None)
        if check is not None:
            message = "`assert` in a loop: use `@pytest.mark.parametrize` so each case reports"
            return [RuffDiagnostic(LOOP_ASSERT, check.lineno, message)]
    return []


def _marked(node: ast.AsyncFunctionDef) -> bool:
    return any("asyncio" in ast.unparse(decorator) for decorator in node.decorator_list)
