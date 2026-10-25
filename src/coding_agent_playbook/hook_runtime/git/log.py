"""``SafeGit``'s commit-log query: who committed what, when (specs/prK-hook-pack.md §F.4.2, §F.5).

commit-message-convention's push scan and the ``playbook ci``
``commit-convention`` step read the commits of a range with their
**committer** date and message, so D-Q3's cut-over (``cutover_date``) can
grandfather legacy history while a rebased or amended commit (a new committer
date) still has to conform. The parents say whether one ``cz check --rev-range``
covers exactly the kept commits (``hook_runtime.judges.commit_cutover``). One ``git log -z``
call gives every field; it reads no worktree content, and ``SafeGit.run`` adds
the hardening flags. ``range_paths`` lists the paths a range changes (the
step's release-title rule reads them).

:class:`LogQueries` is a mixin of ``SafeGit`` beside ``range``'s
``RangeQueries`` (each stays under §D.1's 300-line module rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from coding_agent_playbook.hook_runtime.git.parse import split_z
from coding_agent_playbook.hook_runtime.git.range import checked_rev

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime.dispatch.proc import ProcResult

__all__ = ["LOG_FORMAT", "LogPort", "LogQueries", "LoggedCommit", "parse_commit_log"]

#: ``%H %P`` sha and space-separated parents, ``%cI`` strict ISO 8601 committer
#: date, ``%B`` raw message, unit-separated.
LOG_FORMAT: Final = "--format=%H %P%x1f%cI%x1f%B"
_FIELD: Final = "\x1f"


@dataclass(frozen=True, slots=True)
class LoggedCommit:
    """One commit of a range: its sha, committer date (``%cI``), raw message and parents.

    ``parents`` lists the first parent first: two or more for a merge, none for
    a root commit (or a log read without them).

    Example: ``LoggedCommit("9f2c...", "2026-10-15T09:12:00+02:00", "feat: x\\n", ("41ab...",))``.
    """

    sha: str
    committed: str
    message: str
    parents: tuple[str, ...] = ()


class LogPort(Protocol):
    """The commit-log query of ``GitPort``; ``FakeGit`` scripts it."""

    def commit_log(self, rev_range: str, *, limit: int) -> tuple[LoggedCommit, ...]: ...

    def range_paths(self, base: str, head: str) -> tuple[str, ...]: ...


class _Runner(Protocol):
    """The part of ``SafeGit`` the mixin calls (the mixin's self-type)."""

    def run(
        self,
        args: Sequence[str],
        *,
        input: bytes | None = None,
        index_file: str | None = None,
        ok_codes: tuple[int, ...] = (0,),
    ) -> ProcResult: ...


class LogQueries:
    """``SafeGit``'s :class:`LogPort` implementation (a mixin over ``run``).

    Example::

        >>> git.commit_log("origin/main..HEAD", limit=200)[0].committed  # doctest: +SKIP
        '2026-10-15T09:12:00+02:00'
    """

    def commit_log(self: _Runner, rev_range: str, *, limit: int) -> tuple[LoggedCommit, ...]:
        """The newest ``limit`` commits of ``rev_range`` (``a..b``), newest first."""
        argv = ["log", "-z", f"--max-count={max(limit, 0)}", LOG_FORMAT, checked_rev(rev_range)]
        return parse_commit_log(self.run(argv).stdout)

    def range_paths(self: _Runner, base: str, head: str) -> tuple[str, ...]:
        """Every path ``base`` → ``head`` adds, changes or deletes (a rename: both paths)."""
        argv = ["diff", "--name-only", "-z", "--no-renames", checked_rev(base), checked_rev(head)]
        return split_z(self.run(argv).stdout)


def parse_commit_log(output: bytes) -> tuple[LoggedCommit, ...]:
    """The commits of a ``git log -z`` run with :data:`LOG_FORMAT`; malformed records are dropped.

    Example::

        >>> parse_commit_log(b"ab cd\\x1f2026-10-15T09:00:00Z\\x1ffeat: x\\n\\x00")[0].parents
        ('cd',)
    """
    records = output.decode("utf-8", errors="replace").split("\x00")
    return tuple(commit for commit in map(_logged_commit, records) if commit is not None)


def _logged_commit(record: str) -> LoggedCommit | None:
    """One :data:`LOG_FORMAT` record; ``None`` when it lacks a sha or a date."""
    parts = record.lstrip("\n").split(_FIELD, 2)
    ids = parts[0].split()
    if len(parts) != 3 or not ids or not parts[1]:
        return None
    return LoggedCommit(ids[0], parts[1], parts[2], tuple(ids[1:]))
