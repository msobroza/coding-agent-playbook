"""The committer-date cut-over of commit-convention range checks (addendum D-Q3; specs/prK-hook-pack.md §F.4).

``[hooks.commit_convention] cutover_date = "YYYY-MM-DD"`` grandfathers legacy
history: a range check (commit-message-convention's push scan, the ``playbook
ci`` ``commit-convention`` step) lints only the commits whose **committer**
date is on or after it, so a commit rewritten later (rebase, amend: a new
committer date) must conform while old ones are left alone. Unset, every
commit is checked. A single new commit (the ``pre_tool_use`` commit check, the
commit-msg twin) is always checked.

:func:`plan_cz_checks` turns a range's commits into what to ask ``cz check``.
A single ``--rev-range`` is used only when it names exactly the kept commits:

- every commit kept: one ``--rev-range <base>..<head>``, the range just listed;
- the kept commits are a linear tail (``head`` back through single parents,
  no merge): one ``--rev-range <oldest kept>^..<head>``;
- otherwise ``--message`` per kept commit, at most ``max_messages``, with a
  note naming how many more CI checks.

A merge among the kept commits rules the tail range out: ``<oldest kept>^``
does not exclude what the merge brought in, so a branch that merged main
would have ``cz`` check main's own commits, which ``<base>..<head>`` excludes
(PR #32: main's non-conventional squash subjects failed the CI step).

Pure and stdlib-only, so the hook (hot path: no ``tomllib``, no evaluators)
and the CI step share it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime.git.log import LoggedCommit

__all__ = ["MAX_MESSAGES", "CzPlan", "committed_since", "parse_cutover", "plan_cz_checks"]

#: Per-commit ``cz check --message`` calls one range check may make (§F.4.2).
MAX_MESSAGES: Final = 20


@dataclass(frozen=True, slots=True)
class CzPlan:
    """The ``cz check`` calls one range needs: one ``rev_range``, per-commit ``commits``, or none.

    ``commits`` are oldest first; ``note`` says how many kept commits were not
    checked here (CI checks the whole range).

    Example::

        >>> CzPlan(rev_range="origin/main..HEAD").empty
        False
    """

    rev_range: str | None = None
    commits: tuple[LoggedCommit, ...] = ()
    note: str = ""

    @property
    def empty(self) -> bool:
        """Nothing to check: every commit predates the cut-over."""
        return self.rev_range is None and not self.commits


def parse_cutover(value: object) -> date | None:
    """``cutover_date`` as a date; ``None`` when unset or empty.

    Raises ``ValueError`` naming the value when it is not ``"YYYY-MM-DD"``.

    Example::

        >>> parse_cutover("2026-10-15"), parse_cutover("")
        (datetime.date(2026, 10, 15), None)
    """
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"cutover_date must be a 'YYYY-MM-DD' string, got {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"cutover_date must be a 'YYYY-MM-DD' string, got {value!r}") from None


def committed_since(committed: str, cutover: date | None) -> bool:
    """Whether a ``%cI`` committer date falls on or after ``cutover`` (its own UTC offset's day).

    An unparsable date counts as new: a commit is never skipped by mistake.

    Example::

        >>> committed_since("2026-10-14T23:30:00-07:00", date(2026, 10, 15))
        False
    """
    if cutover is None:
        return True
    try:
        return datetime.fromisoformat(committed).date() >= cutover
    except ValueError:
        return True


def plan_cz_checks(
    commits: Sequence[LoggedCommit],
    cutover: date | None,
    *,
    base: str,
    head: str = "HEAD",
    truncated: bool = False,
    max_messages: int = MAX_MESSAGES,
) -> CzPlan:
    """What to ask ``cz check`` about ``commits`` (``git log <base>..<head>``, newest first).

    ``truncated`` says the log stopped at its limit, so "every commit kept"
    cannot vouch for the commits beyond it: a linear tail then starts the
    range at the oldest kept commit instead of ``base``.

    Example::

        >>> plan_cz_checks([], None, base="origin/main").empty
        True
    """
    kept = [commit for commit in commits if committed_since(commit.committed, cutover)]
    if not kept:
        return CzPlan()
    if len(kept) == len(commits) and not truncated:
        return CzPlan(rev_range=f"{base}..{head}")
    if _is_linear_tail(commits, kept):
        return CzPlan(rev_range=f"{kept[-1].sha}^..{head}")
    oldest_first = tuple(reversed(kept))
    extra = len(oldest_first) - max_messages
    note = (
        f"{extra} more commits after the cut-over are not checked here; CI checks the full range"
        if extra > 0
        else ""
    )
    return CzPlan(commits=oldest_first[:max_messages], note=note)


def _is_linear_tail(commits: Sequence[LoggedCommit], kept: Sequence[LoggedCommit]) -> bool:
    """Whether ``<oldest kept>^..<head>`` names exactly ``kept``.

    ``git log <base>..<head>`` lists ``head`` first, so ``kept`` must open the
    listing and each kept commit must have one parent: the next kept commit,
    then the oldest one's parent, where the range stops. A merge, a root commit
    or a commit whose parent is not the next kept one (a backdated commit in
    between) fails.
    """
    if list(commits[: len(kept)]) != list(kept):
        return False
    if any(len(commit.parents) != 1 for commit in kept):
        return False
    return all(newer.parents[0] == older.sha for newer, older in pairwise(kept))
