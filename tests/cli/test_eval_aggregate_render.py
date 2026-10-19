"""Renderer tests for the C8 aggregate surface in ``playbook eval --run``.

The text + JSON renderers in :mod:`coding_agent_playbook.evals.report_format` surface
the across-trial aggregate result (``pass@k`` / ``pass^k`` over N trials) when a
task authored an ``[aggregate]`` block, and omit it otherwise. These drive the
renderers directly with a synthetic :class:`TaskResult` (no runner / SyncContext)
so they stay fast and focused on the rendering contract.
"""

from __future__ import annotations

from coding_agent_playbook.evals.report_format import format_task_result_text, task_result_to_dict
from coding_agent_playbook.evals.run.harness_runner import TaskResult
from coding_agent_playbook.grading.scope import CostTier, Determinism
from coding_agent_playbook.grading.types import (
    CheckResult,
    EvaluationReport,
    ScopeDetail,
    TrialResult,
)


def _trial(verdict: bool) -> TrialResult:
    report = EvaluationReport(
        findings=[], warn_count=0, fail_count=0, composite=None, passed=verdict, checks=[]
    )
    return TrialResult(report=report, verdict=verdict)


def _agg_result(score: float, *, passed: bool) -> CheckResult:
    detail = ScopeDetail(
        evaluator="pass_at_k:verdict@5",
        scope_key="verdict",
        value=score,
        baseline=None,
        bound=None,
        score=score,
        level="ok" if passed else "fail",
        kind="absolute",
    )
    return CheckResult(
        check_id="pass_at_k:verdict@5",
        passed=passed,
        score=score,
        weight=0.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        status="run",
        subresults=(detail,),
    )


def _aggregate_result() -> TaskResult:
    trials = [_trial(v) for v in (True, True, True, True, False)]
    return TaskResult(
        task_id="t-agg",
        harness="fake",
        report=trials[0].report,
        passed=True,
        aggregate_score=1.0,
        duration_seconds=0.42,
        transcript="",
        trials=trials,
        aggregate=_agg_result(1.0, passed=True),
    )


def _plain_result() -> TaskResult:
    trial = _trial(True)
    return TaskResult(
        task_id="t-plain",
        harness="fake",
        report=trial.report,
        passed=True,
        aggregate_score=1.0,
        duration_seconds=0.1,
        transcript="",
        trials=[trial],
        aggregate=None,
    )


def test_text_render_shows_aggregate_line() -> None:
    text = format_task_result_text(_aggregate_result())
    assert "aggregate: pass_at_k:verdict@5 = 1.000 (PASS)" in text
    assert "5 trials (4/5 passed)" in text


def test_text_render_omits_aggregate_when_absent() -> None:
    text = format_task_result_text(_plain_result())
    assert "aggregate:" not in text


def test_json_render_includes_aggregate_block() -> None:
    payload = task_result_to_dict(_aggregate_result())
    assert payload["trials"] == 5
    assert payload["trial_verdicts"] == [True, True, True, True, False]
    assert payload["aggregate"]["check_id"] == "pass_at_k:verdict@5"  # type: ignore[index]
    assert payload["aggregate"]["passed"] is True  # type: ignore[index]


def test_json_render_omits_aggregate_when_absent() -> None:
    payload = task_result_to_dict(_plain_result())
    assert "aggregate" not in payload
    assert "trials" not in payload


# --------------------------------------------------------------------------- #
# Skipped aggregate + judged-score labelling across trials
# --------------------------------------------------------------------------- #


def _skipped_aggregate_result() -> TaskResult:
    """``over = "rubric"`` with no judge: the aggregate skipped, verdict fell back."""
    trials = [_trial(True), _trial(True)]
    skipped = CheckResult(
        check_id="pass_at_k:rubric@2",
        passed=False,
        score=None,
        weight=0.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        status="skipped",
    )
    return TaskResult(
        task_id="t-agg-skip",
        harness="fake",
        report=trials[0].report,
        passed=True,
        aggregate_score=1.0,
        duration_seconds=0.1,
        transcript="",
        trials=trials,
        aggregate=skipped,
    )


def test_text_render_explains_a_skipped_aggregate_instead_of_failing_it() -> None:
    """A skipped aggregate has no verdict; never print ``(FAIL)`` beside a PASS task."""
    text = format_task_result_text(_skipped_aggregate_result())
    assert "aggregate: pass_at_k:rubric@2 skipped" in text
    assert "verdict from all 2 trials (2/2 passed)" in text
    assert "(FAIL)" not in text


def _judged_leaf(*, status: str) -> CheckResult:
    return CheckResult(
        check_id="judge:clear",
        passed=status == "run",
        score=0.9 if status == "run" else None,
        weight=1.0,
        required=False,
        determinism=Determinism.JUDGED,
        cost=CostTier.JUDGED,
        status=status,  # type: ignore[arg-type]
    )


def _rubric_layer(*children: CheckResult, status: str = "run") -> CheckResult:
    return CheckResult(
        check_id="rubric",
        passed=True,
        score=1.0,
        weight=0.0,
        required=True,
        determinism=Determinism.JUDGED,
        cost=CostTier.JUDGED,
        status=status,  # type: ignore[arg-type]
        subresults=children,
    )


def _trial_with(*checks: CheckResult) -> TrialResult:
    report = EvaluationReport(
        findings=[], warn_count=0, fail_count=0, composite=None, passed=True, checks=list(checks)
    )
    return TrialResult(report=report, verdict=True)


def test_uncalibrated_flag_considers_every_trial_not_just_the_reported_one() -> None:
    """Trial 0 never reached the judge; trial 1's judged score decided the task."""
    t0 = _trial_with(_rubric_layer(status="skipped"))
    t1 = _trial_with(_rubric_layer(_judged_leaf(status="run")))
    result = TaskResult(
        task_id="t",
        harness="fake",
        report=t0.report,
        passed=True,
        aggregate_score=1.0,
        duration_seconds=0.1,
        transcript="",
        trials=[t0, t1],
        aggregate=_agg_result(1.0, passed=True),
    )
    assert task_result_to_dict(result)["uncalibrated_judge"] is True
    assert "uncalibrated" in format_task_result_text(result)


def test_uncalibrated_flag_ignores_a_judged_composer_whose_judged_leaf_skipped() -> None:
    """Composers inherit JUDGED from any judged child; only a *run* judged leaf counts."""
    deterministic_leaf = CheckResult(
        check_id="file_exists:x",
        passed=True,
        score=1.0,
        weight=0.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        status="run",
    )
    trial = _trial_with(_rubric_layer(deterministic_leaf, _judged_leaf(status="skipped")))
    result = TaskResult(
        task_id="t",
        harness="fake",
        report=trial.report,
        passed=True,
        aggregate_score=1.0,
        duration_seconds=0.1,
        transcript="",
        trials=[trial],
    )
    assert task_result_to_dict(result)["uncalibrated_judge"] is False
