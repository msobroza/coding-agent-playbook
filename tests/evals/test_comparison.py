"""The opt-in eval comparison flags a task that regresses from the base to HEAD (D37; prU F-01).

Defaults: a regression is a mean score drop above 0.05, or a task that passes on
the base failing in 2 of 3 samples on HEAD.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.evals.comparison import (
    SampleOutcome,
    TaskComparison,
    compare_task,
    compared_task_ids,
    comparison_to_dict,
    format_comparison_table,
)
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    from pathlib import Path


def _outcomes(*scores: float, passed: bool = True) -> list[SampleOutcome]:
    return [SampleOutcome(passed=passed, score=score) for score in scores]


def test_a_mean_score_drop_above_the_threshold_is_a_regression() -> None:
    row = compare_task("t", _outcomes(0.9, 0.9, 0.9), _outcomes(0.8, 0.8, 0.8))
    assert row.regressed


def test_a_drop_of_exactly_the_threshold_is_not_a_regression() -> None:
    row = compare_task("t", _outcomes(0.8, 0.8, 0.8), _outcomes(0.75, 0.75, 0.75))
    assert not row.regressed


def test_a_task_passing_on_the_base_and_failing_two_of_three_on_head_regresses() -> None:
    head = [
        SampleOutcome(passed=False, score=0.9),
        SampleOutcome(passed=False, score=0.9),
        SampleOutcome(passed=True, score=0.9),
    ]
    row = compare_task("t", _outcomes(0.9, 0.9, 0.9), head)
    assert row.regressed
    assert row.reasons == ("fails 2 of 3 samples on head",)


def test_one_failure_in_three_is_not_a_regression() -> None:
    head = [SampleOutcome(passed=False, score=0.9), *_outcomes(0.9, 0.9)]
    assert not compare_task("t", _outcomes(0.9, 0.9, 0.9), head).regressed


def test_a_task_already_failing_on_the_base_does_not_regress_by_failing() -> None:
    base = _outcomes(0.5, 0.5, 0.5, passed=False)
    head = _outcomes(0.5, 0.5, 0.5, passed=False)
    assert not compare_task("t", base, head).regressed


def test_mean_and_spread_summarize_each_side() -> None:
    row = compare_task("t", _outcomes(0.6, 0.8, 1.0), _outcomes(0.9, 0.9, 0.9))
    assert (row.base.mean, row.base.passes, row.base.count) == (0.8, 3, 3)
    assert row.base.spread is not None
    assert round(row.base.spread, 4) == 0.1633
    assert row.head.spread == 0.0


def test_an_unscorable_sample_fails_and_is_left_out_of_the_mean() -> None:
    head = [SampleOutcome(passed=False, score=None), *_outcomes(0.9, 0.7)]
    row = compare_task("t", _outcomes(0.8, 0.8, 0.8), head)
    assert (row.head.passes, row.head.mean) == (2, 0.8)


def test_an_outcome_is_read_from_a_json_eval_run() -> None:
    stdout = json.dumps({"passed": False, "aggregate_score": 0.42, "report": {}})
    assert SampleOutcome.from_run(1, stdout) == SampleOutcome(passed=False, score=0.42)


def test_an_unscorable_or_unreadable_run_has_no_score() -> None:
    assert SampleOutcome.from_run(2, "") == SampleOutcome(passed=False, score=None)
    assert SampleOutcome.from_run(0, "not json") == SampleOutcome(passed=False, score=None)


def test_the_compared_tasks_are_those_of_the_seven_rule_including_prompts(
    tmp_path: Path, make_synthetic_repo: Any
) -> None:
    make_synthetic_repo(tmp_path)
    shipped = SyncContext.from_repo(tmp_path).artifact_source.list_eval_samples()
    assert compared_task_ids(shipped) == [
        "characterize-legacy-pricing",
        "generate-tests-async-code",
        "generate-tests-edge-cases",
        "generate-tests-happy-path",
        "make-testable-inject-clock",
        "refactor-extract-helper",
        "refactor-rename-for-clarity",
        "review-architecture-layer-leak",
        "review-spot-the-bug",
        "review-style-only-no-changes-needed",
        "security-review-already-safe",
        "security-review-pickle-load",
    ]


def _rows() -> list[TaskComparison]:
    return [
        compare_task("refactor-extract-helper", _outcomes(0.9, 0.9, 0.9), _outcomes(0.9, 1.0, 0.8)),
        compare_task("review-spot-the-bug", _outcomes(0.9, 0.9, 0.9), _outcomes(0.5, 0.5, 0.5)),
    ]


def test_the_table_lists_each_task_with_outcome_score_and_spread() -> None:
    table = format_comparison_table(_rows(), base_label="main (v1)", head_label="HEAD (v2)")
    lines = table.splitlines()
    assert "main (v1)" in lines[0]
    assert "HEAD (v2)" in lines[0]
    ok_line = next(line for line in lines if line.startswith("refactor-extract-helper"))
    assert "3/3 pass" in ok_line
    assert "0.900 ± 0.000" in ok_line
    assert "0.900 ± 0.082" in ok_line
    assert ok_line.rstrip().endswith("ok")
    bad_line = next(line for line in lines if line.startswith("review-spot-the-bug"))
    assert "REGRESSION: mean score drops 0.400" in bad_line
    assert lines[-1] == "1 of 2 tasks regressed (advisory, not a merge gate)"


def test_an_unscored_side_shows_no_score() -> None:
    row = compare_task("t", _outcomes(0.9), [SampleOutcome(passed=False, score=None)])
    assert "n/a" in format_comparison_table([row], base_label="b", head_label="h")


def test_the_json_view_carries_both_sides_and_the_reasons() -> None:
    view = comparison_to_dict(_rows(), base_label="main (v1)", head_label="HEAD (v2)")
    assert (view["base"], view["head"], view["regressions"]) == ("main (v1)", "HEAD (v2)", 1)
    tasks = view["tasks"]
    assert isinstance(tasks, list)
    assert tasks[1] == {
        "task_id": "review-spot-the-bug",
        "base": {"count": 3, "passes": 3, "mean": 0.9, "spread": 0.0},
        "head": {"count": 3, "passes": 3, "mean": 0.5, "spread": 0.0},
        "regressed": True,
        "reasons": ["mean score drops 0.400"],
    }
