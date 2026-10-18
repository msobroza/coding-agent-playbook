"""The files the module-path rewrite script opens, and its edits to each (specs/prT-package-layout.md 5.4.2-5.4.3).

``rewrites`` walks every file a rule covers, minus what 5.4.3 never opens, picks the
rules by file kind and returns each file's edits and ``review:`` lines;
``module_moves.apply`` writes the edits and ``module_moves.check`` reports them.
Stdlib-only, like ``module_moves``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from tests.architecture._module_moves_python import python_edits, without_overlaps
from tests.architecture._module_moves_text import (
    SECTION_START,
    Edit,
    bare_name_reviews,
    line_regions,
    markdown_edits,
    migration_edits,
    split_lines,
    toml_edits,
    workflow_edits,
)
from tests.architecture._module_moves_tree import ENGINE, module_source

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.architecture.module_moves import MoveMap

_DOC_FILES: Final = ("SPEC.md", "README.md", "MIGRATION.md", "catalog/README.md")
_WORKFLOW_FILE: Final = ".github/workflows/ci.yml"
_PYPROJECT: Final = "pyproject.toml"
#: Never opened (5.4.3): bytecode and the harness directories. specs/, docs/adr/,
#: CONTEXT.md, catalog/** and the root harness files are never listed to begin with.
_NEVER_OPENED_DIRS: Final = frozenset(
    {"__pycache__", ".claude", ".opencode", ".agents", "shared_skills"}
)
#: Never opened: the test fixtures (5.4.3) and the move map.
_NEVER_OPENED_PATHS: Final = frozenset({"tests/fixtures", "tests/architecture/move_map"})
#: Never opened either: the script, its helpers, its samples and its tests
#: (``tests/architecture/*module_moves*.py``), which name old paths on purpose and
#: would otherwise rewrite themselves.
_SCRIPT_DIR: Final = "tests/architecture"
_SCRIPT_STEM: Final = "module_moves"

Rows = list[tuple[str, str, str]]


@dataclass(frozen=True, slots=True)
class FileRewrite:
    """One opened file: its text, the edits the rules make to it, and its ``review:`` lines."""

    path: Path
    text: str
    edits: tuple[Edit, ...]
    reviews: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _TreeResolver:
    """The rules' view of the map and one working tree (a ``PythonResolver``)."""

    moves: MoveMap
    tree: Path

    def dotted(self, name: str) -> str | None:
        return self.moves.resolve(name, self.tree)

    def path(self, path: str) -> str | None:
        return self.moves.resolve_path(path, self.tree)

    def conversion(self, name: str) -> str | None:
        return self.moves.conversion(name, self.tree)

    def is_module(self, name: str) -> bool:
        return module_source(name, self.tree) is not None


def rewrites(repo_root: Path, moves: MoveMap) -> Iterator[FileRewrite]:
    """Each opened file that may name an old path, with its edits; nothing for an empty map.

    Example: ``[r.path for r in rewrites(repo, moves) if r.edits]`` is what ``apply`` writes.
    """
    needles = moves.needles()
    if not needles:
        return
    resolver = _TreeResolver(moves, repo_root)
    rows = migration_rows(moves, repo_root)
    for path in opened_files(repo_root):
        text = path.read_bytes().decode("utf-8")
        relative = path.relative_to(repo_root).as_posix()
        if relative == "MIGRATION.md" or any(needle in text for needle in needles):
            edits, reviews = _file_edits(relative, text, resolver, rows)
            yield FileRewrite(path, text, tuple(without_overlaps(edits)), tuple(reviews))


def opened_files(repo_root: Path) -> Iterator[Path]:
    """Every file a rule covers (5.4.2), minus what 5.4.3 never opens, in a stable order.

    Example: ``next(opened_files(repo))`` is ``repo / "SPEC.md"``; ``tests/fixtures/``
    and this script's own files never appear.
    """
    for name in (*_DOC_FILES, _WORKFLOW_FILE, _PYPROJECT):
        if (repo_root / name).is_file():
            yield repo_root / name
    for top in ("src", "tests"):
        for directory, subdirs, files in os.walk(repo_root / top):
            here = Path(directory)
            subdirs[:] = sorted(
                name for name in subdirs if not _never_opened(repo_root, here / name)
            )
            paths = (here / name for name in sorted(files) if name.endswith(".py"))
            yield from (path for path in paths if not _never_opened(repo_root, path))


