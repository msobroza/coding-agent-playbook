"""Compare eval runs of the same eval samples on a base and on HEAD (D37, D76; prU F-01).

The opt-in ``playbook eval --compare`` runs each eval sample several times per side
and hands the outcomes here. This module is pure: it summarizes each side (passes,
mean score, spread), flags regressions by the default thresholds and renders the
comparison as a table or JSON. An eval sample *regresses* when its mean score drops
by more than :data:`MAX_SCORE_DROP`, or when it passes on the base (a majority of
its base runs pass) and fails a majority of its HEAD runs (2 of 3 by default). The
comparison is advisory, never a merge gate.
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


#: The prompts whose included rule bodies change (D30): their eval samples are compared.
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


class _EvalSampleIds(Protocol):
    """What eval sample selection reads from an ``EvalSample``."""

    @property
    def id(self) -> str: ...

    @property
    def prompt_id(self) -> str: ...


def compared_sample_ids(eval_samples: Iterable[_EvalSampleIds]) -> list[str]:
    """The sorted ids of the eval samples graded against one of :data:`COMPARED_PROMPTS`.

    Example::

        >>> from types import SimpleNamespace as S
        >>> compared_sample_ids([S(id="b", prompt_id="review"), S(id="a", prompt_id="explain")])
        ['b']
    """
    return sorted(s.id for s in eval_samples if s.prompt_id in COMPARED_PROMPTS)


@dataclass(frozen=True)
class RunOutcome:
    """One eval run of one eval sample: its verdict and score (``None`` when unscorable).

    Example::

        >>> RunOutcome.from_run(0, '{"passed": true, "aggregate_score": 1.0}')
        RunOutcome(passed=True, score=1.0)
    """

    passed: bool
    score: float | None

    @classmethod
    def from_run(cls, exit_code: int, stdout: str) -> RunOutcome:
        """Read ``playbook eval <id> --run --format json``'s exit code and output.

        Exit ``2`` (the eval sample could not be scored), or output that is not the
        JSON report, is a failed run with no score; the verdict and score otherwise
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
    """One side's runs of one eval sample: passes out of ``count``, mean score and spread.

    ``mean`` and ``spread`` (population standard deviation) cover the scored
    runs only; both are ``None`` when no run could be scored.
    """

    count: int
    passes: int
    mean: float | None
    spread: float | None

    @classmethod
    def of(cls, outcomes: Sequence[RunOutcome]) -> SideSummary:
        """Summarize ``outcomes``.

        Example::

            >>> SideSummary.of([RunOutcome(True, 0.5), RunOutcome(False, None)])
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
    def failures(self) -> int:
        """How many runs failed (an unscorable run fails)."""
        return self.count - self.passes

    @property
    def passes_overall(self) -> bool:
        """Whether a majority of the runs passed."""
        return _is_majority(self.passes, self.count)

    @property
    def fails_overall(self) -> bool:
        """Whether a majority of the runs failed (2 of 3 by default)."""
        return _is_majority(self.failures, self.count)


def _is_majority(part: int, count: int) -> bool:
    return part * 2 > count


@dataclass(frozen=True)
class SampleComparison:
    """One eval sample's base and HEAD summaries and why it regressed (empty when not)."""

    sample_id: str
    base: SideSummary
    head: SideSummary
    reasons: tuple[str, ...]

    @property
    def regressed(self) -> bool:
        """Whether any regression rule fired."""
        return bool(self.reasons)


@dataclass(frozen=True)
class ComparisonSetup:
    """What both sides shared: their labels, the agent runner and the judge (if any).

    Without a judge the compared score is the deterministic gate score only, so
    the table and JSON say which score they compare.

    Example::

        >>> ComparisonSetup("main (v1)", "HEAD (v1)", runner="fake").score_name
        'gate score'
    """

    base_label: str
    head_label: str
    runner: str
    judge: str | None = None

    @property
    def score_name(self) -> str:
        """``judge score`` with a judge, ``gate score`` (deterministic only) without."""
        return "judge score" if self.judge else "gate score"


def compare_sample(
    sample_id: str, base: Sequence[RunOutcome], head: Sequence[RunOutcome]
) -> SampleComparison:
    """Compare one eval sample's base and HEAD outcomes by the default thresholds (D37).

    Example::

        >>> base = [RunOutcome(True, 0.9)] * 3
        >>> compare_sample("s", base, [RunOutcome(True, 0.7)] * 3).reasons
        ('mean score drops 0.200',)
    """
    base_summary, head_summary = SideSummary.of(base), SideSummary.of(head)
    reasons = regression_reasons(base_summary, head_summary)
    return SampleComparison(sample_id, base_summary, head_summary, reasons)


