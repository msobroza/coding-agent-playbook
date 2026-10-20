"""Replay cumulative module moves: ``python -m tests.architecture.module_moves check``."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from tests.architecture._module_move_common import SKIPPED_DIRECTORIES
from tests.architecture._module_move_docs import (
    bare_reviews,
    migration_section,
    rewrite_prose,
    rewrite_python_prose,
    rewrite_toml,
    rewrite_workflow,
    validate_paths,
)
from tests.architecture._module_move_python import rewrite_python
from tests.architecture._module_move_resolve import Resolver, compose

if TYPE_CHECKING:
    from collections.abc import Callable

# ADR 0002 defines these fixed spellings; map loading must not import the engine
# or resolve them against the checkout that is in the middle of a move.
_FROZEN = frozenset(
    (
        "coding_agent_playbook.hook_runtime",
        "coding_agent_playbook.hook_runtime.cli",
        "coding_agent_playbook.cli",
        "coding_agent_playbook.adapters.base",
    )
)


@dataclass(frozen=True, slots=True)
class ModuleMove:
    """One old dotted module (or package) and its new name."""

    pr: str
    old: str
    new: str
    package: bool = False


@dataclass(frozen=True, slots=True)
class NameMove:
    """Names that leave a module for a split or removed re-export."""

    pr: str
    old: str
    new: str
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PathMove:
    """A doc path that cannot be derived from a module move."""

    pr: str
    old: str
    new: str


@dataclass(frozen=True, slots=True)
class MoveMap:
    """The cumulative map, independent of map-file ordering."""

    modules: tuple[ModuleMove, ...]
    names: tuple[NameMove, ...]
    paths: tuple[PathMove, ...] = ()

    def resolve(self, dotted: str, tree: Path) -> str | None:
        """Return the replacement, or None; e.g. resolve('old.module', repo)."""
        return Resolver(self, tree).resolve(dotted)


def _text(row: dict[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{row!r}: expected a nonempty string for {field}")
    return value


def _frozen_names(map_directory: Path) -> frozenset[str]:
    candidates = [parent / "pyproject.toml" for parent in map_directory.parents]
    candidates.append(Path(__file__).resolve().parents[2] / "pyproject.toml")
    for candidate in candidates:
        if candidate.is_file():
            project = tomllib.loads(candidate.read_text(encoding="utf-8")).get("project", {})
            groups = project.get("entry-points", {})
            if isinstance(groups, dict):
                return _FROZEN | frozenset(groups)
    return _FROZEN


def _validate_destination(move: ModuleMove | NameMove | PathMove, frozen: frozenset[str]) -> None:
    package = isinstance(move, ModuleMove) and move.package
    if not isinstance(move, PathMove) and any(
        move.old == name or (package and name.startswith(move.old + ".")) for name in frozen
    ):
        raise ValueError(f"Frozen name {move.old!r} cannot move")
    if move.old == move.new or (package and move.new.startswith(move.old + ".")):
        raise ValueError(f"Non-idempotent move {move.old!r} -> {move.new!r}")


def _move_keys(move: ModuleMove | NameMove | PathMove) -> list[str]:
    if isinstance(move, NameMove):
        return [f"name:{move.old}.{name}" for name in move.names]
    return [f"{type(move).__name__}:{move.old}"]


def _validate_chains(moves: MoveMap) -> None:
    for module_move in moves.modules:
        compose(module_move.old, moves)
    for name_move in moves.names:
        for name in name_move.names:
            compose(f"{name_move.old}.{name}", moves)
    validate_paths(moves)


def _validate_map(moves: MoveMap, frozen: frozenset[str]) -> None:
    seen: set[str] = set()
    entries: tuple[ModuleMove | NameMove | PathMove, ...] = (
        *moves.modules,
        *moves.names,
        *moves.paths,
    )
    for move in entries:
        _validate_destination(move, frozen)
        for key in _move_keys(move):
            if key in seen:
                raise ValueError(f"Duplicate move for {move.old!r}; expected one destination")
            seen.add(key)
    _validate_chains(moves)


def _package_flag(row: dict[str, object], old: str) -> bool:
    package = row.get("package", False)
    if not isinstance(package, bool):
        raise ValueError(f"{old!r}: expected boolean package, got {package!r}")
    return package


def _name_members(row: dict[str, object], old: str) -> tuple[str, ...]:
    members = row.get("names")
    if (
        not isinstance(members, list)
        or not members
        or not all(isinstance(name, str) and name.isidentifier() for name in members)
    ):
        raise ValueError(f"{old!r}: expected nonempty names list, got {members!r}")
    return tuple(members)


def _parse_move(kind: str, row: dict[str, object]) -> ModuleMove | NameMove | PathMove:
    pr, old, new = (_text(row, key) for key in ("pr", "old", "new"))
    if kind == "module":
        return ModuleMove(pr, old, new, _package_flag(row, old))
    if kind == "path":
        return PathMove(pr, old, new)
    return NameMove(pr, old, new, _name_members(row, old))


def _read_moves(file: Path) -> list[ModuleMove | NameMove | PathMove]:
    entries: list[ModuleMove | NameMove | PathMove] = []
    tables = tomllib.loads(file.read_text(encoding="utf-8"))
    for kind, rows in tables.items():
        if kind not in {"module", "names", "path"} or not isinstance(rows, list):
            raise ValueError(f"{file}: expected [[module]], [[names]] or [[path]], got {kind!r}")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{file}: expected table, got {row!r}")
            entries.append(_parse_move(kind, row))
    return entries


def load_map(path: Path) -> MoveMap:
    """Read the cumulative map; e.g. load_map(repo / 'tests/architecture/move_map')."""
    entries = [move for file in sorted(path.glob("*.toml")) for move in _read_moves(file)]
    moves = MoveMap(
        tuple(move for move in entries if isinstance(move, ModuleMove)),
        tuple(move for move in entries if isinstance(move, NameMove)),
        tuple(move for move in entries if isinstance(move, PathMove)),
    )
    _validate_map(moves, _frozen_names(path))
    return moves


def _owned(path: Path, root: Path) -> bool:
    return not any(
        part.is_symlink() for part in (path, *path.parents) if part != root and root in part.parents
    )


def _python_files(directory: Path) -> list[Path]:
    paths: list[Path] = []
    for parent, directories, names in os.walk(directory):
        directories[:] = [
            name
            for name in directories
            if name not in SKIPPED_DIRECTORIES
            and not name.startswith(".")
            and not (Path(parent) / name).is_symlink()
        ]
        paths.extend(Path(parent) / name for name in names if name.endswith(".py"))
    return paths


def _files(root: Path) -> list[Path]:
    paths = [
        path
        for directory in (root / "src", root / "tests")
        if _owned(directory, root)
        for path in _python_files(directory)
    ]
    paths.extend(
        root / name
        for name in (
            "SPEC.md",
            "README.md",
            "MIGRATION.md",
            "catalog/README.md",
            "pyproject.toml",
            ".github/workflows/ci.yml",
        )
    )
    return sorted(path for path in paths if _owned(path, root) and path.is_file())


def _changes(root: Path, moves: MoveMap) -> list[tuple[Path, str, list[str]]]:
    changes = []
    resolver = Resolver(moves, root)
    for path in _files(root):
        source = path.read_text(encoding="utf-8")
        if path.suffix == ".py":
            rewritten, findings = rewrite_python(source, resolver)
            rewritten, prose_findings = rewrite_python_prose(rewritten, resolver)
            findings.extend(prose_findings)
        elif path.suffix == ".toml":
            rewritten, findings = rewrite_toml(source, resolver)
        elif path.suffix == ".yml":
            rewritten, findings = rewrite_workflow(source, resolver)
        else:
            rewritten, findings = rewrite_prose(source, resolver)
        if path.name == "MIGRATION.md":
            refreshed = migration_section(rewritten, resolver)
            if refreshed != rewritten:
                findings.append("1: stale Module paths section -> regenerate from move map")
            rewritten = refreshed
        findings.extend("review: " + line for line in bare_reviews(source, moves))
        if rewritten != source or findings:
            changes.append((path, rewritten, findings))
    return changes


def _format_paths(paths: list[Path]) -> None:
    paths = [path for path in paths if path.suffix in {".py", ".md"}]
    if not paths:
        return
    for flags in (("check", "--no-cache", "--fix", "--select", "I"), ("format", "--no-cache")):
        subprocess.run(
            [sys.executable, "-m", "ruff", *flags, *map(str, paths)], check=True, timeout=120
        )


def apply(
    repo_root: Path, moves: MoveMap, *, formatter: Callable[[list[Path]], None] = _format_paths
) -> list[Path]:
    """Rewrite mapped files; e.g. apply(repo, load_map(repo / 'tests/architecture/move_map'))."""
    changed = []
    for path, source, _ in _changes(repo_root, moves):
        if path.read_text(encoding="utf-8") == source:
            continue
        path.write_text(source, encoding="utf-8")
        changed.append(path)
    if changed:
        formatter(changed)
    return changed


def check(repo_root: Path, moves: MoveMap) -> list[str]:
    """List stale references without writes; e.g. assert check(repo, moves) == []."""
    return [
        (
            f"review: {path.relative_to(repo_root)}:{line.removeprefix('review: ')}"
            if line.startswith("review: ")
            else f"{path.relative_to(repo_root)}:{line}"
        )
        for path, _, lines in _changes(repo_root, moves)
        for line in lines
    ]


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    """Run the developer command; e.g. main(['check'], root=repo)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("apply", "check"))
    args = parser.parse_args(argv)
    root = root or Path.cwd()
    try:
        moves = load_map(root / "tests/architecture/move_map")
        if args.action == "apply":
            for path in apply(root, moves):
                print(path.relative_to(root))
            return 0
        findings = check(root, moves)
        for line in findings:
            print(line)
        return int(any(not line.startswith("review:") for line in findings))
    except (ValueError, OSError, SyntaxError, subprocess.SubprocessError) as exc:
        print(f"module-moves: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
