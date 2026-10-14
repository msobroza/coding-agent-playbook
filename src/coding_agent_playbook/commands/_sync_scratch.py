"""Hygienic scratch copy for ``playbook sync --check`` (specs/prK-lifecycle-hooks.md §P P2(b)).

``sync --check`` renders into a temporary copy of the consumer repo so adapters
can write freely. :class:`ScratchCopyPolicy` is the ``ignore=`` callable handed
to :func:`shutil.copytree` that keeps the copy cheap and free of secrets:

- every name in :data:`SCRATCH_IGNORE_NAMES` (the detector's ``_IGNORE_DIRS``
  plus tool caches and build outputs) and every ``is_secret_path`` match is
  skipped, so ``.git``, ``.venv`` and ``.env`` never reach ``/tmp``;
- a symlink is copied as its target's content (adapters never write *through* a
  link into the real tree) only when the target exists, lies inside the repo,
  is not itself skipped and is not an ancestor directory of the link; a link
  resolving outside the repo (``-> ~/.ssh``) is skipped, never dereferenced;
- the repo-local canonical source tree ``playbook/`` is exempt from the name
  and secret rules: it is the sync's input, and pruning ``playbook/skills/build/``
  or ``playbook/rules/handling-credentials.md`` would make the scratch run render
  a different artifact set than a real sync.

The policy records every skipped path, so the lockfile-orphan check never judges
a path the scratch run could not see.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Final

from coding_agent_playbook.detector import _IGNORE_DIRS
from coding_agent_playbook.security.paths import is_secret_path

#: Directory and file names never copied into the scratch tree (outside ``playbook/``).
SCRATCH_IGNORE_NAMES: Final[frozenset[str]] = _IGNORE_DIRS | {
    ".ruff_cache",
    ".pytest_cache",
    "dist",
    "build",
}

# The repo-local canonical source tree (``FileSystemArtifactSource`` reads it).
_CANONICAL_SOURCE_DIR: Final = "playbook"


class ScratchCopyPolicy:
    """The ``ignore=`` callable for the ``sync --check`` scratch ``copytree``.

    Returns the names in a directory that must not be copied (module docstring)
    and accumulates them, repo-relative and ``/``-separated, in :attr:`skipped`.

    Example::

        policy = ScratchCopyPolicy(repo_root)
        shutil.copytree(repo_root, scratch, ignore=policy)
        policy.covers(".venv/bin/python")  # True: never copied
    """

    def __init__(self, repo_root: Path) -> None:
        self._root = Path(os.path.abspath(repo_root))
        self._real_root = self._root.resolve()
        self.skipped: set[str] = set()

    def __call__(self, directory: str, names: list[str]) -> set[str]:
        parent = Path(os.path.abspath(directory))
        ignored = {name for name in names if self._skips(parent / name)}
        self.skipped.update((parent / name).relative_to(self._root).as_posix() for name in ignored)
        return ignored

    def covers(self, rel_path: str) -> bool:
        """Whether repo-relative ``rel_path`` is a skipped path or lies under one."""
        parts = PurePosixPath(rel_path).parts
        return any("/".join(parts[: depth + 1]) in self.skipped for depth in range(len(parts)))

    def _skips(self, path: Path) -> bool:
        if path.is_symlink() and not self._link_is_copyable(path):
            return True
        return _is_excluded(path, self._root)

    def _link_is_copyable(self, link: Path) -> bool:
        """Whether ``link`` may be copied as its target's content (module docstring)."""
        target = Path(os.path.realpath(link))
        if not target.exists() or not target.is_relative_to(self._real_root):
            return False
        # A directory link to its own ancestor would make copytree recurse forever.
        if target.is_dir() and link.parent.resolve().is_relative_to(target):
            return False
        return not _is_excluded(target, self._real_root)


def _is_excluded(path: Path, root: Path) -> bool:
    """Whether ``path`` (under ``root``) is an ignored name or a secret path.

    Anything inside the canonical source tree ``playbook/`` is never excluded.
    """
    parts = path.relative_to(root).parts
    if parts[:1] == (_CANONICAL_SOURCE_DIR,):
        return False
    return any(part in SCRATCH_IGNORE_NAMES for part in parts) or is_secret_path(path)
