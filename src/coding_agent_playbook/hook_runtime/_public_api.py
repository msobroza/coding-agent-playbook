"""The public API one module source declares, and what another version adds (specs/prK-hook-pack.md §E.2).

tests-with-source-nudge's symbol model: top-level functions and classes, and
the methods of public classes (``Class.method``). Skipped, because no test is
expected for them: ``_private`` and ``__dunder__`` names, ``main``, and
anything decorated ``@abstractmethod`` or ``@override`` (the implementation
or the base is what a test exercises). Stdlib ``ast`` only; a source that does
not parse declares nothing, so the stage fails open.
"""

from __future__ import annotations

import ast
from typing import Final

__all__ = ["new_public_symbols", "public_symbols"]

_SKIPPED_NAMES: Final = frozenset({"main"})
_SKIPPED_DECORATORS: Final = frozenset({"abstractmethod", "override"})
_FUNCTIONS: Final = (ast.FunctionDef, ast.AsyncFunctionDef)
_DEFINITIONS: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
#: What a hostile or unfinished source can raise while parsing.
_PARSE_ERRORS: Final = (SyntaxError, ValueError, RecursionError, MemoryError)


def public_symbols(source: str) -> list[str]:
    """The public symbols ``source`` declares, in order; ``[]`` when it does not parse.

    Example::

        >>> public_symbols("def f(): ...\\nclass C:\\n    def m(self): ...\\n    def _p(self): ...")
        ['f', 'C', 'C.m']
    """
    return _symbols(source) or []


def new_public_symbols(before: str | None, after: str) -> list[str]:
    """The public symbols of ``after`` that ``before`` lacks (``None``: a new file, all of them).

    An unparseable ``before`` yields nothing, so a broken ``HEAD`` never floods the report.

    Example::

        >>> new_public_symbols("def f(): ...", "def f(): ...\\ndef g(): ...")
        ['g']
    """
    known = [] if before is None else _symbols(before)
    if known is None:
        return []
    seen = set(known)
    return [symbol for symbol in public_symbols(after) if symbol not in seen]


def _symbols(source: str) -> list[str] | None:
    """The public symbols of ``source``, or ``None`` when it does not parse."""
    try:
        tree = ast.parse(source)
    except _PARSE_ERRORS:
        return None
    found: list[str] = []
    for node in tree.body:
        if not isinstance(node, _DEFINITIONS) or not _public(node):
            continue
        found.append(node.name)
        if isinstance(node, ast.ClassDef):
            found.extend(
                f"{node.name}.{item.name}"
                for item in node.body
                if isinstance(item, _FUNCTIONS) and _public(item)
            )
    return found


def _public(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> bool:
    return not _skipped_name(node.name) and not _skipped_decorator(node.decorator_list)


def _skipped_name(name: str) -> bool:
    return name.startswith("_") or name in _SKIPPED_NAMES


def _skipped_decorator(decorators: list[ast.expr]) -> bool:
    """``@abstractmethod`` / ``@override``, bare or qualified (``@abc.abstractmethod``)."""
    for decorator in decorators:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name in _SKIPPED_DECORATORS:
            return True
    return False
