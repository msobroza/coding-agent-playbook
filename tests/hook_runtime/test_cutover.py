"""The committer-date cut-over of commit-convention range checks (addendum D-Q3, specs/prK-hook-pack.md §F.4).

``plan_cz_checks`` is pure: the commits arrive as ``git log`` lists them,
newest first, and the plan says which ``cz check`` calls cover the ones
committed on or after ``cutover_date``.
"""

from __future__ import annotations

from datetime import date
from typing import Final

import pytest

from coding_agent_playbook.hook_runtime.cutover import (
    CzPlan,
    committed_since,
    parse_cutover,
    plan_cz_checks,
)
from coding_agent_playbook.hook_runtime.git_log import LoggedCommit, parse_commit_log

CUTOVER: Final = date(2026, 10, 15)
NEW: Final = "2026-10-16T09:00:00+02:00"
OLD: Final = "2026-09-01T09:00:00+02:00"


def _log(*dates: str) -> list[LoggedCommit]:
    """Commits ``c0`` (newest) .. ``cN`` (oldest) with the given committer dates."""
    return [LoggedCommit(f"c{n}", when, f"msg {n}\n") for n, when in enumerate(dates)]


def test_unset_cutover_checks_whole_range() -> None:
    plan = plan_cz_checks(_log(OLD, OLD, NEW), None, base="origin/main")

    assert plan == CzPlan(rev_range="origin/main..HEAD")


def test_every_commit_after_the_cutover_checks_the_whole_range() -> None:
    assert plan_cz_checks(_log(NEW, NEW), CUTOVER, base="mb") == CzPlan(rev_range="mb..HEAD")


def test_contiguous_tail_uses_rev_range() -> None:
    """Only the newest commits are past the cut-over: one range from the oldest kept one."""
    plan = plan_cz_checks(_log(NEW, NEW, OLD, OLD), CUTOVER, base="mb")

    assert plan == CzPlan(rev_range="c1^..HEAD")


def test_non_contiguous_uses_per_message() -> None:
    plan = plan_cz_checks(_log(NEW, OLD, NEW, OLD), CUTOVER, base="mb")

    assert [commit.sha for commit in plan.commits] == ["c2", "c0"]  # oldest first
    assert (plan.rev_range, plan.note) == (None, "")


def test_over_20_kept_emits_note() -> None:
    commits = _log(OLD, *([NEW, OLD] * 22))

    plan = plan_cz_checks(commits, CUTOVER, base="mb")

    assert len(plan.commits) == 20
    assert plan.note == (
        "2 more commits after the cut-over are not checked here; CI checks the full range"
    )


def test_rebased_commit_new_committer_date_counts() -> None:
    """A commit authored long ago but rebased after the cut-over has a new committer date."""
    rebased = LoggedCommit("c0", "2026-10-20T10:00:00Z", "Old style subject\n")

    plan = plan_cz_checks([rebased, *_log(OLD)[0:1]], CUTOVER, base="mb")

    assert plan == CzPlan(rev_range="c0^..HEAD")


def test_nothing_after_the_cutover_checks_nothing() -> None:
    assert plan_cz_checks(_log(OLD, OLD), CUTOVER, base="mb").empty


def test_truncated_log_never_claims_the_whole_range() -> None:
    plan = plan_cz_checks(_log(NEW, NEW), CUTOVER, base="mb", truncated=True)

    assert plan == CzPlan(rev_range="c1^..HEAD")


@pytest.mark.parametrize(
    ("committed", "since"),
    [
        ("2026-10-15T00:00:00+02:00", True),
        ("2026-10-14T23:30:00-07:00", False),  # its own day, not UTC's
        ("not a date", True),  # unparsable: checked, never skipped
    ],
)
def test_committed_since_reads_the_committer_day(committed: str, since: bool) -> None:
    assert committed_since(committed, CUTOVER) is since


@pytest.mark.parametrize("value", ["2026/10/15", "15-10-2026", 20261015])
def test_parse_cutover_rejects_other_shapes_naming_the_value(value: object) -> None:
    with pytest.raises(ValueError, match=repr(value)):
        parse_cutover(value)


def test_parse_commit_log_reads_sha_date_and_message() -> None:
    output = b"aa\x1f2026-10-16T09:00:00+02:00\x1ffeat: x\n\nbody\n\x00\nbb\x1f2026-09-01T09:00:00Z\x1ffix\n\x00"

    assert parse_commit_log(output) == (
        LoggedCommit("aa", "2026-10-16T09:00:00+02:00", "feat: x\n\nbody\n"),
        LoggedCommit("bb", "2026-09-01T09:00:00Z", "fix\n"),
    )
