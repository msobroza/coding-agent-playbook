"""Shared source coordinates and traversal boundaries for module-move rewrites."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

SKIPPED_DIRECTORIES = frozenset(
    {"fixtures", "__pycache__", ".venv", "build", "dist", "node_modules", "shared_skills"}
)


class SourcePositions:
    """Translate token characters and AST UTF-8 columns; e.g. SourcePositions(source)."""

    def __init__(self, source: str) -> None:
        self.lines = source.splitlines(keepends=True)
        self.offsets = [0]
        for line in self.lines:
            self.offsets.append(self.offsets[-1] + len(line))

    def offset(self, line: int, column: int, *, byte_column: bool = False) -> int:
        """Return a character offset; e.g. offset(1, 0, byte_column=True)."""
        if byte_column:
            column = len(self.lines[line - 1].encode()[:column].decode())
        return self.offsets[line - 1] + column

    def span(self, node: ast.expr | ast.stmt) -> tuple[int, int]:
        """Locate an AST node in the original source; e.g. span(ast.parse(source).body[0])."""
        assert node.end_lineno is not None and node.end_col_offset is not None
        return (
            self.offset(node.lineno, node.col_offset, byte_column=True),
            self.offset(node.end_lineno, node.end_col_offset, byte_column=True),
        )


def docstring_nodes(tree: ast.AST) -> Iterator[ast.Constant]:
    """Yield prose literals for the marker-aware pass; e.g. list(docstring_nodes(ast.parse(s)))."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.body or not isinstance(node.body[0], ast.Expr):
            continue
        literal = node.body[0].value
        if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
            yield literal


def apply_edits(source: str, edits: list[tuple[int, int, str]]) -> str:
    """Apply source spans without shifting later offsets; e.g. apply_edits('old', [(0, 3, 'new')])."""
    for start, end, replacement in sorted(edits, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source


def rewrite_lines(
    source: str, rewrite: Callable[[str], str], *, line_offset: int = 0
) -> tuple[str, list[str]]:
    """Keep diagnostics tied to source lines; e.g. rewrite_lines(text, str.upper)."""
    result, findings = [], []
    for number, line in enumerate(source.splitlines(keepends=True), line_offset + 1):
        rewritten = rewrite(line)
        if rewritten != line:
            findings.append(f"{number}: {line.strip()} -> {rewritten.strip()}")
        result.append(rewritten)
    return "".join(result), findings
