"""The opt-in eval comparison flags an eval sample that regresses from the base to HEAD (D37; prU F-01).

Defaults: a regression is a mean score drop above 0.05, or an eval sample that
passes on the base failing in 2 of 3 runs on HEAD.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.evals.comparison import (
    ComparisonSetup,
    RunOutcome,
    SampleComparison,
    SideSummary,
    compare_sample,
    compared_sample_ids,
    comparison_to_dict,
    format_comparison_table,
)
from coding_agent_playbook.evals.task_registry import TaskRegistry
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    from pathlib import Path


def _outcomes(*scores: float, passed: bool = True) -> list[RunOutcome]:
    return [RunOutcome(passed=passed, score=score) for score in scores]


def test_a_mean_score_drop_above_the_threshold_is_a_regression() -> None:
    row = compare_sample("t", _outcomes(0.9, 0.9, 0.9), _outcomes(0.8, 0.8, 0.8))
    assert row.regressed


def test_a_drop_of_exactly_the_threshold_is_not_a_regression() -> None:
    row = compare_sample("t", _outcomes(0.8, 0.8, 0.8), _outcomes(0.75, 0.75, 0.75))
    assert not row.regressed


def test_a_sample_passing_on_the_base_and_failing_two_of_three_on_head_regresses() -> None:
    head = [
        RunOutcome(passed=False, score=0.9),
        RunOutcome(passed=False, score=0.9),
        RunOutcome(passed=True, score=0.9),
    ]
    row = compare_sample("t", _outcomes(0.9, 0.9, 0.9), head)
    assert row.regressed
    assert row.reasons == ("fails 2 of 3 runs on head",)


def test_one_failure_in_three_is_not_a_regression() -> None:
    head = [RunOutcome(passed=False, score=0.9), *_outcomes(0.9, 0.9)]
    assert not compare_sample("t", _outcomes(0.9, 0.9, 0.9), head).regressed


def test_a_sample_already_failing_on_the_base_does_not_regress_by_failing() -> None:
    base = _outcomes(0.5, 0.5, 0.5, passed=False)
    head = _outcomes(0.5, 0.5, 0.5, passed=False)
    assert not compare_sample("t", base, head).regressed


def test_mean_and_spread_summarize_each_side() -> None:
    row = compare_sample("t", _outcomes(0.6, 0.8, 1.0), _outcomes(0.9, 0.9, 0.9))
    assert (row.base.mean, row.base.passes, row.base.count) == (0.8, 3, 3)
    assert row.base.spread is not None
    assert round(row.base.spread, 4) == 0.1633
    assert row.head.spread == 0.0


def test_an_unscorable_run_fails_and_is_left_out_of_the_mean() -> None:
    head = [RunOutcome(passed=False, score=None), *_outcomes(0.9, 0.7)]
    row = compare_sample("t", _outcomes(0.8, 0.8, 0.8), head)
    assert (row.head.passes, row.head.mean) == (2, 0.8)


def test_an_outcome_is_read_from_a_json_eval_run() -> None:
    stdout = json.dumps({"passed": False, "aggregate_score": 0.42, "report": {}})
    assert RunOutcome.from_run(1, stdout) == RunOutcome(passed=False, score=0.42)


def test_an_unscorable_or_unreadable_run_has_no_score() -> None:
    assert RunOutcome.from_run(2, "") == RunOutcome(passed=False, score=None)
    assert RunOutcome.from_run(0, "not json") == RunOutcome(passed=False, score=None)


def _registry(tmp_path: Path, make_synthetic_repo: Any) -> TaskRegistry:
    make_synthetic_repo(tmp_path)
    ctx = SyncContext.from_repo(tmp_path)
    return TaskRegistry.from_catalog(ctx.artifact_source, ctx.prompts_resolved)


def test_the_compared_samples_come_from_the_samples_of_every_task(
    tmp_path: Path, make_synthetic_repo: Any
) -> None:
    registry = _registry(tmp_path, make_synthetic_repo)
    every = sorted(sample.id for task in registry.tasks() for sample in task.samples)
    assert compared_sample_ids(registry) == every
    assert "explain/pure-function" in every  # no hard-coded list of prompts


def test_the_compared_samples_narrow_to_the_prompts_an_edition_grades(
    tmp_path: Path, make_synthetic_repo: Any
) -> None:
    registry = _registry(tmp_path, make_synthetic_repo)
    assert compared_sample_ids(registry, {"refactor"}) == [
        "refactor/extract-helper",
        "refactor/rename-for-clarity",
    ]
    assert compared_sample_ids(registry, set()) == []


_SETUP = ComparisonSetup("main (v1)", "HEAD (v2)", runner="claude_code", judge="llm")


def _rows() -> list[SampleComparison]:
    return [
        compare_sample(
            "refactor-extract-helper", _outcomes(0.9, 0.9, 0.9), _outcomes(0.9, 1.0, 0.8)
        ),
        compare_sample("review-spot-the-bug", _outcomes(0.9, 0.9, 0.9), _outcomes(0.5, 0.5, 0.5)),
    ]


def test_the_table_lists_each_sample_with_outcome_score_and_spread() -> None:
    table = format_comparison_table(_rows(), _SETUP)
    lines = table.splitlines()
    assert lines[0] == "runner claude_code, judge llm: score = gate and judge rubric"
    assert "main (v1) judge score" in lines[1]
    assert "HEAD (v2) judge score" in lines[1]
    ok_line = next(line for line in lines if line.startswith("refactor-extract-helper"))
    assert "3/3 pass" in ok_line
    assert "0.900 ± 0.000" in ok_line
    assert "0.900 ± 0.082" in ok_line
    assert ok_line.rstrip().endswith("ok")
    bad_line = next(line for line in lines if line.startswith("review-spot-the-bug"))
    assert "REGRESSION: mean score drops 0.400" in bad_line
    assert lines[-1] == "1 of 2 eval samples regressed, 0 unscorable (advisory, not a merge gate)"


def test_an_unscored_side_shows_no_score() -> None:
    row = compare_sample("t", _outcomes(0.9), [RunOutcome(passed=False, score=None)])
    assert "n/a" in format_comparison_table([row], _SETUP)


def test_a_side_with_no_scorable_run_is_reported_unscorable_not_ok() -> None:
    unscored = [RunOutcome(passed=False, score=None)]
    row = compare_sample("t", unscored, unscored)
    assert (row.unscorable_sides, row.regressed) == (("base", "head"), False)
    lines = format_comparison_table([row], _SETUP).splitlines()
    assert lines[-2].endswith("UNSCORABLE: no scorable run on main (v1) and HEAD (v2)")
    assert lines[-1].startswith("0 of 1 eval samples regressed, 1 unscorable")
    view = comparison_to_dict([row], _SETUP)
    assert view["unscorable"] == 1
    samples = view["samples"]
    assert isinstance(samples, list)
    assert samples[0]["unscorable"] == ["base", "head"]


def test_a_regression_with_an_unscorable_head_names_both() -> None:
    head = [RunOutcome(passed=False, score=None)] * 3
    row = compare_sample("t", _outcomes(0.9, 0.9, 0.9), head)
    verdict = format_comparison_table([row], _SETUP).splitlines()[-2]
    assert "REGRESSION: fails 3 of 3 runs on head" in verdict
    assert verdict.endswith("UNSCORABLE: no scorable run on HEAD (v2)")


def test_the_json_view_carries_both_sides_and_the_reasons() -> None:
    view = comparison_to_dict(_rows(), _SETUP)
    assert (view["base"], view["head"], view["regressions"]) == ("main (v1)", "HEAD (v2)", 1)
    assert (view["runner"], view["judge"], view["score"]) == ("claude_code", "llm", "judge score")
    rows = view["samples"]
    assert isinstance(rows, list)
    assert rows[1] == {
        "sample_id": "review-spot-the-bug",
        "base": {"count": 3, "passes": 3, "mean": 0.9, "spread": 0.0},
        "head": {"count": 3, "passes": 3, "mean": 0.5, "spread": 0.0},
        "regressed": True,
        "reasons": ["mean score drops 0.400"],
        "unscorable": [],
    }
    assert view["unscorable"] == 0


def test_without_a_judge_the_table_and_json_name_the_gate_score() -> None:
    setup = ComparisonSetup("main (v1)", "HEAD (v1)", runner="fake")
    lines = format_comparison_table(_rows(), setup).splitlines()
    assert lines[0] == "runner fake, no judge: score = deterministic gate score only"
    assert "main (v1) gate score" in lines[1]
    view = comparison_to_dict(_rows(), setup)
    assert (view["judge"], view["score"]) == (None, "gate score")


def test_a_side_fails_overall_on_a_majority_of_failed_runs() -> None:
    assert SideSummary.of(_outcomes(0.1, 0.1, passed=False) + _outcomes(0.9)).fails_overall
    assert not SideSummary.of(_outcomes(0.9, 0.9) + _outcomes(0.1, passed=False)).fails_overall
