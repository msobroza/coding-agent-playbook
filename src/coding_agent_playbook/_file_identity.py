"""Spelling-proof "is this one of the files written this sync?" (stdlib-only leaf).

Comparing paths as strings is wrong on a case-insensitive filesystem (default
macOS APFS, Windows): after a case-only rename (``Demo`` -> ``demo``) the old
spelling names the very file just written, so a string comparison calls fresh
output stale and deletes it. :class:`FileSet` also compares file identity
(``st_dev``, ``st_ino``). Used by every stale-output decision in ``playbook
sync`` — the adapters' sentinel cleanup and the lockfile leftover policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


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
        for path in files:
            members.add(path)
        return members

    def add(self, path: Path) -> None:
        """Add ``path`` (its identity too, when it exists)."""
        self.paths.add(path.resolve())
        identity = file_identity(path)
        if identity is not None:
            self.identities.add(identity)

    def holds(self, path: Path) -> bool:
        """True when ``path`` resolves to a member or is the same file as one."""
        if path.resolve() in self.paths:
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
