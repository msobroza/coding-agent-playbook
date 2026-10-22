"""Helpers shared by ``detect_smells.py`` and ``lcom4_clusters.py``; not run on its own.

Standard library only, Python 3.10 or later, like the scripts that import it.
Each script puts its own directory on ``sys.path`` before importing this module,
so both still run standalone from any working directory. Keeping these helpers
in one place keeps the two scripts agreeing on what a stub method is, which
files a directory scan visits and when a path cannot be read.
"""

from __future__ import annotations

import ast
import os
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

SKIPPED_DIR_NAMES = frozenset({"__pycache__", "venv", ".venv", "node_modules", "site-packages"})
FUNCTION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


# --- AST helpers -------------------------------------------------------------------------


def simple_name(node: ast.expr | None) -> str:
    """Last dotted component of a name: ``abc.ABC`` -> ``ABC``, ``Base[T]`` -> ``Base``.

    Anything that is not a plain or dotted name yields ``""``.
    """
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else ""


def is_dunder(name: str) -> bool:
    """True for ``__name__``-style names."""
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def receiver_of(fn: FunctionNode) -> str | None:
    """Name of the first positional parameter (``self`` by convention), if any."""
    positional = fn.args.posonlyargs + fn.args.args
    return positional[0].arg if positional else None


def is_string_statement(stmt: ast.stmt) -> bool:
    """True for a statement that is only a string literal (a docstring)."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def is_ellipsis(stmt: ast.stmt) -> bool:
    """True for a bare ``...`` statement."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
    )


def without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """``body`` minus a leading docstring expression."""
    return body[1:] if body and is_string_statement(body[0]) else body


def is_stub_statement(stmt: ast.stmt) -> bool:
    """``pass``, ``...`` or ``raise NotImplementedError``: a placeholder, not behaviour."""
    if isinstance(stmt, ast.Raise):
        return simple_name(stmt.exc) == "NotImplementedError"
    return isinstance(stmt, ast.Pass) or is_ellipsis(stmt)


def is_stub_body(body: list[ast.stmt]) -> bool:
    """True when a body only documents or refuses (docstring, pass, ..., NotImplementedError).

    >>> is_stub_body(ast.parse('"Docs."\\n...').body)
    True
    >>> is_stub_body(ast.parse("0").body)
    False
    """
    return all(is_stub_statement(stmt) for stmt in without_docstring(body))


# --- files -------------------------------------------------------------------------------


def iter_python_files(paths: Sequence[Path]) -> Iterator[Path]:
    """Files named explicitly, plus every ``*.py`` under each directory."""
    for path in paths:
        if path.is_dir():
            yield from walk_python_files(path)
        else:
            yield path


def walk_python_files(root: Path) -> Iterator[Path]:
    """``*.py`` files under ``root`` in sorted order, skipping tool and vendor directories."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and d not in SKIPPED_DIR_NAMES
        )
        yield from (Path(dirpath) / name for name in sorted(filenames) if name.endswith(".py"))


def parse_module(path: Path, prog: str) -> ast.Module | None:
    """Parse one file, or report it on stderr under ``prog`` and return None."""
    try:
        source = path.read_bytes()
        with warnings.catch_warnings():  # the scanned code's own warnings are not ours to print
            warnings.simplefilter("ignore")
            return ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, ValueError, RecursionError) as error:
        print(f"{prog}: skipped {path}: {error}", file=sys.stderr)
        return None


def load_modules(paths: Sequence[Path], prog: str) -> list[tuple[str, ast.Module]]:
    """(display path, tree) for every parseable file, de-duplicated and sorted."""
    files = sorted({path.as_posix(): path for path in iter_python_files(paths)}.items())
    parsed = [(name, parse_module(path, prog)) for name, path in files]
    return [(name, tree) for name, tree in parsed if tree is not None]


def path_problem(path: Path) -> str | None:
    """Why ``path`` cannot be scanned, or None when it can."""
    if not path.exists():
        return f"no such file or directory: {path}"
    mode = os.R_OK | (os.X_OK if path.is_dir() else 0)
    return None if os.access(path, mode) else f"cannot read: {path}"


def report_unreadable(paths: Sequence[Path], prog: str) -> bool:
    """Print the first path that cannot be scanned on stderr; True when there was one."""
    problems = [problem for problem in map(path_problem, paths) if problem]
    if problems:
        print(f"{prog}: error: {problems[0]}", file=sys.stderr)
    return bool(problems)
