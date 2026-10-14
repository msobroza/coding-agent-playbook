"""Where engine output may live: the leftover policy's bounds (SPEC §4.2 step 9, §10.1).

Built from the adapters' declared ``output_locations``, it does two jobs:

- **Deletion allowlist.** An orphan is deleted only inside a declared location,
  so a hand-edited (or merged, under ``commit = true``) lockfile can never aim
  ``playbook sync`` at ``.git/HEAD`` or a source file.
- **Prune boundary.** Directories a deletion empties are pruned bottom-up, but
  never above a declared directory, and a declared directory itself only when
  it is a real directory as spelled. Lockfile paths are *resolved*, so with
  ``.claude/skills -> ../.agents/skills`` an entry reads
  ``.agents/skills/demo/SKILL.md``: pruning stops below ``.agents/skills`` (the
  link's target) instead of removing it — and ``.agents`` — and leaving the
  user's link dangling.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class _Root:
    """A declared output directory (as spelled, or as resolved through a symlink)."""

    rel: PurePosixPath
    prunable: bool  # the spelled, symlink-free form: removed itself once empty


@dataclass(frozen=True)
class OutputLocations:
    """Declared output files and directories, each also under its resolved spelling.

    Example::

        >>> locations = OutputLocations.declared(["AGENTS.md", ".claude/skills/"], Path("/r"))
        >>> locations.contains(".claude/skills/demo/SKILL.md"), locations.contains("src/a.py")
        (True, False)
    """

    files: frozenset[str]
    roots: tuple[_Root, ...]

    @classmethod
    def declared(cls, locations: Iterable[str], repo_root: Path) -> OutputLocations:
        """Build from ``output_locations`` entries (a trailing ``/`` marks a directory).

        Unusable entries (absolute, empty, ``..``) are ignored: they can never
        widen the allowlist to the repo root or beyond.
        """
        root = repo_root.resolve()
        files: set[str] = set()
        roots: list[_Root] = []
        for location in locations:
            spelled = PurePosixPath(location.rstrip("/"))
            if spelled.is_absolute() or not spelled.parts or ".." in spelled.parts:
                continue
            resolved = _resolved_rel(root.joinpath(*spelled.parts), root)
            if not location.endswith("/"):
                files.update(rel.as_posix() for rel in (spelled, resolved) if rel is not None)
                continue
            roots.append(_Root(spelled, prunable=resolved == spelled))
            if resolved is not None and resolved.parts and resolved != spelled:
                roots.append(_Root(resolved, prunable=False))
        return cls(frozenset(files), tuple(roots))

    def contains(self, rel: str) -> bool:
        """True when the repo-relative POSIX ``rel`` lies in a declared location."""
        return rel in self.files or self._root_of(PurePosixPath(rel)) is not None

    def prune_emptied(self, deleted: Iterable[Path], repo_root: Path) -> None:
        """``rmdir`` the directories ``deleted`` files left empty, bottom-up, within bounds.

        Stops at the first directory with anything left in it, never goes above
        the declared directory holding the file, never removes the repo root,
        and removes the declared directory itself only when it is prunable.
        Files outside every declared directory prune nothing.
        """
        root = repo_root.resolve()
        for path in deleted:
            rel = _resolved_rel(path, root)
            owner = None if rel is None else self._root_of(rel)
            if rel is not None and owner is not None:
                _prune_up_to(root, rel, owner)

    def _root_of(self, rel: PurePosixPath) -> _Root | None:
        """The deepest declared directory strictly containing ``rel``."""
        holders = [candidate for candidate in self.roots if candidate.rel in rel.parents]
        return max(holders, key=lambda holder: len(holder.rel.parts), default=None)


def _resolved_rel(path: Path, root: Path) -> PurePosixPath | None:
    """``path`` (which may no longer exist) resolved, relative to ``root``; ``None`` outside."""
    try:
        return PurePosixPath(path.resolve().relative_to(root).as_posix())
    except ValueError:
        return None


def _prune_up_to(root: Path, rel: PurePosixPath, owner: _Root) -> None:
    stop = root.joinpath(*owner.rel.parts)
    for parent in root.joinpath(*rel.parts).parents:
        if parent == stop:
            if owner.prunable:
                _rmdir(parent)
            return
        if not _rmdir(parent):
            return


def _rmdir(directory: Path) -> bool:
    """Remove ``directory`` if it is empty; ``False`` if anything is left (or it is gone)."""
    try:
        directory.rmdir()
    except OSError:
        return False
    return True
