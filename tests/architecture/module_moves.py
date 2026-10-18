"""The module-path rewrite script of the flat package layout (specs/prT-package-layout.md 5.4).

Every move PR, and every chain ticket that rebases onto a move, runs it from the
repository root::

    python -m tests.architecture.module_moves apply   # rewrite the working tree
    python -m tests.architecture.module_moves check   # list stale references (exit 1)

The move map is one TOML file per move PR in ``tests/architecture/move_map/``, with
``[[module]]`` (``pr``, ``old``, ``new``, optional ``package``), ``[[names]]`` (``pr``,
``old``, ``new``, ``names``) and ``[[path]]`` (``pr``, ``old``, ``new``; relative to
``src/coding_agent_playbook/`` unless it starts with ``tests/``) arrays. Entries are
never removed, so a branch written against any older layout is rewritten in one
``apply``. A name is rewritten only when it is stale (the working tree does not
define it) and the composed map gives a current spelling, which makes every rule
idempotent. Stdlib-only, like its ``_module_moves_*`` helpers, so it runs before any
install and on a branch in the middle of a rebase.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from tests.architecture._module_moves_files import rewrites, shown
from tests.architecture._module_moves_format import run_ruff
from tests.architecture._module_moves_text import applied
from tests.architecture._module_moves_tree import (
    ENGINE,
    is_current,
    is_package,
    module_path,
    path_exists,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    Formatter = Callable[[Path, Sequence[Path]], None]
    _Step = Callable[[str, set[object]], tuple[object, str] | None]

MAP_DIR: Final = Path("tests/architecture/move_map")
#: The entry-point group names of pyproject.toml, which L2 freezes (pinned by
#: test_entry_point_groups_match_pyproject).
ENTRY_POINT_GROUPS: Final = (
    "adapters",
    "artifact_sources",
    "checks",
    "gates",
    "hook_handlers",
    "judges",
    "metrics",
    "overlays",
    "rubrics",
    "runners",
    "state_sources",
)
#: L2's external contract (5.4.3): no [[module]] entry renames one of these, or a
#: package that contains one.
FROZEN_MODULES: Final = (
    *(f"{ENGINE}.{name}" for name in ("hook_runtime", "hook_runtime.cli", "cli", "adapters.base")),
    *(f"{ENGINE}.{group}" for group in ENTRY_POINT_GROUPS),
)
#: The console-script targets ``cli:main`` and ``hook_runtime.cli:main``.
_FROZEN_ATTRIBUTES: Final = ((f"{ENGINE}.cli", "main"), (f"{ENGINE}.hook_runtime.cli", "main"))
_FROZEN_PATHS: Final = tuple(
    f"src/{ENGINE}/{path}" for path in ("hook_runtime/", "hook_runtime/cli.py", "adapters/base.py")
)
#: Overlay labels that look like modules but are not (5.4.3).
_NOT_MODULES: Final = (f"{ENGINE}.plugins", f"{ENGINE}.packs")
_DOTTED_NAME: Final = re.compile(rf"^(?:{ENGINE}|tests)(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
_RELATIVE_PATH: Final = re.compile(r"^[A-Za-z0-9_-][\w.-]*(?:/[A-Za-z0-9_-][\w.-]*)*/?$")
_IDENTIFIER: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: The required and the optional keys of each entry kind of a map file.
_ENTRY_KEYS: Final = {
    "module": ({"pr", "old", "new"}, {"package"}),
    "names": ({"pr", "old", "new", "names"}, set[str]()),
    "path": ({"pr", "old", "new"}, set[str]()),
}
APPLY_HINT: Final = "fix: python -m tests.architecture.module_moves apply"


@dataclass(frozen=True, slots=True)
class ModuleMove:
    """One old dotted module (or package, with ``package=True``) and its new name."""

    pr: str
    old: str
    new: str
    package: bool = False


@dataclass(frozen=True, slots=True)
class NameMove:
    """Names that leave ``old`` for ``new``: a split, or a removed re-export."""

    pr: str
    old: str
    new: str
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PathMove:
    """A doc path and its new spelling, repo-relative (``src/coding_agent_playbook/x.py``, ``tests/hooks/``)."""

    pr: str
    old: str
    new: str


@dataclass(frozen=True, slots=True)
class MoveMap:
    """The composed map: every ``move_map/*.toml`` file, chains resolved by name, not by file order."""

    modules: tuple[ModuleMove, ...] = ()
    names: tuple[NameMove, ...] = ()
    paths: tuple[PathMove, ...] = ()

    def resolve(self, dotted: str, tree: Path) -> str | None:
        """The current spelling of ``dotted`` (a module or ``module.attr``), or None if current.

        Also None when the map does not name it or gives no spelling the tree defines.
        Example: ``resolve("coding_agent_playbook._toml", repo)`` -> ``"coding_agent_playbook.toml_writer"``.
        """
        if self._dotted_step(dotted, set()) is None or is_current(dotted, tree):
            return None
        return _follow(dotted, self._dotted_step, lambda name: is_current(name, tree))

    def resolve_path(self, path: str, tree: Path) -> str | None:
        """The current spelling of a repo-relative doc path, or None if it exists or is unmapped.

        Example: ``resolve_path("src/coding_agent_playbook/_toml.py", repo)`` ->
        ``"src/coding_agent_playbook/toml_writer.py"``.
        """
        if self._path_step(path, set()) is None or path_exists(path, tree):
            return None
        return _follow(path, self._path_step, lambda name: path_exists(name, tree))

    def conversion(self, dotted: str, tree: Path) -> str | None:
        """The module a module-object import of ``dotted`` binds after a same-name conversion.

        ``catalog.py`` -> ``catalog/roots.py`` leaves ``coding_agent_playbook.catalog``
        importable as a docstring-only package, so currentness cannot see that
        ``from coding_agent_playbook import catalog`` is stale (5.4.2 R-IMPORT).
        Example: ``conversion("coding_agent_playbook.catalog", repo)`` -> ``"coding_agent_playbook.catalog.roots"``.
        """
        for entry in self.modules:
            same_name = not entry.package and entry.new.startswith(f"{entry.old}.")
            if same_name and entry.old == dotted and is_package(dotted, tree):
                return entry.new if is_current(entry.new, tree) else self.resolve(entry.new, tree)
        return None

    def path_moves(self) -> tuple[PathMove, ...]:
        """The ``[[path]]`` entries derived from ``[[module]]`` entries, then the hand-written ones.

        Example: N1's entry derives ``PathMove("N1", "src/coding_agent_playbook/_toml.py",
        "src/coding_agent_playbook/toml_writer.py")``.
        """
        derived = tuple(
            PathMove(
                entry.pr,
                module_path(entry.old, entry.package),
                module_path(entry.new, entry.package),
            )
            for entry in self.modules
        )
        return derived + self.paths

    def bare_root_names(self) -> frozenset[str]:
        """Moved root module files and package dirs: reported bare, never rewritten (5.4.3).

        Example: with N1 and N12, ``bare_root_names()`` is ``frozenset({"_toml.py", "harness/"})``.
        """
        root = f"src/{ENGINE}/"
        olds = (
            move.old.removeprefix(root) for move in self.path_moves() if move.old.startswith(root)
        )
        return frozenset(old for old in olds if "/" not in old.rstrip("/"))

    def needles(self) -> frozenset[str]:
        """Substrings one of which every reference to an old name contains (a cheap file filter).

        Example: with N1, ``needles()`` is ``frozenset({"_toml"})``; an empty map has none,
        so ``check`` opens no file at all.
        """
        leaves = {entry.old.rpartition(".")[2] for entry in self.modules}
        leaves |= {name for entry in self.names for name in entry.names}
        leaves |= {Path(entry.old).stem for entry in self.paths}
        return frozenset(leaves)

    def _dotted_step(self, name: str, used: set[object]) -> tuple[object, str] | None:
        candidates: list[tuple[object, str, str]] = [
            (entry, entry.old, entry.new) for entry in self.modules
        ]
        candidates += [
            ((entry, moved), f"{entry.old}.{moved}", f"{entry.new}.{moved}")
            for entry in self.names
            for moved in entry.names
        ]
        return _longest(
            name, candidates, used, lambda old: name == old or name.startswith(f"{old}.")
        )

    def _path_step(self, name: str, used: set[object]) -> tuple[object, str] | None:
        candidates: list[tuple[object, str, str]] = [
            (move, move.old, move.new) for move in self.path_moves()
        ]
        return _longest(
            name,
            candidates,
            used,
            lambda old: name == old or (old.endswith("/") and name.startswith(old)),
        )


def _longest(
    name: str,
    candidates: Sequence[tuple[object, str, str]],
    used: set[object],
    matches: Callable[[str], bool],
) -> tuple[object, str] | None:
    """The unused entry with the longest matching ``old`` (the longer ``old`` wins), applied."""
    best: tuple[object, str, str] | None = None
    for key, old, new in candidates:
        if key not in used and matches(old) and (best is None or len(old) > len(best[1])):
            best = (key, old, new)
    return None if best is None else (best[0], best[2] + name[len(best[1]) :])


def _follow(start: str, step: _Step, current: Callable[[str], bool]) -> str | None:
    """Apply entries one after another, each at most once, until a spelling is current."""
    used: set[object] = set()
    spelling = start
    while (found := step(spelling, used)) is not None:
        used.add(found[0])
        spelling = found[1]
        if current(spelling):
            return spelling
    return None


def load_map(path: Path) -> MoveMap:
    """Read and compose every ``*.toml`` under ``path`` (the ``move_map/`` directory).

    Raises ``ValueError`` naming an entry that renames a frozen name (5.4.3), that is
    not idempotent (``new`` under ``old`` with ``package=True``), or whose ``old``
    another entry also moves (two PRs moving one module is a planning error, not a
    merge order). Example: ``load_map(repo / MAP_DIR)`` -> ``MoveMap()`` while empty.
    """
    entries: list[tuple[ModuleMove | NameMove | PathMove, Path]] = []
    for file in sorted(path.glob("*.toml")):
        tables = _read_map_file(file)
        entries += [(_module_entry(file, raw), file) for raw in tables["module"]]
        entries += [(_name_entry(file, raw), file) for raw in tables["names"]]
        entries += [(_path_entry(file, raw), file) for raw in tables["path"]]
    _refuse_doubles(entries)
    return MoveMap(
        tuple(entry for entry, _ in entries if isinstance(entry, ModuleMove)),
        tuple(entry for entry, _ in entries if isinstance(entry, NameMove)),
        tuple(entry for entry, _ in entries if isinstance(entry, PathMove)),
    )


def _read_map_file(file: Path) -> dict[str, list[Mapping[str, object]]]:
    try:
        data = tomllib.loads(file.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{file.name}: not valid TOML ({error})") from error
    unknown = sorted(set(data) - set(_ENTRY_KEYS))
    if unknown:
        raise ValueError(
            f"{file.name}: unknown keys {unknown}; expected [[module]], [[names]] or [[path]] arrays"
        )
    return {kind: _entry_tables(file, kind, data.get(kind, [])) for kind in _ENTRY_KEYS}


def _entry_tables(file: Path, kind: str, raw: object) -> list[Mapping[str, object]]:
    if not isinstance(raw, list) or not all(isinstance(entry, dict) for entry in raw):
        raise ValueError(
            f"{file.name}: {kind} must be an array of tables ([[{kind}]]), got {raw!r}"
        )
    required, optional = _ENTRY_KEYS[kind]
    for entry in raw:
        missing, extra = required - set(entry), set(entry) - required - optional
        if missing or extra:
            raise ValueError(
                f"{file.name}: [[{kind}]] {entry!r} lacks {sorted(missing)} or has unknown"
                f" {sorted(extra)}; expected the keys {sorted(required | optional)}"
            )
    return raw


def _text(file: Path, kind: str, entry: Mapping[str, object], key: str) -> str:
    value = entry[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{file.name}: [[{kind}]] {key} must be a non-empty string, got {value!r}")
    return value


def _dotted(file: Path, kind: str, entry: Mapping[str, object], key: str) -> str:
    value = _text(file, kind, entry, key)
    if not _DOTTED_NAME.match(value):
        raise ValueError(
            f"{file.name}: [[{kind}]] {key} = {value!r} is not a dotted module name"
            f" under {ENGINE} or tests (for example '{ENGINE}.toml_writer')"
        )
    return value


def _module_entry(file: Path, raw: Mapping[str, object]) -> ModuleMove:
    package = raw.get("package", False)
    if not isinstance(package, bool):
        raise ValueError(f"{file.name}: [[module]] package must be true or false, got {package!r}")
    old, new = _dotted(file, "module", raw, "old"), _dotted(file, "module", raw, "new")
    where = f"{file.name}: [[module]] old = {old!r}"
    frozen = [name for name in FROZEN_MODULES if name == old or name.startswith(f"{old}.")]
    if frozen:
        raise ValueError(
            f"{where} renames the frozen name {frozen[0]!r} (L2: the external contract never moves)"
        )
    if any(old == label or old.startswith(f"{label}.") for label in _NOT_MODULES):
        raise ValueError(f"{where} is an overlay label, not a module")
    if old == new or (package and new.startswith(f"{old}.")):
        raise ValueError(
            f"{where} is not idempotent: new = {new!r} equals old or lies under the moved package"
        )
    return ModuleMove(_text(file, "module", raw, "pr"), old, new, package)


def _name_entry(file: Path, raw: Mapping[str, object]) -> NameMove:
    old, new = _dotted(file, "names", raw, "old"), _dotted(file, "names", raw, "new")
    names = raw["names"]
    where = f"{file.name}: [[names]] old = {old!r}"
    if not isinstance(names, list) or not _distinct_identifiers(names) or old == new:
        raise ValueError(
            f"{where}: names must be distinct identifiers moving to another module, got {names!r} -> {new!r}"
        )
    frozen = [name for name in names if (old, name) in _FROZEN_ATTRIBUTES]
    if frozen:
        raise ValueError(f"{where} moves the frozen console-script target {old}:{frozen[0]} (L2)")
    return NameMove(_text(file, "names", raw, "pr"), old, new, tuple(names))


def _distinct_identifiers(names: list[object]) -> bool:
    valid = all(isinstance(name, str) and _IDENTIFIER.match(name) for name in names)
    return valid and bool(names) and len(set(names)) == len(names)


def _path_entry(file: Path, raw: Mapping[str, object]) -> PathMove:
    old, new = _text(file, "path", raw, "old"), _text(file, "path", raw, "new")
    where = f"{file.name}: [[path]] old = {old!r}"
    if not (_RELATIVE_PATH.match(old) and _RELATIVE_PATH.match(new)) or old == new:
        raise ValueError(
            f"{where}: old and new must be distinct relative paths ('x/y.py' or 'x/y/'), got new = {new!r}"
        )
    if old.endswith("/") != new.endswith("/"):
        raise ValueError(
            f"{where}: old and new must both be directories (ending in '/') or both files"
        )
    entry = PathMove(_text(file, "path", raw, "pr"), _repo_relative(old), _repo_relative(new))
    frozen = [
        path
        for path in _FROZEN_PATHS
        if path == entry.old or (old.endswith("/") and path.startswith(entry.old))
    ]
    if frozen:
        raise ValueError(f"{where} renames the frozen path {frozen[0]!r} (L2)")
    return entry


def _repo_relative(path: str) -> str:
    return path if path.startswith("tests/") else f"src/{ENGINE}/{path}"


def _refuse_doubles(entries: Sequence[tuple[ModuleMove | NameMove | PathMove, Path]]) -> None:
    seen: dict[tuple[str, str], Path] = {}
    keyed = ((key, file) for entry, file in entries for key in _double_keys(entry))
    for key, file in keyed:
        if key in seen:
            raise ValueError(
                f"{file.name}: [[{key[0]}]] {key[1]!r} is also moved by {seen[key].name};"
                " two PRs moving one name is a planning error, not a merge order"
            )
        seen[key] = file


def _double_keys(entry: ModuleMove | NameMove | PathMove) -> list[tuple[str, str]]:
    if isinstance(entry, ModuleMove):
        return [("module", entry.old), ("path", module_path(entry.old, entry.package))]
    if isinstance(entry, NameMove):
        return [("names", f"{entry.old}.{name}") for name in entry.names]
    return [("path", entry.old)]


def apply(repo_root: Path, moves: MoveMap, *, formatter: Formatter | None = None) -> list[Path]:
    """Rewrite every file the rules of 5.4.2 cover; return the files changed.

    R-FORMAT then hands the changed ``.py`` and ``.md`` files to ``formatter``
    (``_module_moves_format.run_ruff`` by default). Example:
    ``apply(repo, load_map(repo / MAP_DIR))`` -> ``[]`` on a tree that is already current.
    """
    # Every refusal (a relative import, an unbalanced marker) raises while the edits are
    # computed, so all of them are computed before the first write: a refusal in a later
    # file left earlier files rewritten and never formatted (review of #152).
    pending = [rewrite for rewrite in rewrites(repo_root, moves) if rewrite.edits]
    for rewrite in pending:
        rewrite.path.write_bytes(applied(rewrite.text, rewrite.edits).encode("utf-8"))
    changed = [rewrite.path for rewrite in pending]
    formattable = [path for path in changed if path.suffix in (".py", ".md")]
    if formattable:
        (formatter or run_ruff)(repo_root, formattable)
    return changed


def check(repo_root: Path, moves: MoveMap) -> list[str]:
    """``path:line: <old> -> <new>`` for every stale reference, plus the ``review:`` lines of 5.4.3.

    Example: ``check(repo, moves)`` ->
    ``["tests/a.py:1: coding_agent_playbook._toml -> coding_agent_playbook.toml_writer"]``.
    """
    stale: list[str] = []
    reviews: list[str] = []
    for rewrite in rewrites(repo_root, moves):
        relative = rewrite.path.relative_to(repo_root).as_posix()
        stale += [f"{relative}:{shown(rewrite.text, edit)}" for edit in rewrite.edits]
        reviews += [f"review: {relative}:{review}" for review in rewrite.reviews]
    return stale + reviews


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``apply`` or ``check`` on ``--repo`` (default: this checkout).

    Returns 1 when check prints a stale line and 2 for an invalid map. Example:
    ``main(["check"])`` prints nothing and returns 0 on a current tree.
    """
    parser = argparse.ArgumentParser(
        prog="python -m tests.architecture.module_moves",
        description="Rewrite (apply) or list (check) the module paths the move map has moved.",
    )
    parser.add_argument("command", choices=("apply", "check"))
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    arguments = parser.parse_args(argv)
    try:
        return _run(arguments.command, arguments.repo.resolve())
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _run(command: str, repo: Path) -> int:
    moves = load_map(repo / MAP_DIR)
    if command == "apply":
        for path in apply(repo, moves):
            print(path.relative_to(repo).as_posix())
        return 0
    lines = check(repo, moves)
    for line in lines:
        print(line)
    return 1 if any(not line.startswith("review: ") for line in lines) else 0


if __name__ == "__main__":
    raise SystemExit(main())