def regression_reasons(
    base: SideSummary, head: SideSummary, head_label: str = "head"
) -> tuple[str, ...]:
    """Why ``head`` regressed from ``base`` by the D37 thresholds (empty: it did not).

    The one home of the rule: ``--compare`` and the release regression check
    (``evals.release_regression``) both call it.

    Example::

        >>> regression_reasons(SideSummary(3, 3, 0.9, 0.0), SideSummary(3, 1, 0.9, 0.0), "new")
        ('fails 2 of 3 runs on new',)
    """
    reasons: list[str] = []
    if base.mean is not None and head.mean is not None:
        drop = round(base.mean - head.mean, _DIGITS)
        if drop > MAX_SCORE_DROP:
            reasons.append(f"mean score drops {drop:.3f}")
    if base.passes_overall and head.fails_overall:
        reasons.append(f"fails {head.failures} of {head.count} runs on {head_label}")
    return tuple(reasons)


def improvement_reasons(base: SideSummary, head: SideSummary) -> tuple[str, ...]:
    """Why ``head`` improved on ``base``: the mirror of :func:`regression_reasons`.

    Example::

        >>> improvement_reasons(SideSummary(3, 0, 0.5, 0.0), SideSummary(3, 3, 0.9, 0.0))
        ('mean score rises 0.400', 'passes 3 of 3 runs')
    """
    reasons: list[str] = []
    if base.mean is not None and head.mean is not None:
        rise = round(head.mean - base.mean, _DIGITS)
        if rise > MAX_SCORE_DROP:
            reasons.append(f"mean score rises {rise:.3f}")
    if base.fails_overall and head.passes_overall:
        reasons.append(f"passes {head.passes} of {head.count} runs")
    return tuple(reasons)


def format_comparison_table(rows: Sequence[SampleComparison], setup: ComparisonSetup) -> str:
    """Render ``rows`` as an aligned table, one line per eval sample, framed by setup and summary.

    The first line names the runner and judge both sides ran with; each side then
    shows ``passes/count pass`` and ``mean ± spread`` of the scores; the last column
    is ``ok`` or ``REGRESSION: <reasons>``.

    Example::

        >>> row = compare_sample("s", [RunOutcome(True, 0.9)], [RunOutcome(True, 0.9)])
        >>> format_comparison_table([row], ComparisonSetup("b", "h", "fake")).splitlines()[-1]
        '0 of 1 eval samples regressed (advisory, not a merge gate)'
    """
    score = setup.score_name
    header: tuple[str, ...] = ("eval sample", f"{setup.base_label} outcome")
    header += (f"{setup.head_label} outcome", f"{setup.base_label} {score}")
    header += (f"{setup.head_label} {score}", "verdict")
    table = [header] + [_table_cells(row) for row in rows]
    widths = [max(len(cells[i]) for cells in table) for i in range(len(header) - 1)]
    lines = [_setup_line(setup)]
    lines += [
        "  ".join([*(c.ljust(w) for c, w in zip(cells, widths, strict=False)), cells[-1]])
        for cells in table
    ]
    regressed = sum(1 for row in rows if row.regressed)
    lines.append(f"{regressed} of {len(rows)} eval samples regressed (advisory, not a merge gate)")
    return "\n".join(lines)


def _setup_line(setup: ComparisonSetup) -> str:
    if setup.judge:
        return f"runner {setup.runner}, judge {setup.judge}: score = gate and judge rubric"
    return f"runner {setup.runner}, no judge: score = deterministic gate score only"


def _table_cells(row: SampleComparison) -> tuple[str, ...]:
    verdict = "REGRESSION: " + "; ".join(row.reasons) if row.regressed else "ok"
    outcomes = (_outcome_cell(row.base), _outcome_cell(row.head))
    return (row.sample_id, *outcomes, _score_cell(row.base), _score_cell(row.head), verdict)


def _outcome_cell(side: SideSummary) -> str:
    return f"{side.passes}/{side.count} pass"


def _score_cell(side: SideSummary) -> str:
    if side.mean is None or side.spread is None:
        return "n/a"
    return f"{side.mean:.3f} ± {side.spread:.3f}"


def comparison_to_dict(
    rows: Sequence[SampleComparison], setup: ComparisonSetup
) -> dict[str, object]:
    """Stable JSON view: both labels, runner, judge, score kind, regressions, each sample.

    Example::

        >>> comparison_to_dict([], ComparisonSetup("b", "h", "fake"))["regressions"]
        0
    """
    return {
        "base": setup.base_label,
        "head": setup.head_label,
        "runner": setup.runner,
        "judge": setup.judge,
        "score": setup.score_name,
        "regressions": sum(1 for row in rows if row.regressed),
        "samples": [_row_to_dict(row) for row in rows],
    }


def _row_to_dict(row: SampleComparison) -> dict[str, object]:
    return {
        "sample_id": row.sample_id,
        "base": _side_to_dict(row.base),
        "head": _side_to_dict(row.head),
        "regressed": row.regressed,
        "reasons": list(row.reasons),
    }


def _side_to_dict(side: SideSummary) -> dict[str, object]:
    return {"count": side.count, "passes": side.passes, "mean": side.mean, "spread": side.spread}
