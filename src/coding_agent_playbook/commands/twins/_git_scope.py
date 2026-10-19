"""The git a CLI twin runs and the base it compares against (specs/prK-hook-pack.md §F.5).

``playbook ci`` and ``playbook gate-scan`` run off-workstation, usually in CI,
so they use a **stateless** ``SafeGit`` (no hook state directory exists there)
with a CLI-sized per-call timeout. The base is ``--base`` or the default branch
(``SafeGit.default_branch``: ``origin/HEAD``, then ``main``, then ``master``),
and the compared range starts at its merge base with ``HEAD``. A shallow CI
checkout has neither, hence :data:`FETCH_DEPTH_HINT` in every such error.

A twin's ``--range A..B`` / ``A...B`` resolves to a :class:`ScanRange` here
(:func:`resolve_range`), so no twin imports the gate-scan command for it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.paths import find_repo
from coding_agent_playbook.hook_runtime.dispatch.proc import SubprocessProc
from coding_agent_playbook.hook_runtime.git.safe_git import SafeGit

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.git.safe_git import GitPort

__all__ = [
    "BASE_FLAG_HELP",
    "CLI_GIT_TIMEOUT_S",
    "FETCH_DEPTH_HINT",
    "RANGE_FLAG_HELP",
    "GitBaseError",
    "MergeBase",
    "ScanRange",
    "open_git",
    "resolve_merge_base",
    "resolve_range",
]

#: Per git call; a range diff of a large PR can outlive the hooks' 2-5 s bounds.
CLI_GIT_TIMEOUT_S: Final = 30.0
FETCH_DEPTH_HINT: Final = "in CI, check out the full history (actions/checkout with fetch-depth: 0)"
#: The ``--base`` help of the twins that compare against a base (:func:`resolve_merge_base`).
BASE_FLAG_HELP: Final = "base ref (default: the default branch, origin/HEAD first)"
#: The ``--range`` help of the twins that scan a range (:func:`resolve_range`).
RANGE_FLAG_HELP: Final = "A..B, or A...B from their merge base (default: <merge-base>..HEAD)"


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


@dataclass(frozen=True, slots=True)
class ScanRange:
    """The revisions a scan diffs (``base`` to ``head``) and how to name the range.

    Example: ``ScanRange("HEAD~1", "HEAD", "HEAD~1..HEAD")``.
    """

    base: str
    head: str
    label: str


def resolve_range(git: GitPort, text: str | None) -> ScanRange:
    """``A..B``, ``A...B`` (from their merge base) or, for ``None``, the default range.

    An empty side means ``HEAD``. Raises ``ValueError`` for any other form.

    Example::

        >>> resolve_range(git, "HEAD~1..HEAD")  # doctest: +SKIP
        ScanRange(base='HEAD~1', head='HEAD', label='HEAD~1..HEAD')
    """
    if text is None:
        base = resolve_merge_base(git, None)
        return ScanRange(base.sha, "HEAD", f"{base.sha[:12]}..HEAD")
    if "..." in text:
        left, _, right = text.partition("...")
        head = right or "HEAD"
        return ScanRange(_symmetric_base(git, left or "HEAD", head), head, text)
    if ".." in text:
        left, _, right = text.partition("..")
        return ScanRange(left or "HEAD", right or "HEAD", text)
    raise ValueError(f"--range {text!r}: expected A..B or A...B (revisions)")


def _symmetric_base(git: GitPort, left: str, right: str) -> str:
    sha = git.merge_base(left, right)
    if sha is None:
        raise ValueError(f"--range {left}...{right}: the two share no history")
    return sha
