"""What ``playbook scan-secrets`` reads in each mode (specs/prK-hook-pack.md §E.4).

A :class:`SecretScope` is one run's input, gathered through the stateless,
hardened ``SafeGit`` (``--no-ext-diff --no-textconv``, filter drivers
neutralized), so no repository config can run code during a scan:

- ``--staged``: the index against ``HEAD`` (the ``playbook-secrets`` pre-commit entry);
- ``--range A..B``: as ``playbook gate-scan`` (CI passes ``<merge base>..HEAD``);
- ``--worktree``: tracked changes against ``HEAD`` plus untracked, non-ignored files;
- ``PATHS``: whole files, relative to ``--repo-root`` or absolute.

``base`` is the revision the pragma and the ``[guardrails]`` policy are read
at: ``HEAD`` (``None`` before the first commit), or the range's base.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands.twins._git_scope import resolve_range
from coding_agent_playbook.hook_runtime._git_parse import AddedLine, parse_diff_lines, split_z
from coding_agent_playbook.hook_runtime.git_range import PATCH_FLAGS, checked_rev

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime.git import SafeGit

__all__ = ["SecretScope", "paths_scope", "range_scope", "staged_scope", "worktree_scope"]

#: Paths a change adds, copies or modifies; a rename counts as an add (``--no-renames``).
_NAME_ONLY: Final = ("--name-only", "-z", "--no-renames", "--diff-filter=ACM")


@dataclass(frozen=True, slots=True)
class SecretScope:
    """One run's input: added diff lines, changed tracked paths, whole files to read.

    ``changed`` paths are classified by name only (a credential file is never
    read); ``files`` (untracked files or PATHS) are read from the working tree.

    Example: ``SecretScope("staged", "HEAD", added=(...), changed=("src/a.py",))``.
    """

    label: str
    base: str | None
    added: tuple[AddedLine, ...] = ()
    changed: tuple[str, ...] = ()
    files: tuple[str, ...] = ()


def staged_scope(git: SafeGit) -> SecretScope:
    """The index against ``HEAD`` (or the empty tree before the first commit).

    Example::

        >>> staged_scope(git).label  # doctest: +SKIP
        'staged'
    """
    added = parse_diff_lines(git.run(["diff", "--cached", *PATCH_FLAGS]).stdout).added
    return SecretScope("staged", _head(git), added, _names(git, "--cached"))


def range_scope(git: SafeGit, text: str | None) -> SecretScope:
    """``A..B`` / ``A...B`` (``resolve_range``); ``None`` is ``<merge base>..HEAD``.

    Example::

        >>> range_scope(git, "HEAD~1..HEAD").base  # doctest: +SKIP
        'HEAD~1'
    """
    span = resolve_range(git, text)
    added = git.diff_range(span.base, span.head).added
    changed = _names(git, checked_rev(span.base), checked_rev(span.head))
    return SecretScope(span.label, span.base, added, changed)


def worktree_scope(git: SafeGit) -> SecretScope:
    """Tracked changes against ``HEAD`` plus every untracked, non-ignored file.

    Example::

        >>> worktree_scope(git).files  # doctest: +SKIP
        ('.env.prod', 'notes/todo.py')
    """
    base = _head(git)
    # Before the first commit every tracked (staged) file is new.
    changed = split_z(git.run(["ls-files", "-z"]).stdout) if base is None else _names(git, base)
    return SecretScope("worktree", base, git.diff_added(), changed, git.ls_untracked())


def paths_scope(git: SafeGit, paths: Sequence[str], cwd: Path) -> SecretScope:
    """Whole files: each of ``paths`` relative to ``cwd`` (or absolute), named repo-relative.

    Raises ``ValueError`` naming a path that is not a file. A path outside the
    repository keeps its absolute spelling.

    Example::

        >>> paths_scope(git, ["src/a.py"], Path(".")).files  # doctest: +SKIP
        ('src/a.py',)
    """
    root = Path(git.repo.worktree_root)
    files: list[str] = []
    for raw in paths:
        full = Path(os.path.normpath(cwd / raw))
        if not (full.is_file() or full.is_symlink()):
            raise ValueError(f"{raw}: not a file (pass files, or use --worktree)")
        rel = os.path.relpath(full, root)
        files.append(str(full) if rel.startswith("..") else Path(rel).as_posix())
    return SecretScope("paths", _head(git), files=tuple(files))


def _head(git: SafeGit) -> str | None:
    return "HEAD" if git.head_tree() is not None else None


def _names(git: SafeGit, *revs: str) -> tuple[str, ...]:
    return split_z(git.run(["diff", *revs, *_NAME_ONLY]).stdout)
