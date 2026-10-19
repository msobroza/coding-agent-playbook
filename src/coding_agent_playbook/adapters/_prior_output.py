"""What the previous ``playbook sync`` provably wrote, per its lockfile (SPEC §10.8).

The :class:`~coding_agent_playbook.adapters._skill_writer.SkillWriter` only ever
claims or removes something to make room for its own output when that is
provably engine output it may replace:

- a sentinel-less (pre-v0.15) skill dir is re-claimed only through a ``SKILL.md``
  the lockfile lists **and** whose bytes still hash to that entry — an edited one
  (a user who adopted a leftover, or stripped the sentinel) is the user's;
- a file/folder swap displaces only files the one leftover policy (SPEC §4.2
  step 9) would delete — listed, unchanged, untracked, every adapter installed.
  ``playbook sync`` installs that policy around its write-mode render
  (:func:`judging_leftovers_with`); with none installed nothing is displaced.

A file the lockfile does not list is a user file and is never deleted.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Iterator, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook.lockfile import LockEntry

#: Decides whether files an earlier sync wrote may be deleted (all or nothing).
LeftoverJudge = Callable[[Sequence[Path]], bool]

_LEFTOVER_JUDGE: ContextVar[LeftoverJudge | None] = ContextVar(
    "playbook_leftover_judge", default=None
)


@contextlib.contextmanager
def judging_leftovers_with(judge: LeftoverJudge) -> Iterator[None]:
    """Let :meth:`PriorOutput.may_displace` delete what ``judge`` approves, for this block.

    Write-mode ``playbook sync`` passes the §4.2 step 9 leftover policy, so a
    file/folder swap and an orphan are judged by the very same rule (DRY).

    Example::

        with judging_leftovers_with(policy.may_delete):
            written = adapter.write_skill(skill, repo_root)
    """
    token = _LEFTOVER_JUDGE.set(judge)
    try:
        yield
    finally:
        _LEFTOVER_JUDGE.reset(token)


@dataclass
class PriorOutput:
    """The previous sync's lockfile as proof of what the engine wrote (lazy, fail-safe).

    Consulted only on rare paths — a sentinel-less legacy skill dir, or a file
    or folder blocking a write after a file/folder swap — so the lockfile is
    loaded on first use. Any read/parse failure lists nothing: the fail-safe
    answer, since "not listed" only ever means "leave it alone".

    Example::

        prior = PriorOutput(repo_root)
        prior.wrote_unchanged(repo_root / ".claude/skills/demo/SKILL.md")  # True if pristine
    """

    repo_root: Path
    _entries: dict[str, LockEntry] | None = field(default=None, init=False, repr=False)

    def wrote_unchanged(self, path: Path) -> bool:
        """Whether the lockfile lists ``path`` and its bytes still match that entry."""
        entry = self._entry_for(path)
        return entry is not None and _is_regular_file(path) and entry.matches_file(path)

    def may_displace(self, blocker: Path) -> bool:
        """Whether ``blocker`` (a regular file, or a real dir) may be deleted for a swap.

        A symlink or special file anywhere in it vetoes the displacement, as does
        any file the installed leftover policy would keep (a user file, an edited
        or tracked one); outside ``playbook sync`` write mode nothing is displaced.
        An empty directory tree holds no data and is always displaceable.
        """
        entries = _non_dir_entries(blocker) if blocker.is_dir() else [blocker]
        if not entries:
            return True
        if not all(_is_regular_file(entry) for entry in entries):
            return False
        judge = _LEFTOVER_JUDGE.get()
        return judge is not None and judge(entries)

    def _entry_for(self, path: Path) -> LockEntry | None:
        if self._entries is None:
            self._entries = _load_lockfile_entries(self.repo_root)
        for spelling in _repo_relative_spellings(path, self.repo_root):
            entry = self._entries.get(spelling)
            if entry is not None:
                return entry
        return None


def _load_lockfile_entries(repo_root: Path) -> dict[str, LockEntry]:
    # Lazy import: sources.filesystem pulls in the whole eval-loader stack at
    # import time, and only the rare paths above need the lockfile.
    from coding_agent_playbook.config.files import FileSystemStateSource

    try:
        lockfile = FileSystemStateSource(repo_root=repo_root).load_lockfile()
    except (OSError, ValueError, KeyError, TypeError):  # TOMLDecodeError is a ValueError
        return {}
    return {} if lockfile is None else {entry.path: entry for entry in lockfile.entries}


def _repo_relative_spellings(path: Path, repo_root: Path) -> list[str]:
    """``path`` relative to ``repo_root`` as resolved (the lockfile's form) and as spelled."""
    spellings: list[str] = []
    # realpath: Path.resolve() raises on a link loop (a user's SKILL.md -> SKILL.md) on 3.12
    resolved = Path(os.path.realpath(path))
    for candidate, root in ((resolved, repo_root.resolve()), (path, repo_root)):
        with contextlib.suppress(ValueError):
            spellings.append(candidate.relative_to(root).as_posix())
    return spellings


def _non_dir_entries(top: Path) -> list[Path]:
    """Every non-directory entry under ``top`` (symlinked dirs included), never following links."""
    entries: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(top, followlinks=False):
        base = Path(dirpath)
        entries.extend(base / name for name in dirnames if (base / name).is_symlink())
        entries.extend(base / name for name in filenames)
    return entries


def _is_regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()