def _never_opened(repo_root: Path, path: Path) -> bool:
    if path.name in _NEVER_OPENED_DIRS or path.name.endswith(".egg-info"):
        return True
    relative = path.relative_to(repo_root)
    if relative.parent.as_posix() == _SCRIPT_DIR and _SCRIPT_STEM in relative.name:
        return True
    return relative.as_posix() in _NEVER_OPENED_PATHS


def _file_edits(
    relative: str, text: str, resolver: _TreeResolver, rows: Rows
) -> tuple[list[Edit], list[str]]:
    try:
        if relative.endswith(".py"):
            return _python_file(text, resolver)
        if relative == _PYPROJECT:
            return toml_edits(text, resolver), []
        if relative == _WORKFLOW_FILE:
            return workflow_edits(text, resolver), []
        return _doc_file(relative, text, resolver, rows)
    except ValueError as error:
        raise ValueError(f"{relative}: {error}") from error


def _python_file(text: str, resolver: _TreeResolver) -> tuple[list[Edit], list[str]]:
    reviews = bare_name_reviews(split_lines(text), resolver.moves.bare_root_names())
    try:
        return python_edits(text, resolver), reviews
    except SyntaxError as error:
        return [], [
            *reviews,
            f"{error.lineno or 1}: not parsed as Python ({error.msg}); not checked",
        ]


def _doc_file(
    relative: str, text: str, resolver: _TreeResolver, rows: Rows
) -> tuple[list[Edit], list[str]]:
    prose = [line for line in line_regions(text) if line.region == "doc"]
    edits = markdown_edits(text, resolver)
    reviews = bare_name_reviews(prose, resolver.moves.bare_root_names())
    if relative == "MIGRATION.md":
        edits += migration_edits(text, rows)
        if rows and SECTION_START not in text:
            reviews.append(
                f"1: no {SECTION_START} section to list the {len(rows)} public module moves in"
            )
    return edits, reviews


def migration_rows(moves: MoveMap, tree: Path) -> Rows:
    """``(old, current new, PR)`` for every move of a public engine module or name (R-MIGRATION).

    Only an old public path gets a row (5.3.8: the section is for out-of-tree code,
    which never imports an underscore module), so N1's ``_toml`` -> ``toml_writer``
    is not listed, and ``tests.*`` moves never are. Example: with N2's
    ``config`` -> ``config.model`` alone, ``migration_rows(moves, repo)`` is
    ``[("coding_agent_playbook.config", "coding_agent_playbook.config.model", "N2")]``.
    """

    def final(dotted: str) -> str:
        return moves.resolve(dotted, tree) or dotted

    rows = [
        (entry.old, final(entry.new), entry.pr)
        for entry in moves.modules
        if _is_public_engine(entry.old)
    ]
    rows += [
        (f"{entry.old}.{name}", final(f"{entry.new}.{name}"), entry.pr)
        for entry in moves.names
        for name in entry.names
        if _is_public_engine(f"{entry.old}.{name}")
    ]
    return sorted(rows)


def _is_public_engine(dotted: str) -> bool:
    parts = dotted.split(".")
    return parts[0] == ENGINE and not any(part.startswith("_") for part in parts)


def shown(text: str, edit: Edit) -> str:
    """How ``check`` prints one edit: ``<line>: <label>``, or ``<line>: old -> new`` on one line.

    The statements of a split import are joined with ``; ``, as one line of Python.
    Example: ``shown("import a", Edit(7, 8, "b"))`` is ``"1: a -> b"``.
    """
    line = text.count("\n", 0, edit.start) + 1
    if edit.label is not None:
        return f"{line}: {edit.label}"
    old = " ".join(text[edit.start : edit.end].split())
    new = "; ".join(" ".join(part.split()) for part in edit.new.split("\n") if part.strip())
    return f"{line}: {old} -> {new}"
