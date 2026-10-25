"""Spelling-proof "is this one of the files written this sync?" (stdlib and ``symlinks`` only).

Comparing paths as strings is wrong on a case-insensitive filesystem (default
macOS APFS, Windows): after a case-only rename (``Demo`` -> ``demo``) the old
spelling names the very file just written, so a string comparison calls fresh
output stale and deletes it. :class:`FileSet` also compares file identity
(``st_dev``, ``st_ino``). Used by every stale-output decision in ``playbook
sync`` — the adapters' sentinel cleanup and the lockfile leftover policy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.generated_output.symlinks import BatchRealPaths

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass
class FileSet:
    """Files known by resolved path *and* by identity (``st_dev``, ``st_ino``).

    Identity makes membership spelling-proof (case-insensitive filesystems,
    hard links); the resolved path also covers members that do not exist on
    disk (a ``--check`` render of a file not yet synced).

    Example::

        >>> written = FileSet.of([Path("AGENTS.md")])  # doctest: +SKIP
        >>> written.holds(Path("agents.md"))  # True on a case-insensitive FS  # doctest: +SKIP
        True
    """

    paths: set[Path] = field(default_factory=set)
    identities: set[tuple[int, int]] = field(default_factory=set)

    @classmethod
    def of(cls, files: Iterable[Path]) -> FileSet:
        """Build a set holding every path in ``files``."""
        members = cls()
        # One batch: a sync's ~730 written paths share their parents, and per-path
        # realpath here was 3,660 calls (5.5 s cumulative under cProfile) of one sync.
        # ``files`` is read first, so nothing it does while iterated falls between lookups.
        real = BatchRealPaths()
        for path in list(files):
            members._add_resolved(path, real.real(path))
        return members

    def add(self, path: Path) -> None:
        """Add ``path`` (its identity too, when it exists)."""
        self._add_resolved(path, _real(path))

    def _add_resolved(self, path: Path, resolved: Path) -> None:
        """Add ``path``, already resolved to ``resolved``, and its identity when it exists."""
        self.paths.add(resolved)
        identity = file_identity(path)
        if identity is not None:
            self.identities.add(identity)

    def holds(self, path: Path) -> bool:
        """True when ``path`` resolves to a member or is the same file as one."""
        if _real(path) in self.paths:
            return True
        identity = file_identity(path)
        return identity is not None and identity in self.identities


def file_identity(path: Path) -> tuple[int, int] | None:
    """``(st_dev, st_ino)`` of ``path`` (symlinks followed), ``None`` if it cannot be stat'ed.

    Example::

        >>> file_identity(Path("/no/such/file")) is None
        True
    """
    try:
        status = path.stat()
    except OSError:
        return None
    return (status.st_dev, status.st_ino)


def _real(path: Path) -> Path:
    """``path`` resolved without ``Path.resolve()``, which raises on a link loop on Python 3.12."""
    return Path(os.path.realpath(path))
