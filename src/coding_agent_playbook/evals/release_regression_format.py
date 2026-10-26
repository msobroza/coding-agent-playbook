"""Render a :class:`~coding_agent_playbook.evals.release_regression.RegressionCheck` (ticket 08).

A table by default (``playbook eval --check-regressions``), a stable JSON object
with ``--format json``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evals.release_regression import verdict_to_dict

if TYPE_CHECKING:
    from coding_agent_playbook.evals.release_regression import RegressionCheck, SampleVerdict

_HEADER = ("sample", "previous", "new", "delta", "verdict")


def format_regression_table(check: RegressionCheck) -> str:
    """One line per sample between the setup line, the notes, the warnings and the tally.

    Example::

        >>> format_regression_table(check).splitlines()[-1]  # doctest: +SKIP
        '0 regressions (0 accepted), 1 improvement, 0 not comparable: ok'
    """
    rows = [_HEADER, *(_cells(verdict) for verdict in check.samples)]
    widths = [max(len(row[i]) for row in rows) for i in range(len(_HEADER) - 1)]
    lines = [f"release {check.release} vs {check.previous} on target {check.target!r}"]
    lines += [f"note: {note}" for note in check.notes]
    lines += [
        "  ".join([*(cell.ljust(width) for cell, width in zip(row, widths, strict=False)), row[-1]])
        for row in rows
    ]
    lines += [
        f"warning: {verdict.sample_id}: {warning}"
        for verdict in check.samples
        for warning in verdict.warnings
    ]
    lines.append(_tally(check))
    return "\n".join(lines)


def regression_check_to_dict(check: RegressionCheck) -> dict[str, object]:
    """The JSON view: release, previous, target, blocked, counts, notes and each sample.

    Example::

        >>> regression_check_to_dict(check)["blocked"]  # doctest: +SKIP
        False
    """
    return {
        "release": check.release,
        "previous": check.previous,
        "target": check.target,
        "blocked": check.blocked,
        "regressions": check.count("regression"),
        "accepted_regressions": check.accepted_regressions,
        "improvements": check.count("improvement"),
        "not_comparable": check.count("not_comparable"),
        "notes": list(check.notes),
        "samples": [verdict_to_dict(verdict) for verdict in check.samples],
    }


def _cells(verdict: SampleVerdict) -> tuple[str, ...]:
    previous = "-" if verdict.previous_mean is None else f"{verdict.previous_mean:.3f}"
    delta = "-" if verdict.delta is None else f"{verdict.delta:+.3f}"
    return (verdict.sample_id, previous, f"{verdict.mean:.3f}", delta, _verdict_cell(verdict))


def _verdict_cell(verdict: SampleVerdict) -> str:
    reasons = "; ".join(verdict.reasons)
    if verdict.status == "regression":
        accepted = f" (accepted: {verdict.accepted})" if verdict.accepted else ""
        return f"REGRESSION: {reasons}{accepted}"
    return f"{verdict.status}: {reasons}" if reasons else verdict.status


def _tally(check: RegressionCheck) -> str:
    regressions = check.count("regression")
    improvements = check.count("improvement")
    counts = (
        f"{regressions} regression{'' if regressions == 1 else 's'} "
        f"({check.accepted_regressions} accepted), "
        f"{improvements} improvement{'' if improvements == 1 else 's'}, "
        f"{check.count('not_comparable')} not comparable"
    )
    return f"{counts}: {'BLOCKED' if check.blocked else 'ok'}"
