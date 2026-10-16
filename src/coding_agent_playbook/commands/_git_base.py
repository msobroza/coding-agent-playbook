"""The git a CLI twin runs and the base it compares against (specs/prK-hook-pack.md §F.5).

``playbook ci`` and ``playbook gate-scan`` run off-workstation, usually in CI,
so they use a **stateless** ``SafeGit`` (no hook state directory exists there)
with a CLI-sized per-call timeout. The base is ``--base`` or the default branch
(``SafeGit.default_branch``: ``origin/HEAD``, then ``main``, then ``master``),
and the compared range starts at its merge base with ``HEAD``. A shallow CI
checkout has neither, hence :data:`FETCH_DEPTH_HINT` in every such error.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.git import SafeGit
from coding_agent_playbook.hook_runtime.paths import find_repo
from coding_agent_playbook.hook_runtime.proc import SubprocessProc

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.git import GitPort

__all__ = [
    "CLI_GIT_TIMEOUT_S",
    "FETCH_DEPTH_HINT",
    "GitBaseError",
    "MergeBase",
    "open_git",
    "resolve_merge_base",
]

#: Per git call; a range diff of a large PR can outlive the hooks' 2-5 s bounds.
CLI_GIT_TIMEOUT_S: Final = 30.0
FETCH_DEPTH_HINT: Final = "in CI, check out the full history (actions/checkout with fetch-depth: 0)"


class GitBaseError(ValueError):
    """No usable repository or base revision; the twins exit 2 with this message."""


@dataclass(frozen=True, slots=True)
class MergeBase:
    """The base ref as resolved (``origin/main``) and its merge base with ``HEAD``.

    Example: ``MergeBase("origin/main", "9f2c41...")``.
    """

    ref: str
    sha: str


def open_git(repo_root: Path) -> SafeGit:
    """A stateless ``SafeGit`` for the repository holding ``repo_root``.

    Raises :class:`GitBaseError` outside a git repository.

    Example::

        >>> open_git(Path(".")).default_branch()  # doctest: +SKIP
        'origin/main'
    """
    repo = find_repo(str(repo_root))
    if repo is None:
        raise GitBaseError(f"{repo_root} is not inside a git repository")
    return SafeGit(repo, proc=SubprocessProc(), env=dict(os.environ), timeout_s=CLI_GIT_TIMEOUT_S)


def resolve_merge_base(git: GitPort, base: str | None) -> MergeBase:
    """``base`` (default: the default branch) and its merge base with ``HEAD``.

    Raises :class:`GitBaseError` when no default branch exists or the two share
    no history; ``GitError`` when git rejects ``base``.

    Example::

        >>> resolve_merge_base(git, None)  # doctest: +SKIP
        MergeBase(ref='origin/main', sha='9f2c41...')
    """
    ref = base or git.default_branch()
    if ref is None:
        raise GitBaseError(
            "cannot find the default branch (refs/remotes/origin/HEAD, main or master); "
            f"pass --base REF, or {FETCH_DEPTH_HINT}"
        )
    sha = git.merge_base(ref, "HEAD")
    if sha is None:
        raise GitBaseError(f"{ref} and HEAD share no history; {FETCH_DEPTH_HINT}")
    return MergeBase(ref, sha)
