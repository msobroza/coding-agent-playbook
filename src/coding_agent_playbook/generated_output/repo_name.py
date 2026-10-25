"""The repo root and name every sync mode derives the same way, however the root was typed.

``--repo-root`` arrives as typed: ``.`` (whose ``Path.name`` is ``""``),
``x/sub/..`` (``..``), a symlink alias with its own name, or a case or Unicode
normalization variant (NFC typed for an NFD directory) on a filesystem that
ignores both, as APFS does. Write mode named ``HARNESS.md`` after that spelling
while ``sync --check`` rendered into a scratch directory named after the
resolved directory, so a fresh sync was drift (#268). :func:`canonical_root` is
the one root the sync pipeline works on, and :func:`repo_dir_name` the one name
both modes write.
"""

from __future__ import annotations

import os
import unicodedata
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.generated_output.symlinks import real_path

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

#: The name of a root with no last component (``/``, a drive root). It is what write
#: mode wrote for ``--repo-root .`` before #268, and the only fallback left.
FALLBACK_REPO_NAME: Final = "harness"


def canonical_root(root: Path) -> Path:
    """``root`` absolute and resolved, its last component spelled as on disk; never raises.

    Symlinks resolve (a link loop stays unresolved, as with :func:`real_path`, where
    Python 3.12's ``Path.resolve()`` raises). On a filesystem that ignores case or
    Unicode normalization (APFS) the leaf takes the directory's own spelling, which
    ``realpath`` keeps as typed on macOS. An absolute physical root (``Path.cwd()``) comes back unchanged.

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


def _same_file(candidate: Path, resolved: Path) -> bool:
    """``os.path.samefile`` that answers ``False`` instead of raising."""
    try:
        return os.path.samefile(candidate, resolved)
    except OSError:
        return False


def _spelling_key(name: str) -> str:
    """``name`` as a filesystem that ignores case and Unicode normalization compares it.

    APFS keeps the bytes it was given but matches ``café`` typed NFC against an NFD
    entry, so the key folds both normalization (NFC) and case.
    """
    return unicodedata.normalize("NFC", name).casefold()


def _on_disk_spelling(
    resolved: Path,
    *,
    list_dir: Callable[[Path], list[str]] = os.listdir,
    same_file: Callable[[Path, Path], bool] = _same_file,
) -> str:
    """The parent's entry for ``resolved``: its own name, or the one entry that spells it differently.

    The exact name listed means it is the spelling. Otherwise the entry must match
    by :func:`_spelling_key` (case and Unicode normalization) *and* be the same
    file, so a sibling that a case- or normalization-sensitive filesystem keeps
    apart is never taken. An unreadable parent or a missing root keeps the
    resolved name. ``list_dir`` and ``same_file`` are seams for tests on a
    filesystem that tells spellings apart (CI's ext4).

    Example: ``_on_disk_spelling(Path("/work/PROBE"))`` on APFS -> ``"probe"``.
    """
    try:
        names = list_dir(resolved.parent)
    except OSError:
        return resolved.name
    if resolved.name in names:
        return resolved.name
    key = _spelling_key(resolved.name)
    for name in names:
        if _spelling_key(name) == key and same_file(resolved.parent / name, resolved):
            return name
    return resolved.name
