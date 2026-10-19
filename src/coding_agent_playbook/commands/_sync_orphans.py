"""Ownership of output an earlier sync left behind (SPEC §4.2 step 9, §10.8).

The previous lockfile is the ownership record: every path it lists that the
current render did not rewrite and that still exists is an **orphan** — a
removed skill's ``SKILL.md`` and copied scripts, a script dropped from a skill
that still exists, everything a since-disabled adapter wrote. This module is
the **only** deletion policy for stale native-skill output (adapters'
``cleanup_stale`` never deletes inside a skill directory, and a file/folder
swap displaces only what :meth:`LeftoverPolicy.may_delete` approves), and it
runs under both ``[output] commit`` settings.

Write mode deletes an orphan only when that is provably safe — it lies in a
declared output location, its bytes still hash to the old lockfile entry
(pristine engine output), git does not track it, and every enabled adapter is
installed. Every other orphan is **kept**: carried forward in the new lockfile
(and, for ``commit = false``, listed in the managed ``.gitignore`` block) until
it is gone. A file the lockfile never listed is a user file and is never an
orphan, even inside an engine-owned skill directory; so is a path reached
through a symlink (the user re-pointed it since) or under ``.git/``.

"Not rewritten" and "tracked" compare **file identity** (``st_dev``/``st_ino``)
and Unicode NFC, not path spelling: after a case-only skill-id rename on a
case-insensitive filesystem the old entry ``.claude/skills/Demo/run.py`` names
the very file just written as ``.claude/skills/demo/run.py`` (not an orphan),
and git's index entry ``Demo/run.py`` tracks ``demo/run.py`` (kept).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from coding_agent_playbook._file_identity import FileSet
from coding_agent_playbook._symlinks import real_path
from coding_agent_playbook.gitignore import GITIGNORE_FILENAME, LOCKFILE_NAME

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.commands._output_locations import OutputLocations
    from coding_agent_playbook.git_client import GitClient
    from coding_agent_playbook.lockfile.model import LockEntry, Lockfile

# User/state files an orphan entry must never resolve to, whatever an old (or
# hand-edited) lockfile claims.
_NEVER_ORPHANED = frozenset(
    {
        GITIGNORE_FILENAME,
        LOCKFILE_NAME,
        ".coding-agent-playbook.toml",
        ".coding-agent-playbook.local.toml",
    }
)
_GIT_DIR = ".git"


@dataclass(frozen=True)
class OrphanPlan:
    """What write mode does with each orphan: ``delete`` it or ``keep`` owning it.

    An orphan in neither (outside every declared output location) is released:
    never deleted, no longer owned.
    """

    delete: tuple[LockEntry, ...] = ()
    keep: tuple[LockEntry, ...] = ()


def find_orphans(
    previous: Lockfile | None, written: Iterable[Path], repo_root: Path
) -> list[LockEntry]:
    """Return ``previous`` entries not rewritten by this sync that still exist on disk.

    Entries escaping ``repo_root``, crossing a symlink, under ``.git/`` or naming
    a user/state file are never orphans, and neither is a scoped
    (``json:<pointer>``) entry: its file is shared with the user and only its
    managed elements are engine-owned (specs/prK-lifecycle-hooks.md §B.6). An
    entry naming the same file as a written path (or as an earlier orphan) — a
    case variant on a case-insensitive filesystem, say — is not an orphan.

    Example::

        >>> find_orphans(None, [], Path("."))
        []
    """
    if previous is None:
        return []
    root = repo_root.resolve()
    seen = FileSet.of(written)
    orphans: list[LockEntry] = []
    for entry in previous.entries:
        path = _owned_path(root, entry.path) if entry.is_whole_file else None
        if path is None or not path.is_file() or seen.holds(path):
            continue
        seen.add(path)
        orphans.append(entry)
    return orphans


def plan_orphans(
    orphans: Sequence[LockEntry],
    repo_root: Path,
    git: GitClient,
    *,
    keep_all: bool,
    locations: OutputLocations,
) -> OrphanPlan:
    """Split ``orphans`` into deletable (in bounds + pristine + untracked) and kept.

    ``keep_all`` (an enabled adapter is missing from this environment, so its
    output cannot be judged stale) keeps every orphan. Otherwise an orphan
    outside ``locations`` is released, and git is asked about the rest only when
    there is something to decide. Git failing inside a git work tree keeps them
    all (fail closed); outside one (``None``, no ``.git``) nothing is tracked.

    Example::

        >>> plan_orphans([], Path("."), FakeGitClient(), keep_all=False, locations=...)  # doctest: +SKIP
        OrphanPlan(delete=(), keep=())
    """
    if keep_all or not orphans:
        return OrphanPlan(keep=tuple(orphans))
    candidates = [entry for entry in orphans if locations.contains(entry.path)]
    tracked = _tracked_entry_paths(candidates, repo_root, git)
    if tracked is None:
        return OrphanPlan(keep=tuple(candidates))
    delete: list[LockEntry] = []
    keep: list[LockEntry] = []
    for entry in candidates:
        safe = entry.path not in tracked and entry.matches_file(repo_root / entry.path)
        (delete if safe else keep).append(entry)
    return OrphanPlan(delete=tuple(delete), keep=tuple(keep))


def delete_orphans(
    entries: Iterable[LockEntry], repo_root: Path, locations: OutputLocations
) -> list[Path]:
    """Delete each entry's file, prune directories left empty; return the deleted paths.

    Re-checks every bound (inside the repo, no symlink, not ``.git/``, in a
    declared location) so a caller can never widen what is deleted.

    Example::

        >>> delete_orphans([], Path("."), OutputLocations.declared([], Path(".")))  # doctest: +SKIP
        []
    """
    root = repo_root.resolve()
    deleted: list[Path] = []
    for entry in entries:
        path = _owned_path(root, entry.path)
        if path is None or not locations.contains(entry.path):
            continue
        path.unlink(missing_ok=True)
        deleted.append(repo_root / entry.path)
    locations.prune_emptied(deleted, repo_root)
    return deleted


def entry_paths(entries: Iterable[LockEntry], repo_root: Path) -> list[Path]:
    """Map lockfile entries back to paths under ``repo_root``.

    Example::

        >>> entry_paths([], Path("."))
        []
    """
    return [repo_root / entry.path for entry in entries]


@dataclass
class LeftoverPolicy:
    """The one rule for deleting output an earlier sync wrote, bound to one ``sync`` run.

    ``plan`` settles orphans; ``may_delete`` judges the files a file/folder swap
    must displace (installed into the ``SkillWriter`` via
    ``skill_dirs.ownership.judging_leftovers_with``) by the very same ``plan_orphans``,
    recording approved files in ``displaced``.

    Example::

        policy = LeftoverPolicy(previous, repo_root, git, keep_all=False, locations=locations)
        plan = policy.plan(written)
        removed = policy.delete(plan.delete)
    """

    previous: Lockfile | None
    repo_root: Path
    git: GitClient
    keep_all: bool
    locations: OutputLocations
    displaced: list[Path] = field(default_factory=list)

    def plan(self, written: Iterable[Path]) -> OrphanPlan:
        """Plan the orphans this render (``written``, real-tree paths) left behind."""
        orphans = find_orphans(self.previous, written, self.repo_root)
        return self._plan(orphans)

    def delete(self, entries: Iterable[LockEntry]) -> list[Path]:
        """Delete planned orphans (see :func:`delete_orphans`)."""
        return delete_orphans(entries, self.repo_root, self.locations)

    def prune_vanished(self) -> None:
        """Prune directories left empty by earlier output that is gone — a kept
        leftover the user has since deleted, say — within the same bounds."""
        if self.previous is None:
            return
        root = self.repo_root.resolve()
        gone = []
        for entry in self.previous.entries:
            path = _owned_path(root, entry.path)
            if path is not None and not path.exists():
                gone.append(path)
        self.locations.prune_emptied(gone, self.repo_root)

    def may_delete(self, files: Sequence[Path]) -> bool:
        """Whether every one of ``files`` is a leftover the policy would delete.

        All or nothing: one unlisted (user), edited, tracked or out-of-bounds
        file — or a missing adapter — vetoes the lot.
        """
        entries = self._entries_naming(files)
        if entries is None or len(self._plan(entries).delete) != len(entries):
            return False
        self.displaced.extend(files)
        return True

    def _plan(self, orphans: Sequence[LockEntry]) -> OrphanPlan:
        return plan_orphans(
            orphans, self.repo_root, self.git, keep_all=self.keep_all, locations=self.locations
        )

    def _entries_naming(self, files: Sequence[Path]) -> list[LockEntry] | None:
        """The previous-lockfile entry of each file; ``None`` if any is unlisted."""
        if self.previous is None:
            return None
        root = self.repo_root.resolve()
        listed = {entry.path: entry for entry in self.previous.entries if entry.is_whole_file}
        entries: list[LockEntry] = []
        for path in files:
            entry = listed.get(_resolved_posix(path, root) or "")
            if entry is None or _owned_path(root, entry.path) is None:
                return None
            entries.append(entry)
        return entries


def _owned_path(root: Path, rel: str) -> Path | None:
    """``root / rel`` if output may be judged there, else ``None`` (released).

    ``None`` when ``rel`` leaves ``root``, names a user/state file, has a
    ``.git`` segment, or crosses a symlink: lockfile paths are recorded
    resolved, so a symlink on the way means the user re-pointed the path since
    (e.g. took a skill dir over by moving it and linking it back) and whatever
    it reaches now is theirs — git, too, cannot see through it.
    """
    parts = PurePosixPath(rel).parts
    if not parts or parts[-1] in _NEVER_ORPHANED:
        return None
    if any(part.casefold() == _GIT_DIR for part in parts):
        return None
    spelled = root.joinpath(*parts)
    resolved = real_path(spelled)  # Path.resolve() raises on a link loop on Python 3.12
    if resolved != spelled or root not in resolved.parents:
        return None
    return resolved


def _tracked_entry_paths(
    entries: Sequence[LockEntry], repo_root: Path, git: GitClient
) -> set[str] | None:
    """The ``entries`` paths git tracks; ``None`` when git cannot answer in a work tree.

    Asked case-insensitively and confirmed by NFC spelling (git on macOS reports
    precomposed names) or file identity (an index entry ``Demo/x`` *is*
    ``demo/x`` on a case-insensitive filesystem, and is not on a sensitive one).
    """
    if not entries:
        return set()
    answer = git.tracked_paths(repo_root, [entry.path for entry in entries], ignore_case=True)
    if answer is None:
        return None if _in_git_work_tree(repo_root) else set()
    spelled = {_nfc(path) for path in answer}
    index_files = FileSet.of(repo_root / path for path in answer)
    return {
        entry.path
        for entry in entries
        if _nfc(entry.path) in spelled or index_files.holds(repo_root / entry.path)
    }


def _in_git_work_tree(repo_root: Path) -> bool:
    """True when ``repo_root`` or an ancestor holds ``.git`` (a dir, or a worktree file)."""
    root = repo_root.resolve()
    return any((directory / _GIT_DIR).exists() for directory in (root, *root.parents))


def _resolved_posix(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def _nfc(path: str) -> str:
    return unicodedata.normalize("NFC", path)
