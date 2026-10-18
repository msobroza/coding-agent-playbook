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

from tests.architecture._module_moves_text import (
    Edit,
    Resolver,
    applied,
    colon_or_dotted,
    prose_edits,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

_EXACT_NAME: Final = re.compile(
    r"^(?:coding_agent_playbook|tests)(?:\.[A-Za-z_]\w*)+(?::[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)?$"
)
_SIMPLE_LITERAL: Final = re.compile(r"^([rRuU]?)([\"'])(.*)\2$", re.DOTALL)
_DOCSTRING_OWNERS: Final = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
#: How rebuilt statements join when the statement follows other code on its line.
_SAME_LINE: Final = "; "


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


class _Statement(NamedTuple):
    """One import statement to emit: ``head`` plus its names and each name's own comment.

    With no ``names``, ``head`` is the whole statement (a plain ``import``).
    """

    head: str
    names: tuple[tuple[str, str | None], ...] = ()

    def one_line(self) -> str:
        return self.head + ", ".join(name for name, _ in self.names)

    def render(self, shared: Sequence[str], joiner: str) -> str:
        """One line ending in the shared comments, or parenthesised when a name has its own."""
        if all(comment is None for _, comment in self.names):
            return self.one_line() + _suffix(shared)
        body = "".join(f"{joiner}    {name},{_suffix([comment])}" for name, comment in self.names)
        return f"{self.head}({_suffix(shared)}{body}{joiner})"


class _Carried(NamedTuple):
    """The comments of an import statement that its rebuilt statements carry over."""

    #: After ``(``, on a line of their own, or after the statement: every statement gets them.
    shared: tuple[str, ...]
    #: Per alias, the comment on the line where it ends: the statement that receives it gets it.
    by_alias: tuple[str | None, ...]
    #: Where the rewrite ends: past a comment that follows the statement on its last line.
    end: int


class _Lines:
    """Converts ``ast`` (UTF-8 byte columns) and ``tokenize`` positions to text offsets."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.starts = [0, *(match.end() for match in re.finditer("\n", text))]
        #: 1-based line -> (text offset, ``# ...``): a line holds at most one comment.
        self.comments = {
            token.start[0]: (self.starts[token.start[0] - 1] + token.start[1], token.string)
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type == tokenize.COMMENT
        }

    def comment_after(self, line: int, end: int) -> tuple[int, str] | None:
        """The comment of ``line`` that follows offset ``end`` with only blanks between."""
        found = self.comments.get(line)
        if found is None or found[0] < end or self.text[end : found[0]].strip():
            return None
        return found

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
    goes (``_carried`` applies R-DOC to the comments it carries over).
    Example: ``without_overlaps([Edit(0, 9, "x"), Edit(4, 6, "y")])`` keeps the first.
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
    start, _ = lines.span(node)
    if _only_the_module_changes(node, targets):
        return _module_token_edit(lines.text, start, module, targets[0].module)
    carried = _carried(node, lines, resolver)
    old = f"from {module} import {', '.join(_alias(a.name, a.asname) for a in node.names)}"
    return [_rebuilt(lines.text, start, old, _from_statements(targets, carried), carried)]


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


def _from_statements(targets: Sequence[_Target], carried: _Carried) -> list[_Statement]:
    """One ``from`` per destination, in first-seen order; each name keeps its own comment."""
    grouped: dict[str, list[tuple[str, str | None]]] = {}
    for target, comment in zip(targets, carried.by_alias, strict=True):
        grouped.setdefault(target.module, []).append((_alias(target.name, target.asname), comment))
    return [_Statement(f"from {module} import ", tuple(names)) for module, names in grouped.items()]


def _import_edit(node: ast.Import, lines: _Lines, resolver: PythonResolver) -> list[Edit]:
    pieces = [_import_piece(alias, resolver) for alias in node.names]
    if all(piece is None for piece in pieces):
        return []
    statements = [
        _Statement(piece or f"import {_alias(alias.name, alias.asname)}")
        for piece, alias in zip(pieces, node.names, strict=True)
    ]
    start, _ = lines.span(node)
    old = f"import {', '.join(_alias(alias.name, alias.asname) for alias in node.names)}"
    return [_rebuilt(lines.text, start, old, statements, _carried(node, lines, resolver))]


def _carried(node: ast.Import | ast.ImportFrom, lines: _Lines, resolver: Resolver) -> _Carried:
    """The comments a rebuilt statement keeps (5.4.2: imports are edited so comments stay).

    A split once dropped every comment inside the statement, ``# noqa`` pragmas
    included, and kept a trailing one on the last statement only (review of #152).
    A comment on a line where aliases end belongs to each of them; any other one is shared.
    """
    _, end = lines.span(node)
    last = node.end_lineno or node.lineno
    # A comment runs to the end of its line, so one inside the span sits before ``last``.
    inside = {
        row: _current_comment(lines.comments[row][1], resolver)
        for row in range(node.lineno, last)
        if row in lines.comments
    }
    alias_rows = {alias.end_lineno for alias in node.names}
    shared = [comment for row, comment in inside.items() if row not in alias_rows]
    after = lines.comment_after(last, end)
    if after is not None:
        shared.append(_current_comment(after[1], resolver))
        end = after[0] + len(after[1])
    by_alias = tuple(inside.get(alias.end_lineno or 0) for alias in node.names)
    return _Carried(tuple(dict.fromkeys(shared)), by_alias, end)


def _current_comment(comment: str, resolver: Resolver) -> str:
    """R-DOC on a carried comment: the rebuilt statement overlaps, and so drops, its own edit."""
    return applied(comment, without_overlaps(prose_edits(comment, 0, resolver)))


def _rebuilt(
    text: str, start: int, old: str, statements: Sequence[_Statement], carried: _Carried
) -> Edit:
    """The edit that replaces a statement (and its trailing comment) with ``statements``.

    ``check`` prints the label: both sides on one line, without the comments.
    """
    new = _SAME_LINE.join(statement.one_line() for statement in statements)
    joined = _emitted(statements, carried.shared, _joiner(text, start))
    return Edit(start, carried.end, joined, label=f"{old} -> {new}")


def _emitted(statements: Sequence[_Statement], shared: Sequence[str], joiner: str) -> str:
    """The statements, each carrying the shared comments, joined by ``joiner``.

    After other code on its line, a comment would swallow the statements after it,
    so every comment goes once at the end of the line instead.
    """
    if joiner != _SAME_LINE:
        return joiner.join(statement.render(shared, joiner) for statement in statements)
    own = (comment for statement in statements for _, comment in statement.names)
    every = dict.fromkeys(comment for comment in (*shared, *own) if comment is not None)
    return _SAME_LINE.join(statement.one_line() for statement in statements) + _suffix(every)


def _suffix(comments: Iterable[str | None]) -> str:
    return "".join(f"  {comment}" for comment in comments if comment is not None)


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
    return "\n" + indent if not indent.strip() else _SAME_LINE


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
    return [
        edit
        for offset, comment in lines.comments.values()
        for edit in prose_edits(comment, offset, resolver)
    ]
