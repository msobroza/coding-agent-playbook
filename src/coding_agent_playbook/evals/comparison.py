"""Compare eval runs of the same tasks on a base and on HEAD (D37, D76; prU F-01).

The opt-in ``playbook eval --compare`` runs each task several times per side and
hands the outcomes here. This module is pure: it summarizes each side (passes,
mean score, spread), flags regressions by the default thresholds and renders the
comparison as a table or JSON. A task *regresses* when its mean score drops by
more than :data:`MAX_SCORE_DROP`, or when it passes on the base (a majority of
its base samples pass) and fails a majority of its HEAD samples (2 of 3 by
default). The comparison is advisory, never a merge gate.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

#: A mean score drop above this (base mean minus HEAD mean) is a regression (D37).
MAX_SCORE_DROP: Final = 0.05
#: Means and spreads are rounded to this many digits, so a drop of exactly
#: ``MAX_SCORE_DROP`` (0.80 -> 0.75 is 0.05000000000000004 in floats) is not one.
_DIGITS: Final = 6


#: The prompts whose included rule bodies change (D30): their eval tasks are compared.
COMPARED_PROMPTS: Final = frozenset(
    {
        "characterize",
        "generate-tests",
        "make-testable",
        "refactor",
        "review",
        "review-architecture",
        "security-review",
    }
)


class _Task(Protocol):
    """What task selection reads from an eval sample (``EvalSample``)."""

    @property
    def id(self) -> str: ...

    @property
    def prompt_id(self) -> str: ...


def compared_task_ids(tasks: Iterable[_Task]) -> list[str]:
    """The sorted ids of the tasks graded against one of :data:`COMPARED_PROMPTS`.

    Example::

        >>> from types import SimpleNamespace as T
        >>> compared_task_ids([T(id="b", prompt_id="review"), T(id="a", prompt_id="explain")])
        ['b']
    """
    return sorted(task.id for task in tasks if task.prompt_id in COMPARED_PROMPTS)


@dataclass(frozen=True)
class SampleOutcome:
    """One eval run of one task: its verdict and score (``None`` when unscorable).

    Example::

        >>> SampleOutcome.from_run(0, '{"passed": true, "aggregate_score": 1.0}')
        SampleOutcome(passed=True, score=1.0)
    """

    passed: bool
    score: float | None

    @classmethod
    def from_run(cls, exit_code: int, stdout: str) -> SampleOutcome:
        """Read ``playbook eval <id> --run --format json``'s exit code and output.

        Exit ``2`` (the task could not be scored), or output that is not the JSON
        report, is a failed sample with no score; the verdict and score otherwise
        come from the report's ``passed`` and ``aggregate_score``.
        """
        if exit_code not in (0, 1):
            return cls(passed=False, score=None)
        try:
            report = json.loads(stdout)
            score = float(report["aggregate_score"])
            passed = bool(report["passed"])
        except (ValueError, TypeError, KeyError):
            return cls(passed=False, score=None)
        return cls(passed=passed, score=score)


@dataclass(frozen=True)
class SideSummary:
    """One side's outcomes for one task: passes out of ``count``, mean score and spread.

    ``mean`` and ``spread`` (population standard deviation) cover the scored
    samples only; both are ``None`` when no sample could be scored.
    """

    count: int
    passes: int
    mean: float | None
    spread: float | None

    @classmethod
    def of(cls, outcomes: Sequence[SampleOutcome]) -> SideSummary:
        """Summarize ``outcomes``.

        Example::

            >>> SideSummary.of([SampleOutcome(True, 0.5), SampleOutcome(False, None)])
            SideSummary(count=2, passes=1, mean=0.5, spread=0.0)
        """
        scores = [o.score for o in outcomes if o.score is not None]
        passes = sum(1 for o in outcomes if o.passed)
        if not scores:
            return cls(len(outcomes), passes, None, None)
        mean = round(statistics.fmean(scores), _DIGITS)
        spread = round(statistics.pstdev(scores), _DIGITS)
        return cls(len(outcomes), passes, mean, spread)

    @property
    def passes_overall(self) -> bool:
        """Whether a majority of the samples passed."""
        return self.passes * 2 > self.count

    @property
    def failures(self) -> int:
        """How many samples failed (an unscorable sample fails)."""
        return self.count - self.passes


@dataclass(frozen=True)
class TaskComparison:
    """One task's base and HEAD summaries and why it regressed (empty when it did not)."""

    task_id: str
    base: SideSummary
    head: SideSummary
    reasons: tuple[str, ...]

    @property
    def regressed(self) -> bool:
        """Whether any regression rule fired."""
        return bool(self.reasons)


