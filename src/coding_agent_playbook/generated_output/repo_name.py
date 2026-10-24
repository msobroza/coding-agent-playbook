"""The repo root and name every sync mode derives the same way, however the root was typed.

``--repo-root`` arrives as typed: ``.`` (whose ``Path.name`` is ``""``),
``x/sub/..`` (``..``), a symlink alias with its own name, or a case variant on a
case-insensitive filesystem. Write mode named ``HARNESS.md`` after that spelling
while ``sync --check`` rendered into a scratch directory named after the
resolved directory, so a fresh sync was drift (#268). :func:`canonical_root` is
the one root the sync pipeline works on, and :func:`repo_dir_name` the one name
both modes write.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.generated_output.symlinks import real_path

if TYPE_CHECKING:
    from pathlib import Path

#: The name of a root with no last component (``/``, a drive root). It is what write
#: mode wrote for ``--repo-root .`` before #268, and the only fallback left.
FALLBACK_REPO_NAME: Final = "harness"


def canonical_root(root: Path) -> Path:
    """``root`` absolute and resolved, its last component spelled as on disk; never raises.

    Symlinks resolve (a link loop stays unresolved, as with :func:`real_path`, where
    Python 3.12's ``Path.resolve()`` raises). On a case-insensitive filesystem the
    leaf takes the directory's own spelling, which ``realpath`` keeps as typed on
    macOS. An absolute physical root (``Path.cwd()``) comes back unchanged.

    Example: ``canonical_root(Path(".."))`` from ``/work/probe/sub`` -> ``/work/probe``.
    """
    resolved = real_path(root)
    if not resolved.name:
        return resolved
    return resolved.with_name(_on_disk_spelling(resolved))


def repo_dir_name(root: Path) -> str:
    """The repo's directory name for name-derived output (``HARNESS.md``), whatever ``root``'s spelling.

    The leaf of :func:`canonical_root`, or :data:`FALLBACK_REPO_NAME` for a root
    with no name (``/``).

    Example: ``repo_dir_name(Path("."))`` inside ``/work/probe`` -> ``"probe"``.
    """
    return canonical_root(root).name or FALLBACK_REPO_NAME


def _on_disk_spelling(resolved: Path) -> str:
    """The parent's entry for ``resolved``: its own name, or the one entry it differs from by case.

    The exact name listed means it is the spelling (a case-insensitive filesystem
    cannot list two names that differ only by case). Otherwise the entry must
    match by casefold *and* be the same file, so a case-sensitive sibling is
    never taken. An unreadable parent or a missing root keeps the resolved name.
    """
    try:
        names = os.listdir(resolved.parent)
    except OSError:
        return resolved.name
    if resolved.name in names:
        return resolved.name
    folded = resolved.name.casefold()
    for name in names:
        if name.casefold() == folded and _same_file(resolved.parent / name, resolved):
            return name
    return resolved.name


def _same_file(candidate: Path, resolved: Path) -> bool:
    """``os.path.samefile`` that answers ``False`` instead of raising."""
    try:
        return os.path.samefile(candidate, resolved)
    except OSError:
        return False
