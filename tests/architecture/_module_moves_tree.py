"""Working-tree queries of the module-path rewrite script (specs/prT-package-layout.md 5.4.2).

A dotted name is **current** when its longest module prefix resolves to a module or
package in the working tree and the remainder is a name that module's source binds
at top level (read with ``ast``). This module answers that, and "is it a module, a
package, an existing path". Stdlib-only, like ``module_moves``.
"""

from __future__ import annotations

import ast
import os
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path

ENGINE: Final = "coding_agent_playbook"
_COMPOUND: Final = (ast.If, ast.Try, ast.TryStar, ast.With, ast.For, ast.While)
_NAMES_CACHE: dict[tuple[Path, int, int], frozenset[str]] = {}
#: Directories Python writes next to sources and git does not track. A checkout or
#: rebase that removes a package's tracked files leaves them, and so the package
#: directory, on disk; a fresh clone has neither.
_UNTRACKED_DIRS: Final = frozenset({"__pycache__"})


def module_path(dotted: str, package: bool) -> str:
    """The repo-relative file (or directory, for a package) of a dotted name.

    Example: ``module_path("coding_agent_playbook.harness", True)`` -> ``"src/coding_agent_playbook/harness/"``.
    """
    parts = dotted.split(".")
    base = f"src/{'/'.join(parts)}" if parts[0] == ENGINE else "/".join(parts)
    return f"{base}/" if package else f"{base}.py"


def module_source(dotted: str, tree: Path) -> Path | None:
    """The file Python would import for ``dotted`` (a directory for a namespace package).

    A regular package wins over a same-name module, as in Python's own finder. A
    directory without a file outside ``__pycache__/`` is no namespace package: a fresh
    clone does not have it (``holds_files``).
    Example: ``module_source("coding_agent_playbook.cli", repo)`` -> ``repo/src/coding_agent_playbook/cli.py``.
    """
    parts = dotted.split(".")
    if parts[0] not in (ENGINE, "tests"):
        return None
    base = tree / "src" if parts[0] == ENGINE else tree
    path = base.joinpath(*parts)
    for candidate in (path / "__init__.py", path.with_name(f"{parts[-1]}.py")):
        if candidate.is_file() and spelled_exactly(candidate, base):
            return candidate
    return path if holds_files(path) and spelled_exactly(path, base) else None


def is_package(dotted: str, tree: Path) -> bool:
    """Whether ``dotted`` is a package (regular or namespace) in the working tree.

    Example: after N3, ``is_package("coding_agent_playbook.catalog", repo)`` is True.
    """
    source = module_source(dotted, tree)
    return source is not None and (source.is_dir() or source.name == "__init__.py")


def is_current(dotted: str, tree: Path) -> bool:
    """Whether the working tree defines ``dotted`` (a module, or ``module.attr``).

    Example: after N2, ``is_current("coding_agent_playbook.config.schema", repo)`` is
    True and ``is_current("coding_agent_playbook.config.Config", repo)`` is False.
    """
    parts = dotted.split(".")
    for cut in range(len(parts), 0, -1):
        source = module_source(".".join(parts[:cut]), tree)
        if source is not None:
            return cut == len(parts) or parts[cut] in defined_names(source)
    return False


def path_exists(path: str, tree: Path) -> bool:
    """Whether a repo-relative path exists; a trailing ``/`` asks for a directory.

    A directory counts only when it ``holds_files``, as in a fresh clone.
    Example: ``path_exists("tests/hooks/", repo)`` is False once A13 has moved them.
    """
    target = tree / path
    found = holds_files(target) if target.is_dir() else target.is_file() and not path.endswith("/")
    return found and spelled_exactly(target, tree)


def holds_files(directory: Path) -> bool:
    """Whether ``directory`` holds a file, at any depth, outside ``__pycache__/``.

    git leaves a moved package's directory on disk when a checkout or rebase removes
    its tracked files, because the untracked ``__pycache__/`` stays. Counted as a
    namespace package, it made the old names look current: ``check`` passed locally and
    failed in CI's fresh clone, and ``apply`` left them stale (review of #152).
    Example: after N12, ``holds_files(repo / "src/coding_agent_playbook/harness")`` is
    False even with ``harness/__pycache__/`` still on disk.
    """
    for _, subdirs, files in os.walk(directory):
        if files:
            return True
        subdirs[:] = [name for name in subdirs if name not in _UNTRACKED_DIRS]
    return False


def spelled_exactly(path: Path, base: Path) -> bool:
    """Whether every part of ``path`` below ``base`` has the case its directory lists.

    A case-insensitive file system (macOS APFS, Windows NTFS) finds ``detector/Facts.py``
    when only ``detector/facts.py`` exists, which made the class ``detector.Facts`` look
    like a current submodule, so its stale imports were never rewritten.
    Example: ``spelled_exactly(repo / "src/coding_agent_playbook/Detector", repo)`` is False.
    """
    directory = base
    for part in path.relative_to(base).parts:
        if part not in os.listdir(directory):
            return False
        directory = directory / part
    return True


def defined_names(source: Path) -> frozenset[str]:
    """The top-level names a module binds, read with ``ast`` (cached per file version).

    Imports count (``orchestrator.detect`` is current while orchestrator imports it),
    and so do names bound under ``if TYPE_CHECKING:`` or ``try:`` at top level.
    Example: ``"detect" in defined_names(repo / "src/coding_agent_playbook/orchestrator.py")``.
    """
    if source.is_dir():
        return frozenset()
    stat = source.stat()
    key = (source, stat.st_mtime_ns, stat.st_size)
    if key not in _NAMES_CACHE:
        try:
            body = ast.parse(source.read_bytes()).body
        except SyntaxError:
            body = []
        _NAMES_CACHE[key] = frozenset(_bound_names(body))
    return _NAMES_CACHE[key]


def _bound_names(body: Sequence[ast.stmt]) -> Iterator[str]:
    for statement in body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            yield statement.name
        elif isinstance(statement, ast.Assign):
            yield from (name for target in statement.targets for name in _target_names(target))
        elif isinstance(statement, ast.AnnAssign | ast.AugAssign):
            yield from _target_names(statement.target)
        elif isinstance(statement, ast.TypeAlias):
            yield from _target_names(statement.name)
        elif isinstance(statement, ast.Import | ast.ImportFrom):
            yield from (
                _bound_alias(alias, statement) for alias in statement.names if alias.name != "*"
            )
        elif isinstance(statement, _COMPOUND):
            yield from _bound_names(list(_nested_statements(statement)))


def _bound_alias(alias: ast.alias, statement: ast.Import | ast.ImportFrom) -> str:
    if alias.asname is not None:
        return alias.asname
    return alias.name.split(".")[0] if isinstance(statement, ast.Import) else alias.name


def _nested_statements(statement: ast.stmt) -> Iterator[ast.stmt]:
    """The statements of a top-level compound statement (``if TYPE_CHECKING:``, ``try:`` ...)."""
    for name in ("body", "orelse", "finalbody"):
        yield from getattr(statement, name, [])
    for handler in getattr(statement, "handlers", []):
        yield from handler.body


def _target_names(target: ast.expr) -> Iterator[str]:
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, ast.Tuple | ast.List):
        for element in target.elts:
            yield from _target_names(element)
    elif isinstance(target, ast.Starred):
        yield from _target_names(target.value)