def compare_task(
    task_id: str, base: Sequence[SampleOutcome], head: Sequence[SampleOutcome]
) -> TaskComparison:
    """Compare one task's base and HEAD outcomes by the default thresholds (D37).

    Example::

        >>> base = [SampleOutcome(True, 0.9)] * 3
        >>> compare_task("t", base, [SampleOutcome(True, 0.7)] * 3).reasons
        ('mean score drops 0.200',)
    """
    base_summary, head_summary = SideSummary.of(base), SideSummary.of(head)
    reasons: list[str] = []
    if base_summary.mean is not None and head_summary.mean is not None:
        drop = round(base_summary.mean - head_summary.mean, _DIGITS)
        if drop > MAX_SCORE_DROP:
            reasons.append(f"mean score drops {drop:.3f}")
    if base_summary.passes_overall and head_summary.failures * 2 > head_summary.count:
        reasons.append(f"fails {head_summary.failures} of {head_summary.count} samples on head")
    return TaskComparison(task_id, base_summary, head_summary, tuple(reasons))


def format_comparison_table(
    rows: Sequence[TaskComparison], *, base_label: str, head_label: str
) -> str:
    """Render ``rows`` as an aligned text table, one line per task, plus a summary line.

    Each side shows ``passes/count pass`` and ``mean ± spread`` of the scores; the
    last column is ``ok`` or ``REGRESSION: <reasons>``.

    Example::

        >>> row = compare_task("t", [SampleOutcome(True, 0.9)], [SampleOutcome(True, 0.9)])
        >>> format_comparison_table([row], base_label="b", head_label="h").splitlines()[-1]
        '0 of 1 tasks regressed (advisory, not a merge gate)'
    """
    header: tuple[str, ...] = ("task", f"{base_label} outcome", f"{head_label} outcome")
    header += (f"{base_label} score", f"{head_label} score", "verdict")
    table = [header] + [_table_cells(row) for row in rows]
    widths = [max(len(cells[i]) for cells in table) for i in range(len(header) - 1)]
    lines = [
        "  ".join([*(c.ljust(w) for c, w in zip(cells, widths, strict=False)), cells[-1]])
        for cells in table
    ]
    regressed = sum(1 for row in rows if row.regressed)
    lines.append(f"{regressed} of {len(rows)} tasks regressed (advisory, not a merge gate)")
    return "\n".join(lines)


def _table_cells(row: TaskComparison) -> tuple[str, ...]:
    verdict = "REGRESSION: " + "; ".join(row.reasons) if row.regressed else "ok"
    outcomes = (_outcome_cell(row.base), _outcome_cell(row.head))
    return (row.task_id, *outcomes, _score_cell(row.base), _score_cell(row.head), verdict)


def _outcome_cell(side: SideSummary) -> str:
    return f"{side.passes}/{side.count} pass"


def _score_cell(side: SideSummary) -> str:
    if side.mean is None or side.spread is None:
        return "n/a"
    return f"{side.mean:.3f} ± {side.spread:.3f}"


def comparison_to_dict(
    rows: Sequence[TaskComparison], *, base_label: str, head_label: str
) -> dict[str, object]:
    """Stable JSON view of the comparison: both labels, the regression count and each task.

    Example::

        >>> comparison_to_dict([], base_label="b", head_label="h")["regressions"]
        0
    """
    return {
        "base": base_label,
        "head": head_label,
        "regressions": sum(1 for row in rows if row.regressed),
        "tasks": [_row_to_dict(row) for row in rows],
    }


def _row_to_dict(row: TaskComparison) -> dict[str, object]:
    return {
        "task_id": row.task_id,
        "base": _side_to_dict(row.base),
        "head": _side_to_dict(row.head),
        "regressed": row.regressed,
        "reasons": list(row.reasons),
    }


def _side_to_dict(side: SideSummary) -> dict[str, object]:
    return {"count": side.count, "passes": side.passes, "mean": side.mean, "spread": side.spread}
