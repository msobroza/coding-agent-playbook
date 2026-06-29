"""Renderer tests for the C8 aggregate surface in ``playbook eval --run``.

The text + JSON renderers in :mod:`coding_agent_playbook.commands.eval` surface
the across-trial aggregate result (``pass@k`` / ``pass^k`` over N trials) when a
task authored an ``[aggregate]`` block, and omit it otherwise. These drive the
renderers directly with a synthetic :class:`TaskResult` (no runner / SyncContext)
so they stay fast and focused on the rendering contract.
"""

from __future__ import annotations

from coding_agent_playbook.commands.eval import _format_result_text, _result_to_dict
from coding_agent_playbook.evals.runner import TaskResult
from coding_agent_playbook.evaluators.scope import CostTier, Determinism
from coding_agent_playbook.evaluators.types import (
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
    text = _format_result_text(_aggregate_result())
    assert "aggregate: pass_at_k:verdict@5 = 1.000 (PASS)" in text
    assert "5 trials (4/5 passed)" in text


def test_text_render_omits_aggregate_when_absent() -> None:
    text = _format_result_text(_plain_result())
    assert "aggregate:" not in text


def test_json_render_includes_aggregate_block() -> None:
    payload = _result_to_dict(_aggregate_result())
    assert payload["trials"] == 5
    assert payload["trial_verdicts"] == [True, True, True, True, False]
    assert payload["aggregate"]["check_id"] == "pass_at_k:verdict@5"  # type: ignore[index]
    assert payload["aggregate"]["passed"] is True  # type: ignore[index]


def test_json_render_omits_aggregate_when_absent() -> None:
    payload = _result_to_dict(_plain_result())
    assert "aggregate" not in payload
    assert "trials" not in payload
