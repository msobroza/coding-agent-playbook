"""Where engine output may live: the leftover policy's bounds (SPEC §4.2 step 9, §10.1).

Built from the adapters' declared ``output_locations`` (current and retired), it
does two jobs:

- **Deletion allowlist.** An orphan is deleted only inside a declared location,
  so a hand-edited (or merged, under ``commit = true``) lockfile can never aim
  ``playbook sync`` at ``.git/HEAD`` or a source file.
- **Prune boundary.** Directories a deletion empties are pruned bottom-up, but
  never above a declared directory, and a declared directory itself only when
  it is a real directory as spelled. Lockfile paths are *resolved*, so with
  ``.claude/skills -> ../.agents/skills`` an entry reads
  ``.agents/skills/demo/SKILL.md``: pruning stops below ``.agents/skills`` (the
  link's target) instead of removing it — and ``.agents`` — and leaving the
  user's link dangling. That holds whatever order the adapters declare the two
  roots in, and in either link direction (specs/prS-skills-context.md 5.4.3).

Paths resolve through ``_symlinks.real_path`` (:func:`os.path.realpath`), not
``Path.resolve()``: on Python 3.12 the latter raises ``RuntimeError`` on a
symlink loop, so ``OutputLocations`` keeps a looping path as spelled and never
raises on one. The sync path's other loop-prone resolutions use the same helper
(``_sync_orphans._owned_path``, the protected rows, the stale-output scan).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from coding_agent_playbook._symlinks import real_path

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


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
        root = real_path(repo_root)
        files: set[str] = set()
        dirs: list[tuple[PurePosixPath, PurePosixPath | None]] = []
        for location in locations:
            spelled = PurePosixPath(location.rstrip("/"))
            if spelled.is_absolute() or not spelled.parts or ".." in spelled.parts:
                continue
            resolved = _resolved_rel(root.joinpath(*spelled.parts), root)
            if location.endswith("/"):
                dirs.append((spelled, resolved))
            else:
                files.update(rel.as_posix() for rel in (spelled, resolved) if rel is not None)
        return cls(frozenset(files), _declared_roots(dirs))

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
        root = real_path(repo_root)
        for path in deleted:
            rel = _resolved_rel(path, root)
            owner = None if rel is None else self._root_of(rel)
            if rel is not None and owner is not None:
                _prune_up_to(root, rel, owner)

    def _root_of(self, rel: PurePosixPath) -> _Root | None:
        """The deepest declared directory strictly containing ``rel``."""
        holders = [candidate for candidate in self.roots if candidate.rel in rel.parents]
        return max(holders, key=lambda holder: len(holder.rel.parts), default=None)


def _declared_roots(
    dirs: Sequence[tuple[PurePosixPath, PurePosixPath | None]],
) -> tuple[_Root, ...]:
    """Each declared directory as spelled and, through a symlink, as resolved.

    A directory is prunable only when it is real as spelled and no other declared
    directory is a symlink to it, whatever order the adapters declared them in:
    every ``_Root`` sharing a ``rel`` then agrees on ``prunable``, so the
    tie-break in :meth:`OutputLocations._root_of` cannot remove a link target.

    Example::

        >>> _declared_roots([(PurePosixPath("a"), PurePosixPath("a"))])
        (_Root(rel=PurePosixPath('a'), prunable=True),)
    """
    link_targets = {
        resolved for spelled, resolved in dirs if resolved is not None and resolved != spelled
    }
    roots: list[_Root] = []
    for spelled, resolved in dirs:
        roots.append(_Root(spelled, prunable=resolved == spelled and spelled not in link_targets))
        if resolved is not None and resolved.parts and resolved != spelled:
            roots.append(_Root(resolved, prunable=False))
    return tuple(roots)


def _resolved_rel(path: Path, root: Path) -> PurePosixPath | None:
    """``path`` (which may no longer exist) resolved, relative to ``root``; ``None`` outside."""
    try:
        return PurePosixPath(real_path(path).relative_to(root).as_posix())
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
