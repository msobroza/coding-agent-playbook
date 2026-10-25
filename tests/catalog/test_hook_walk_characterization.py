"""``catalog._hook_walk`` pinned against its code before the nested-hook lookup changed.

``_layout_problem`` found a hook's outer hook directory by calling
``hook_dir.is_relative_to(parent)`` on every earlier hook directory, each call a
fresh walk up ``hook_dir.parents``. The reference functions below are that code,
verbatim, so the walk's whole output (hooks, errors, messages, order) on the
shipped hook pack, on hand-built broken trees and on generated ones must stay
exactly what it was.
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.catalog import _hook_walk
from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE
from tests._catalog import CORE_ROOT
from tests.hook_samples import write_hook

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.hook_schema import HookSchemaError

_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")

ErrorRow = tuple[str, str, str, str]


def _reference_outer(hook_dir: Path, earlier: list[Path]) -> Path | None:
    """The pre-change nested-hook scan (catalog/_hook_walk.py at 8eb43dff)."""
    return next((parent for parent in earlier if hook_dir.is_relative_to(parent)), None)


def _reference_layout_problem(
    hook_dir: Path, markers: list[str], earlier: list[Path], root: Path
) -> HookSchemaError | None:
    """``_layout_problem`` as it was at 8eb43dff."""
    outer = _reference_outer(hook_dir, earlier)
    if outer is not None:
        return _hook_walk._layout_error(
            hook_dir / markers[0],
            f"a hook directory nested under hook directory {str(outer)!r}; "
            "move it out (hooks cannot contain hooks)",
        )
    if len(markers) > 1:
        return _hook_walk._layout_error(
            hook_dir, "both HOOK.md and HOOK.md.j2 in one hook directory; keep exactly one"
        )
    marker = hook_dir / markers[0]
    if not marker.resolve().is_relative_to(root.resolve()):
        return _hook_walk._layout_error(
            marker, f"links outside its layer {str(root)!r}; copy it in instead"
        )
    if not marker.is_file():
        return _hook_walk._layout_error(marker, "is not a regular file")
    return None


def _reference_walk(root: Path, source_package: str) -> _hook_walk.HookWalk:
    """``walk_hook_layer`` as it was at 8eb43dff."""
    walk = _hook_walk.HookWalk()
    hook_dirs: list[Path] = []
    for hook_dir, markers in _hook_walk._marker_dirs(root):
        problem = _reference_layout_problem(hook_dir, markers, hook_dirs, root)
        hook_dirs.append(hook_dir)
        if problem is not None:
            walk.errors.append(problem)
            continue
        _hook_walk._load_into(walk, hook_dir / markers[0], source_package)
    return walk


def _snapshot(walk: _hook_walk.HookWalk) -> tuple[list[Hook], list[ErrorRow]]:
    """Everything a walk reports, errors as ``(type, where, field, message)`` rows."""
    rows = [(type(error).__name__, error.where, error.field, str(error)) for error in walk.errors]
    return walk.hooks, rows


def _assert_walk_unchanged(root: Path, source_package: str = "<repo-local>") -> None:
    assert _snapshot(_hook_walk.walk_hook_layer(root, source_package)) == _snapshot(
        _reference_walk(root, source_package)
    )


def _nested(where: Path, outer: Path) -> str:
    return (
        f"{where}: layout: a hook directory nested under hook directory {str(outer)!r}; "
        "move it out (hooks cannot contain hooks)"
    )


# --- the shipped hook pack -------------------------------------------------------------


@pytest.mark.catalog
def test_shipped_hook_pack_walks_exactly_as_before() -> None:
    root = CORE_ROOT / "hooks"
    walk = _hook_walk.walk_hook_layer(root, ENGINE_PACKAGE)

    assert walk.hooks, f"no hook found under {root}: the comparison would be vacuous"
    assert walk.errors == []
    _assert_walk_unchanged(root, ENGINE_PACKAGE)


# --- hand-built broken trees -----------------------------------------------------------


def test_a_chain_of_nested_hooks_names_the_outermost_one(tmp_path: Path) -> None:
    outer = write_hook(tmp_path, "outer", scripts=True)
    middle = write_hook(outer.parent / "scripts", "middle", category="", scripts=True)
    inner = write_hook(middle.parent / "scripts", "inner", category="")

    _hooks, rows = _snapshot(_hook_walk.walk_hook_layer(tmp_path, "<repo-local>"))

    assert [row[3] for row in rows] == [
        _nested(middle, outer.parent),
        _nested(inner, outer.parent),
    ]
    _assert_walk_unchanged(tmp_path)


def test_a_name_prefix_is_not_an_outer_hook_directory(tmp_path: Path) -> None:
    write_hook(tmp_path, "guard", category="")
    write_hook(tmp_path, "guard-x", category="")
    write_hook(tmp_path / "guard-x" / "sub", "guard", category="")

    hooks, rows = _snapshot(_hook_walk.walk_hook_layer(tmp_path, "<repo-local>"))

    assert [hook.frontmatter.id for hook in hooks] == ["guard", "guard-x"]
    assert [row[3] for row in rows] == [
        _nested(tmp_path / "guard-x" / "sub" / "guard" / "HOOK.md", tmp_path / "guard-x")
    ]
    _assert_walk_unchanged(tmp_path)


def test_hooks_under_a_two_marker_dir_and_their_siblings(tmp_path: Path) -> None:
    both = write_hook(tmp_path, "both")
    write_hook(tmp_path, "both", marker="HOOK.md.j2")
    write_hook(both.parent, "inner", category="deeper")
    write_hook(tmp_path, "after")

    hooks, rows = _snapshot(_hook_walk.walk_hook_layer(tmp_path, "<repo-local>"))

    assert [hook.frontmatter.id for hook in hooks] == ["after"]
    assert [row[3] for row in rows] == [
        f"{both.parent}: layout: both HOOK.md and HOOK.md.j2 in one hook directory; "
        "keep exactly one",
        _nested(both.parent / "deeper" / "inner" / "HOOK.md", both.parent),
    ]
    _assert_walk_unchanged(tmp_path)


def _outside_link(root: Path) -> None:
    target = write_hook(root.parent / "elsewhere", "linked")
    link = root / "protect" / "linked" / "HOOK.md"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)


def _broken_link(root: Path) -> None:
    marker = root / "protect" / "broken" / "HOOK.md"
    marker.parent.mkdir(parents=True)
    marker.symlink_to(marker.parent / "missing.md")


def _fifo(root: Path) -> None:
    marker = root / "protect" / "fifo" / "HOOK.md"
    marker.parent.mkdir(parents=True)
    os.mkfifo(marker)


@_POSIX_ONLY
@pytest.mark.parametrize("make_odd", [_outside_link, _broken_link, _fifo])
def test_odd_markers_report_as_before(tmp_path: Path, make_odd: Callable[[Path], None]) -> None:
    root = tmp_path / "hooks"
    write_hook(root, "good")
    make_odd(root)
    write_hook(root / "protect" / "good", "under-good", category="")

    _assert_walk_unchanged(root)


# --- generated trees -------------------------------------------------------------------

#: Few names, so generated hook directories often land inside one another.
_SEGMENTS = ("a", "ab", "b", "scripts", ".hidden")


def _random_tree(root: Path, rng: random.Random) -> None:
    """Write 1-12 hook directories at random, often nested, doubled or dot-hidden."""
    for _ in range(rng.randint(1, 12)):
        *parents, name = [rng.choice(_SEGMENTS) for _ in range(rng.randint(1, 4))]
        marker = "HOOK.md.j2" if rng.random() < 0.2 else "HOOK.md"
        write_hook(root.joinpath(*parents), name, category="", marker=marker)


@pytest.mark.parametrize("seed", range(40))
def test_generated_trees_walk_exactly_as_before(tmp_path: Path, seed: int) -> None:
    root = tmp_path / "hooks"
    _random_tree(root, random.Random(seed))

    _assert_walk_unchanged(root)


# --- the outer-hook-directory lookup ---------------------------------------------------


def test_outer_hook_dir_is_none_without_earlier_hooks() -> None:
    assert _hook_walk._outer_hook_dir(Path("/h/a"), []) is None


def test_outer_hook_dir_is_the_first_earlier_ancestor_in_walk_order() -> None:
    earlier = [Path("/h/x"), Path("/h/a/scripts"), Path("/h/a")]

    assert _hook_walk._outer_hook_dir(Path("/h/a/scripts/b"), earlier) == Path("/h/a/scripts")


def test_outer_hook_dir_counts_the_directory_itself() -> None:
    assert _hook_walk._outer_hook_dir(Path("/h/a"), [Path("/h/a")]) == Path("/h/a")


def test_outer_hook_dir_ignores_a_mere_name_prefix() -> None:
    assert _hook_walk._outer_hook_dir(Path("/h/guard-x"), [Path("/h/guard")]) is None


def _random_path(rng: random.Random) -> Path:
    head = rng.choice(("/", "", "/h", "h"))
    tail = [rng.choice(("a", "ab", "b", "..", "scripts")) for _ in range(rng.randint(0, 5))]
    return Path(head, *tail) if head else Path(*tail)


def test_outer_hook_dir_matches_the_is_relative_to_scan_on_generated_paths() -> None:
    rng = random.Random(1729)
    for _ in range(5000):
        earlier = [_random_path(rng) for _ in range(rng.randint(0, 8))]
        hook_dir = _random_path(rng)
        assert _hook_walk._outer_hook_dir(hook_dir, earlier) == _reference_outer(
            hook_dir, earlier
        ), (hook_dir, earlier)


def test_outer_hook_dir_returns_the_earlier_entry_itself() -> None:
    first = Path("/h/a")
    earlier = [Path("/h/x"), first]

    assert _hook_walk._outer_hook_dir(Path("/h/a/b"), earlier) is first
