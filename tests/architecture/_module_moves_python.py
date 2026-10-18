"""Python rules of the module-path rewrite script (specs/prT-package-layout.md 5.4.2).

R-IMPORT (import statements, located with ``ast`` and edited as text, so comments
and ``TYPE_CHECKING`` or function-level indentation stay), R-STRING (string
constants that are exactly a stale dotted name, ``module.attr`` or ``module:attr``)
and R-DOC on docstrings and comments. ``python_edits`` only computes edits;
``module_moves`` applies or reports them. Stdlib-only, like ``module_moves``.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from typing import TYPE_CHECKING, Final, NamedTuple, Protocol

from tests.architecture._module_moves_text import Edit, Resolver, colon_or_dotted, prose_edits

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

_EXACT_NAME: Final = re.compile(
    r"^(?:coding_agent_playbook|tests)(?:\.[A-Za-z_]\w*)+(?::[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)?$"
)
_SIMPLE_LITERAL: Final = re.compile(r"^([rRuU]?)([\"'])(.*)\2$", re.DOTALL)
_DOCSTRING_OWNERS: Final = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


class PythonResolver(Resolver, Protocol):
    """A ``Resolver`` that also knows modules and same-name conversions (module_moves)."""

    def conversion(self, name: str) -> str | None:
        """The module a module-object import of ``name`` must now bind, or None (5.4.2)."""

    def is_module(self, name: str) -> bool:
        """Whether ``name`` is a module or package in the working tree."""


class _Target(NamedTuple):
    """Where one imported name of a ``from`` statement comes from after the moves."""

    module: str
    name: str
    asname: str | None


class _Lines:
    """Converts ``ast`` (UTF-8 byte columns) and ``tokenize`` positions to text offsets."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.starts = [0, *(match.end() for match in re.finditer("\n", text))]

    def from_ast(self, line: int, column: int) -> int:
        start = self.starts[line - 1]
        stop = self.starts[line] if line < len(self.starts) else len(self.text)
        prefix = self.text[start:stop].encode("utf-8")[:column]
        return start + len(prefix.decode("utf-8", "replace"))

    def span(self, node: ast.stmt | ast.expr) -> tuple[int, int]:
        if node.end_lineno is None or node.end_col_offset is None:
            raise ValueError(f"line {node.lineno}: ast gave no end position for {ast.dump(node)}")
        start = self.from_ast(node.lineno, node.col_offset)
        return start, self.from_ast(node.end_lineno, node.end_col_offset)


def python_edits(source: str, resolver: PythonResolver) -> list[Edit]:
    """Every edit the Python rules make to ``source``, overlaps dropped (imports win).

    Raises ``SyntaxError`` for unparsable source and ``ValueError`` for a relative
    import, which is refused (the code base has none). Example: with N1 applied,
    ``python_edits("import coding_agent_playbook._toml as t\\n", resolver)`` is one
    edit whose ``new`` is ``"import coding_agent_playbook.toml_writer as t"``.
    """
    tree = ast.parse(source)
    lines = _Lines(source)
    docstrings = _docstrings(tree)
    edits = [
        *_import_edits(tree, lines, resolver),
        *_string_edits(tree, lines, docstrings, resolver),
        *_docstring_edits(docstrings, lines, resolver),
        *_comment_edits(lines, resolver),
    ]
    return without_overlaps(edits)


def without_overlaps(edits: Sequence[Edit]) -> list[Edit]:
    """``edits`` by position, dropping any that overlaps an earlier one.

    An import statement is rewritten whole when split, so a comment edit inside it
    goes. Example: ``without_overlaps([Edit(0, 9, "x"), Edit(4, 6, "y")])`` keeps the first.
    """
    kept: list[Edit] = []
    for edit in sorted(edits, key=lambda edit: (edit.start, edit.end)):
        if not kept or edit.start >= kept[-1].end:
            kept.append(edit)
    return kept


def _import_edits(tree: ast.Module, lines: _Lines, resolver: PythonResolver) -> Iterator[Edit]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            yield from _from_import_edit(node, lines, resolver)
        elif isinstance(node, ast.Import):
            yield from _import_edit(node, lines, resolver)


def _from_import_edit(node: ast.ImportFrom, lines: _Lines, resolver: PythonResolver) -> list[Edit]:
    if node.level:
        statement = f"from {'.' * node.level}{node.module or ''} import ..."
        raise ValueError(
            f"line {node.lineno}: relative import {statement!r} is refused; use an absolute import"
        )
    module = node.module or ""
    targets = [_from_target(module, alias, resolver) for alias in node.names]
    if targets == [_Target(module, alias.name, alias.asname) for alias in node.names]:
        return []
    start, end = lines.span(node)
    if _only_the_module_changes(node, targets):
        return _module_token_edit(lines.text, start, module, targets[0].module)
    return [Edit(start, end, _joiner(lines.text, start).join(_from_statements(targets)))]


