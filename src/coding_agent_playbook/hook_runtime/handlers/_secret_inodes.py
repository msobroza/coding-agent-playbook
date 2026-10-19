"""The secret-inode index of secrets-path-guard (specs/prK-hook-pack.md §E.4).

A hard link gives a credential file a second, innocent name (``ln .env
notes.txt``) that no path glob sees, while uv hard-links every ``.venv``
install, so ``st_nlink > 1`` alone cannot ask. The guard asks only when the
linked file's ``(st_dev, st_ino)`` is one of a secret file's:

- the index holds the inode of every file the path policy names: in the
  worktree (a walk that never enters ``WALK_SKIP_DIRS`` and stops at 50 ms or
  20,000 entries, then is ``complete = False``) and the literal ``~/`` files
  and directories of the catalog (``~/.ssh/*``, ``~/.aws/*``, ...);
- it is built lazily, on the first hard link of a session, and kept in the
  session's state; a lookup miss rebuilds it once it is a minute old, so a
  link made after the build is still caught.

Path-only for secrets: files are ``lstat``-ed, never opened. A private module.
"""

from __future__ import annotations

import os
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.state.store import StateUnavailable, session_key
from coding_agent_playbook.security.patterns import WALK_SKIP_DIRS

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from coding_agent_playbook.hook_runtime.deps import Clock
    from coding_agent_playbook.hook_runtime.state.store import StateStore
    from coding_agent_playbook.security.paths import PathPolicy

__all__ = [
    "INDEX_TTL_S",
    "MAX_WALK_ENTRIES",
    "WALK_BUDGET_S",
    "InodeIndex",
    "build_inode_index",
    "inode_of",
    "is_secret_inode",
]

WALK_BUDGET_S: Final = 0.05
MAX_WALK_ENTRIES: Final = 20_000
#: A lookup miss rebuilds an index older than this.
INDEX_TTL_S: Final = 60.0
#: The stored list is capped: a repository rarely holds more than a handful of secrets.
MAX_STORED_INODES: Final = 4096
_DOCUMENT: Final = "secret-inodes.json"
_HOME: Final = "~/"
_MAGIC: Final = frozenset("*?[")

type Inode = tuple[int, int]


@dataclass(frozen=True, slots=True)
class InodeIndex:
    """The ``(st_dev, st_ino)`` of every secret file found, and whether the walk finished.

    Example: ``InodeIndex(frozenset({(16777234, 912)}), complete=True, built_at=1.0)``.
    """

    inodes: frozenset[Inode]
    complete: bool
    built_at: float


@dataclass(slots=True)
class _Walk:
    """A bounded walk of one worktree; ``complete`` turns False when a bound stops it."""

    clock: Clock
    deadline: float
    max_entries: int
    seen: int = 0
    complete: bool = True
    stack: list[str] = field(default_factory=list)

    def files(self, root: str) -> Iterator[os.DirEntry[str]]:
        """Every regular file under ``root``, depth-first, skipping ``WALK_SKIP_DIRS``."""
        self.stack.append(root)
        while self.stack:
            for entry in _entries(self.stack.pop()):
                if not self._step():
                    return
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in WALK_SKIP_DIRS:
                        self.stack.append(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    yield entry

    def _step(self) -> bool:
        self.seen += 1
        if self.seen > self.max_entries or self.clock.monotonic() > self.deadline:
            self.complete = False
        return self.complete


def build_inode_index(
    root: str,
    policy: PathPolicy,
    *,
    home: str,
    platform: str,
    clock: Clock,
    budget_s: float = WALK_BUDGET_S,
    max_entries: int = MAX_WALK_ENTRIES,
) -> InodeIndex:
    """Index the secret files of the worktree at ``root`` and of ``home`` (module docstring).

    Example::

        >>> build_inode_index("/repo", PathPolicy(), home="/h", platform="linux",
        ...                   clock=SystemClock()).complete  # doctest: +SKIP
        True
    """
    walk = _Walk(clock, clock.monotonic() + budget_s, max_entries)
    found: set[Inode] = set()
    for entry in walk.files(root):
        rel = os.path.relpath(entry.path, root).replace(os.sep, "/")
        if policy.matches(rel, home=home, platform=platform):
            found.update(_inode(entry.path))
    for path in _home_files(policy, home):
        found.update(_inode(path))
    return InodeIndex(frozenset(found), walk.complete, clock.time())


def inode_of(path: str) -> Inode | None:
    """``(st_dev, st_ino)`` of the file ``path`` names (links followed), else ``None``.

    Example: ``inode_of("/no/such/file") is None``.
    """
    found = _inode(path, follow=True)
    return found[0] if found else None


def is_secret_inode(
    inode: Inode,
    store: StateStore,
    session_id: str,
    build: Callable[[], InodeIndex],
    *,
    clock: Clock,
) -> bool:
    """Whether ``inode`` is a secret file's: the session's index, rebuilt when stale.

    ``build`` makes a fresh index; it runs when none is stored, or on a miss
    when the stored one is :data:`INDEX_TTL_S` old. Stateless, it builds every time.

    Example::

        >>> is_secret_inode((1, 2), store, "s1", lambda: index, clock=clock)  # doctest: +SKIP
        False
    """
    rel = f"sessions/{session_key(session_id)}/{_DOCUMENT}"
    stored = _load(store, rel)
    if stored is not None and (
        inode in stored.inodes or clock.time() - stored.built_at < INDEX_TTL_S
    ):
        return inode in stored.inodes
    fresh = build()
    _save(store, rel, fresh)
    return inode in fresh.inodes


def _home_files(policy: PathPolicy, home: str) -> Iterator[str]:
    """The literal ``~/`` files of the policy, and the files of its literal ``~/<dir>/**``."""
    for glob in policy.deny:
        if not glob.startswith(_HOME):
            continue
        rel = glob[len(_HOME) :]
        if rel.endswith("/**") and not _MAGIC.intersection(rel[:-3]):
            directory = os.path.join(home, rel[:-3])
            yield from (e.path for e in _entries(directory) if e.is_file(follow_symlinks=False))
        elif not _MAGIC.intersection(rel):
            yield os.path.join(home, rel)


def _entries(directory: str) -> list[os.DirEntry[str]]:
    try:
        with os.scandir(directory) as found:
            return list(found)
    except OSError:
        return []


def _inode(path: str, *, follow: bool = False) -> list[Inode]:
    try:
        status = os.stat(path) if follow else os.lstat(path)
    except OSError:
        return []
    return [(status.st_dev, status.st_ino)]


def _load(store: StateStore, rel: str) -> InodeIndex | None:
    try:
        document = store.read_json(rel)
    except StateUnavailable:
        return None
    raw, built = document.get("inodes"), document.get("built_at")
    if not isinstance(raw, list) or not isinstance(built, int | float):
        return None
    inodes = frozenset(
        (pair[0], pair[1])
        for pair in raw
        if isinstance(pair, list) and len(pair) == 2 and all(type(n) is int for n in pair)
    )
    return InodeIndex(inodes, document.get("complete") is True, float(built))


def _save(store: StateStore, rel: str, index: InodeIndex) -> None:
    pairs = [list(pair) for pair in sorted(index.inodes)[:MAX_STORED_INODES]]
    document = {"built_at": index.built_at, "complete": index.complete, "inodes": pairs}
    with suppress(StateUnavailable):
        store.write_json(rel, document)
