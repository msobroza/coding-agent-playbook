"""Resolve move chains against source files without importing the engine."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from tests.architecture._module_move_common import SKIPPED_DIRECTORIES

if TYPE_CHECKING:
    from pathlib import Path

    from tests.architecture.module_moves import MoveMap


def _conversion_destination(dotted: str, old: str, new: str, moves: MoveMap) -> bool:
    if not new.startswith(old + "."):
        return False
    destinations = [new, *(move.new for move in moves.modules), *(move.new for move in moves.names)]
    # A later move can rename the implementation inside the same new package.
    return any(
        destination.startswith(old + ".")
        and (dotted == destination or dotted.startswith(destination + "."))
        for destination in destinations
    )


def mapped_name(dotted: str, moves: MoveMap) -> str | None:
    """Choose the longest mapped prefix; e.g. mapped_name('old.module.Member', moves)."""
    candidates = [(move.old, move.new) for move in moves.modules]
    candidates += [
        (f"{move.old}.{name}", f"{move.new}.{name}") for move in moves.names for name in move.names
    ]
    for old, new in sorted(candidates, key=lambda pair: len(pair[0]), reverse=True):
        if _conversion_destination(dotted, old, new, moves):
            continue
        if dotted == old or dotted.startswith(old + "."):
            return new + dotted[len(old) :]
    return None


def compose(dotted: str, moves: MoveMap) -> str:
    """Follow an acyclic map to its final spelling; e.g. compose('old.module', moves)."""
    for move in moves.modules:
        if move.old == move.new or (move.package and move.new.startswith(move.old + ".")):
            raise ValueError(f"Non-idempotent move {move.old!r} -> {move.new!r}")
    seen: set[str] = set()
    for _ in range(2 * (len(moves.modules) + len(moves.names)) + 2):
        if dotted in seen:
            break
        seen.add(dotted)
        replacement = mapped_name(dotted, moves)
        if replacement is None:
            return dotted
        dotted = replacement
    raise ValueError(f"Non-idempotent move chain at {dotted!r}; expected an acyclic map")


def _bindings(statements: list[ast.stmt]) -> set[str]:
    names: set[str] = set()
    pending: list[ast.AST] = list(statements)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
            continue
        if isinstance(
            node, ast.Lambda | ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
        ):
            continue
        if isinstance(node, ast.Import | ast.ImportFrom):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        if isinstance(node, ast.MatchAs | ast.MatchStar) and node.name:
            names.add(node.name)
        if isinstance(node, ast.MatchMapping) and node.rest:
            names.add(node.rest)
        # Except handlers and match cases wrap statements without introducing scopes.
        pending.extend(ast.iter_child_nodes(node))
    return names


def _safe_source(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    if root.is_symlink() or parts[0] == "catalog" or parts[:2] == ("docs", "adr"):
        return False
    current = root
    for part in parts:
        if part.startswith(".") or part in SKIPPED_DIRECTORIES:
            return False
        current /= part
        if current.is_symlink():
            return False
    return path.is_file()


class Resolver:
    """A per-run AST cache; e.g. Resolver(moves, repo).resolve('old.module')."""

    def __init__(self, moves: MoveMap, root: Path) -> None:
        self.moves = moves
        self.root = root
        self.exports: dict[Path, set[str]] = {}

    def module_file(self, dotted: str) -> Path | None:
        """Locate a source module without executing it; e.g. module_file('pkg.mod')."""
        parts = dotted.split(".")
        if not all(part.isidentifier() for part in parts):
            return None
        for base in (self.root / "src", self.root):
            stem = base.joinpath(*parts)
            for path in (stem / "__init__.py", stem.with_suffix(".py")):
                if _safe_source(path, self.root):
                    return path
        return None

    def current(self, dotted: str) -> bool:
        """Check module-level names; e.g. current('pkg.module.Config')."""
        parts = dotted.split(".")
        for size in range(len(parts), 0, -1):
            path = self.module_file(".".join(parts[:size]))
            if path is None:
                continue
            if size == len(parts):
                return True
            if path not in self.exports:
                self.exports[path] = _bindings(ast.parse(path.read_text(encoding="utf-8")).body)
            return parts[size] in self.exports[path]
        return False

    def resolve(self, dotted: str) -> str | None:
        """Return a replacement only for stale names; e.g. resolve('old.mod.attr')."""
        if mapped_name(dotted, self.moves) is None or self.current(dotted):
            return None
        result = compose(dotted, self.moves)
        return result if result != dotted else None

    def module_object(self, dotted: str) -> str | None:
        """Retarget former modules now holding only a package; e.g. module_object('pkg.config')."""
        path = self.module_file(dotted)
        for move in self.moves.modules:
            if (
                move.old == dotted
                and path
                and path.name == "__init__.py"
                and move.new.startswith(dotted + ".")
            ):
                return compose(move.new, self.moves)
        return self.resolve(dotted)