def _from_target(module: str, alias: ast.alias, resolver: PythonResolver) -> _Target:
    if alias.name == "*":
        current = resolver.dotted(module)
        return _Target(current if current and resolver.is_module(current) else module, "*", None)
    full, local = f"{module}.{alias.name}", alias.asname or alias.name
    converted = resolver.conversion(full)
    if converted is not None:
        return _module_object(converted, local)
    current = resolver.dotted(full)
    if current is None:
        return _Target(module, alias.name, alias.asname)
    if resolver.is_module(current):
        return _module_object(current, local)
    suffix = f".{alias.name}"
    owner = current.removesuffix(suffix) if current.endswith(suffix) else module
    return _Target(owner, alias.name, alias.asname)


def _module_object(module: str, local: str) -> _Target:
    """``from <parent> import <leaf> as <local>``, so call sites keep their name."""
    parent, _, leaf = module.rpartition(".")
    return _Target(parent, leaf, None if local == leaf else local)


def _only_the_module_changes(node: ast.ImportFrom, targets: Sequence[_Target]) -> bool:
    if len({target.module for target in targets}) != 1:
        return False
    return all(
        (t.name, t.asname) == (a.name, a.asname) for t, a in zip(targets, node.names, strict=True)
    )


def _module_token_edit(text: str, start: int, module: str, new: str) -> list[Edit]:
    """Edit only the module after ``from``, keeping the names, their comments and layout."""
    token = re.compile(r"from\s+" + re.escape(module) + r"\b").match(text, start)
    if token is None:
        raise ValueError(f"offset {start}: expected 'from {module} import' at the statement start")
    return [Edit(token.end() - len(module), token.end(), new)]


def _from_statements(targets: Sequence[_Target]) -> list[str]:
    grouped: dict[str, list[str]] = {}
    for target in targets:
        grouped.setdefault(target.module, []).append(_alias(target.name, target.asname))
    return [f"from {module} import {', '.join(names)}" for module, names in grouped.items()]


def _import_edit(node: ast.Import, lines: _Lines, resolver: PythonResolver) -> list[Edit]:
    pieces = [_import_piece(alias, resolver) for alias in node.names]
    if all(piece is None for piece in pieces):
        return []
    rendered = [
        piece or f"import {_alias(alias.name, alias.asname)}"
        for piece, alias in zip(pieces, node.names, strict=True)
    ]
    start, end = lines.span(node)
    return [Edit(start, end, _joiner(lines.text, start).join(rendered))]


def _import_piece(alias: ast.alias, resolver: PythonResolver) -> str | None:
    converted = resolver.conversion(alias.name) if alias.asname else None
    if converted is not None:
        target = _module_object(converted, alias.asname or alias.name)
        return f"from {target.module} import {_alias(target.name, target.asname)}"
    current = resolver.dotted(alias.name)
    if current is None or not resolver.is_module(current):
        return None
    return f"import {_alias(current, alias.asname)}"


def _alias(name: str, asname: str | None) -> str:
    return name if asname is None else f"{name} as {asname}"


def _joiner(text: str, start: int) -> str:
    """Split statements go on new lines at the statement's indentation, or after ``; ``."""
    indent = text[text.rfind("\n", 0, start) + 1 : start]
    return "\n" + indent if not indent.strip() else "; "


def _docstrings(tree: ast.Module) -> list[ast.Constant]:
    owners = (node for node in ast.walk(tree) if isinstance(node, _DOCSTRING_OWNERS) and node.body)
    return [docstring for node in owners if (docstring := _docstring(node.body[0])) is not None]


def _docstring(first: ast.stmt) -> ast.Constant | None:
    if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
        return None
    return first.value if isinstance(first.value.value, str) else None


def _string_edits(
    tree: ast.Module, lines: _Lines, docstrings: Sequence[ast.Constant], resolver: PythonResolver
) -> list[Edit]:
    # An f-string part is never a whole constant: its text is built at run time (5.4.2).
    skipped = {id(node) for node in docstrings} | _fstring_parts(tree)
    edits = []
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Constant)
            or not isinstance(node.value, str)
            or id(node) in skipped
        ):
            continue
        current = colon_or_dotted(node.value, resolver) if _EXACT_NAME.match(node.value) else None
        if current is not None:
            edits += _literal_edit(node, lines, current)
    return edits


def _fstring_parts(tree: ast.Module) -> set[int]:
    return {
        id(part)
        for node in ast.walk(tree)
        if isinstance(node, ast.JoinedStr)
        for part in ast.walk(node)
    }


def _literal_edit(node: ast.Constant, lines: _Lines, value: str) -> list[Edit]:
    start, end = lines.span(node)
    literal = _SIMPLE_LITERAL.match(lines.text[start:end])
    if literal is None or literal.group(3) != node.value:
        return []  # implicit concatenation, escapes or triple quotes: left to the author
    return [Edit(start + literal.start(3), start + literal.end(3), value)]


def _docstring_edits(
    docstrings: Sequence[ast.Constant], lines: _Lines, resolver: Resolver
) -> list[Edit]:
    edits = []
    for node in docstrings:
        start, end = lines.span(node)
        edits += prose_edits(lines.text[start:end], start, resolver)
    return edits


def _comment_edits(lines: _Lines, resolver: Resolver) -> list[Edit]:
    edits = []
    for token in tokenize.generate_tokens(io.StringIO(lines.text).readline):
        if token.type == tokenize.COMMENT:
            row, column = token.start
            edits += prose_edits(token.string, lines.starts[row - 1] + column, resolver)
    return edits
