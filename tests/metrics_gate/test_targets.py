"""The fix note: the raw value a finding passes at, and one refactoring hint per metric.

Findings are built by hand (``ScopeDetail``), as the checks emit them: the
deciding ``0-1`` ``bound`` for a new or absolute finding, the raw ``baseline``
for a regression.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.grading.metric import all_metrics, get_metric
from coding_agent_playbook.grading.types import Kind, ScopeDetail
from coding_agent_playbook.metrics_gate.config import MetricConfig, parse_metrics_config
from coding_agent_playbook.metrics_gate.targets import FIX_HINTS, fix_note, passing_target


def _finding(
    evaluator: str,
    value: float,
    *,
    baseline: float | None = None,
    bound: float | None = None,
    kind: Kind = "new",
) -> ScopeDetail:
    return ScopeDetail(evaluator, "src/x.py::parse", value, baseline, bound, 0.0, "fail", kind)


@pytest.mark.parametrize(
    ("finding", "target"),
    [
        (_finding("cyclomatic_complexity", 23, bound=0.25), "<= 16"),  # the default fail
        (_finding("cyclomatic_complexity", 14, bound=0.5), "<= 12"),  # the default warn
        (_finding("wmc", 70, bound=0.2), "<= 50"),
        (_finding("cognitive_complexity", 16, bound=1.0), "<= 15"),  # the standard limit
        (_finding("maintainability_index", 50, bound=0.65), ">= 65"),
        (_finding("diff_coverage", 50, bound=0.8), ">= 80"),
    ],
)
def test_a_new_finding_passes_where_its_bound_is_met(finding: ScopeDetail, target: str) -> None:
    assert passing_target(finding, MetricConfig()) == target


@pytest.mark.parametrize(
    ("finding", "target"),
    [
        # From inside the free budget (CC <= 5 scores 1.0), back into it.
        (_finding("cyclomatic_complexity", 9, baseline=1, kind="regression"), "<= 5"),
        # From over the budget, back to the baseline.
        (_finding("cyclomatic_complexity", 9, baseline=8, kind="regression"), "<= 8"),
        (_finding("cognitive_complexity", 20, baseline=1, kind="regression"), "<= 15"),
        (_finding("ruff_violations", 1, baseline=0, kind="regression"), "<= 0"),
        (_finding("maintainability_index", 60, baseline=70.5, kind="regression"), ">= 70.5"),
    ],
)
def test_a_regression_passes_back_at_its_baseline_score(finding: ScopeDetail, target: str) -> None:
    assert passing_target(finding, MetricConfig()) == target


def test_a_configured_threshold_moves_the_target() -> None:
    config = parse_metrics_config({"thresholds": {"cognitive_complexity": {"fail": 0.9}}})

    assert passing_target(_finding("cognitive_complexity", 30, bound=0.9), config) == "<= 25"


def test_regression_tolerance_moves_the_target() -> None:
    config = parse_metrics_config({"regression": {"cyclomatic_complexity": {"max_worsening": 0.2}}})
    finding = _finding("cyclomatic_complexity", 14, baseline=8, kind="regression")

    # 0.8 - 0.2 = 0.6 puts the edge at 11, but the check's own float subtraction
    # (0.8 - 0.6 = 0.20000000000000007 > 0.2) already fails 11: the target is what it accepts.
    assert passing_target(finding, config) == "<= 10"


@pytest.mark.parametrize("metric", ["cyclomatic_complexity", "cognitive_complexity", "wmc"])
def test_the_target_is_the_exact_last_value_the_check_accepts(metric: str) -> None:
    """Swept cutoffs: float error never moves the boundary (the check compares scores)."""
    score = get_metric(metric).score
    for step in range(1, 101):
        cutoff = step / 100
        target = passing_target(_finding(metric, 1000, bound=cutoff), MetricConfig())
        best = int(target.removeprefix("<= "))
        assert score(best) >= cutoff > score(best + 1), (cutoff, target)


def test_no_target_where_nothing_could_fail_or_the_scale_is_not_raw() -> None:
    sloc = _finding("file_sloc", 900, baseline=850, kind="regression")  # max_worsening 1.0
    example = _finding("docstring_example", 0.5, baseline=1.0, kind="regression")  # Identity

    assert passing_target(sloc, MetricConfig()) == ""
    assert passing_target(example, MetricConfig()) == ""


def test_fix_note_joins_the_target_and_the_hint_or_keeps_whichever_is_known() -> None:
    config = MetricConfig()

    assert fix_note(_finding("cyclomatic_complexity", 23, bound=0.25), config) == (
        "passes at <= 16: split branches into helpers"
    )
    assert fix_note(_finding("ruff_violations", 1, baseline=0, kind="regression"), config) == (
        "passes at <= 0"
    )
    assert fix_note(
        _finding("docstring_example", 0.5, baseline=1.0, kind="regression"), config
    ) == ("add a usage example to the docstring")
    assert fix_note(_finding("no_such_metric", 3, bound=0.5), config) == ""


def test_every_hint_names_a_registered_metric() -> None:
    assert set(FIX_HINTS) <= {metric.name for metric in all_metrics()}
