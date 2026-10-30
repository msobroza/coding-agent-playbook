"""The release pull request's ``Release metrics`` section (spec D3/D4).

``scripts/release.py prepare --eval`` puts it into the body after the notes:
one line per target (its mode, as ``scripts/release_eval_mode.py`` names it,
its scores and its regression check, with the check's notes), then the release
report of ``coding_agent_playbook.evals.release_report`` for the version, cut
at a section boundary to leave room for the rest of the body.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.release_report import (
    ReleaseReportError,
    load_history,
    release_report,
)
from coding_agent_playbook.release.manifest import RELEASES_DIRNAME
from release_eval_mode import changed_only_mode
from release_tools import ReleaseError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from release_eval import TargetMetrics

#: The report's share of the PR body: GitHub caps a body at 65,536 characters.
PR_REPORT_LIMIT: Final = 60_000
_CATALOG: Final = "catalog"


def metrics_body(outcomes: Sequence[TargetMetrics], *, checkout: Path, version: str) -> str:
    """The PR body's ``Release metrics`` section: one line per target, then the report (D3/D4).

    The report reads every metrics file under the checkout's releases directory,
    ``version``'s among them, so they must be written first.

    Example::

        >>> metrics_body(outcomes, checkout=Path("."), version="9.9.9")  # doctest: +SKIP
        '## Release metrics\\n\\n- `claude-opus`: 2 samples (full run), ...'
    """
    lines = ["## Release metrics", ""]
    for outcome in outcomes:
        lines.append(f"- `{outcome.name}`: {_summary_line(outcome)}")
        if outcome.check is not None:
            lines += [f"  - note: {note}" for note in outcome.check.notes]
    try:
        history = load_history(checkout / _CATALOG / RELEASES_DIRNAME)
        report = release_report(history, version).markdown(limit=PR_REPORT_LIMIT)
    except ReleaseReportError as exc:
        raise ReleaseError(f"--eval: the release report: {exc}") from exc
    return "\n".join(lines) + "\n\n" + report


def _summary_line(outcome: TargetMetrics) -> str:
    summary = outcome.metrics.get("summary")
    facts = summary if isinstance(summary, dict) else {}
    line = (
        f"{facts.get('samples')} samples ({_mode(outcome)}), "
        f"pass rate {facts.get('pass_rate')}, mean score {facts.get('mean_score')}"
    )
    check = outcome.check
    if check is None:
        return f"{line}; no previous release metrics to compare with"
    return (
        f"{line}; vs {check.previous}: {check.count('regression')} regressions "
        f"({check.accepted_regressions} accepted), {check.count('improvement')} improvements, "
        f"{check.count('not_comparable')} not comparable"
    )


def _mode(outcome: TargetMetrics) -> str:
    """``changed-only: N rerun, M carried[, R rejudged] (K compared with <previous>)``, or ``full run``."""
    if not outcome.changed_only:
        return "full run"
    reason = outcome.full_rerun_reason
    return changed_only_mode(outcome.metrics, full_rerun_reason=reason, check=outcome.check)
