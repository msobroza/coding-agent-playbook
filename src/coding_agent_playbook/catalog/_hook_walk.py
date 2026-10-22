"""Discover the hook directories of one artifact layer (specs/prK-lifecycle-hooks.md §A.1, §A.5).

A hook is a directory holding ``HOOK.md`` or ``HOOK.md.j2``, at any depth under
a layer's ``hooks/`` root; the folders above it are categories with no
meaning. Only those two exact names mark a hook, so a ``scripts/README.md`` is
never parsed as one. Split out of ``catalog/source.py`` for the file-size
budget.

The walk uses ``os.walk`` rather than ``Path.rglob``: it never follows a
directory symlink on any supported Python (``rglob``'s behaviour changed in
3.13), and it prunes dot-directories (the ``catalog.skill_rules.iter_md_files`` hygiene rule)
before descending into them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.hook import Hook
from coding_agent_playbook.artifacts.hook_schema import HookSchemaError

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The marker file names; the directory holding one is the hook directory.
HOOK_MARKERS: Final = ("HOOK.md", "HOOK.md.j2")


@dataclass
class HookWalk:
    """One layer's hooks plus one error per hook directory that could not load."""

    hooks: list[Hook] = field(default_factory=list)
    errors: list[HookSchemaError] = field(default_factory=list)


def walk_hook_layer(root: Path, source_package: str) -> HookWalk:
    """Load every hook directory under ``root``, recording errors instead of raising.

    Layout errors are H2: both markers in one directory, a hook directory
    beneath another one (its ``scripts/`` included); so are a marker that links
    out of ``root`` and one that is not a regular file. Each is a
    ``HookSchemaError`` on field ``layout``.

    Example::

        >>> walk_hook_layer(Path("/repo/playbook/hooks"), "<repo-local>").hooks  # doctest: +SKIP
        [Hook(...)]
    """
    walk = HookWalk()
    hook_dirs: list[Path] = []
    for hook_dir, markers in _marker_dirs(root):
        problem = _layout_problem(hook_dir, markers, hook_dirs, root)
        hook_dirs.append(hook_dir)
        if problem is not None:
            walk.errors.append(problem)
            continue
        _load_into(walk, hook_dir / markers[0], source_package)
    return walk


def _load_into(walk: HookWalk, marker: Path, source_package: str) -> None:
    """Parse ``marker`` onto ``walk.hooks``, or its error onto ``walk.errors``."""
    try:
        walk.hooks.append(Hook.from_markdown(marker, source_package))
    except HookSchemaError as exc:
        walk.errors.append(exc)
    except OSError as exc:  # permissions, or deleted between the walk and the read
        walk.errors.append(_layout_error(marker, f"cannot be read: {exc}"))


def _marker_dirs(root: Path) -> Iterator[tuple[Path, list[str]]]:
    """``(directory, markers present)`` for each directory holding a marker, parents first."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Pruning in place stops os.walk descending; sorting makes the order deterministic.
        dirnames[:] = sorted(name for name in dirnames if not name.startswith("."))
        markers: list[str] = [name for name in HOOK_MARKERS if name in filenames]
        if markers:
            yield Path(dirpath), markers


def _layout_problem(
    hook_dir: Path, markers: list[str], earlier: list[Path], root: Path
) -> HookSchemaError | None:
    """The H2 layout error of ``hook_dir``, or ``None`` when it may load."""
    outer = next((parent for parent in earlier if hook_dir.is_relative_to(parent)), None)
    if outer is not None:
        return _layout_error(
            hook_dir / markers[0],
            f"a hook directory nested under hook directory {str(outer)!r}; "
            "move it out (hooks cannot contain hooks)",
        )
    if len(markers) > 1:
        return _layout_error(
            hook_dir, "both HOOK.md and HOOK.md.j2 in one hook directory; keep exactly one"
        )
    marker = hook_dir / markers[0]
    if not marker.resolve().is_relative_to(root.resolve()):
        return _layout_error(marker, f"links outside its layer {str(root)!r}; copy it in instead")
    if not marker.is_file():
        # A broken link would raise on read, and a FIFO would block it forever.
        return _layout_error(marker, "is not a regular file")
    return None


def _layout_error(path: Path, problem: str) -> HookSchemaError:
    return HookSchemaError(
        str(path), "layout", str(path), "one HOOK.md or HOOK.md.j2 per hook", problem=problem
    )
