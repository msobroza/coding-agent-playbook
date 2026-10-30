"""How closely a new judge agrees with the old one on the same stored answers (spec D10).

A record that re-judges stored runs (D9) pairs each re-graded run's old and new
rubric verdict and weighted rubric score (both re-scored by ``evals.rejudge``)
into an :class:`AgreementRun`. :func:`judge_change` folds them into the metrics
file's ``judge_change``: the share of runs whose verdict is the same and the
mean absolute score difference, overall and per task. It is measured and
reported, never gated. :func:`agreement_line` is the line the record prints.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

#: Rounding of the agreement values, as the metrics file's other values.
_DIGITS: Final = 6


@dataclass(frozen=True)
class AgreementRun:
    """One re-judged run of a ``task``: the old and new rubric verdict and weighted score."""

    task: str
    old_passed: bool
    new_passed: bool
    old_score: float
    new_score: float


def judge_change(
    runs: Sequence[AgreementRun],
    *,
    old: Sequence[Mapping[str, object]],
    new: Mapping[str, object],
) -> dict[str, object] | None:
    """The metrics file's ``judge_change`` over ``runs``; ``None`` without a run.

    ``from`` lists the distinct ``old`` judge parts in a stable order: one record
    can re-judge entries graded by different judges.

    Example::

        >>> judge_change([AgreementRun("t", True, False, 0.6, 0.4)], old=[{}], new={})["runs"]
        1
    """
    if not runs:
        return None
    by_task: dict[str, list[AgreementRun]] = defaultdict(list)
    for run in runs:
        by_task[run.task].append(run)
    return {
        "from": _distinct(old),
        "to": dict(new),
        **_agreement(runs),
        "tasks": {task: _agreement(by_task[task]) for task in sorted(by_task)},
    }


def agreement_line(change: Mapping[str, object]) -> str:
    """The line a record prints for ``change`` (a :func:`judge_change` result).

    Example::

        >>> agreement_line({"from": [{"judge_model": "a"}], "to": {"judge_model": "b"},
        ...                 "runs": 4, "pass_agreement": 0.75, "mean_abs_score_diff": 0.1})
        'judge change: a -> b: pass agreement 75% over 4 runs, mean |Δ| 0.10'
    """
    olds, new = change.get("from"), change.get("to")
    if not isinstance(olds, list) or not isinstance(new, dict):
        raise TypeError(f"judge_change: expected a list 'from' and a dict 'to', got {change!r}")
    models = ", ".join(str(parts.get("judge_model")) for parts in olds)
    percent = round(100 * _number(change, "pass_agreement"))
    diff = _number(change, "mean_abs_score_diff")
    return (
        f"judge change: {models} -> {new.get('judge_model')}: pass agreement {percent}% "
        f"over {change.get('runs')} runs, mean |Δ| {diff:.2f}"
    )


def _number(change: Mapping[str, object], key: str) -> float:
    """``change[key]`` as a float, refused with the offending value unless it is a number."""
    value = change.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"judge_change.{key}: expected a number, got {value!r}")
    return float(value)


def _agreement(runs: Sequence[AgreementRun]) -> dict[str, object]:
    """``runs``' count, share of unchanged verdicts and mean absolute score difference."""
    same = sum(1 for run in runs if run.old_passed == run.new_passed)
    diff = statistics.fmean(abs(run.new_score - run.old_score) for run in runs)
    return {
        "runs": len(runs),
        "pass_agreement": round(same / len(runs), _DIGITS),
        "mean_abs_score_diff": round(diff, _DIGITS),
    }


def _distinct(parts: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Each distinct judge-parts dict of ``parts`` once, ordered by its canonical JSON."""
    unique = {json.dumps(dict(p), sort_keys=True, default=str): dict(p) for p in parts}
    return [unique[key] for key in sorted(unique)]


__all__ = ["AgreementRun", "agreement_line", "judge_change"]
