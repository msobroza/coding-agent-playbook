"""Tests for the evals ABCs after the R1 runner + R2 judge activation.

The :class:`~coding_agent_playbook.evals.judge.Judge` ABC is now **live** (PR R2,
Option A): :meth:`Judge.score_criterion` is the single abstract primitive and
:meth:`Judge.score` is a concrete batch wrapper over it (no more
``NotImplementedError`` placeholder). The
:class:`~coding_agent_playbook.evals.run.harness_runner.HarnessRunner` is live (PR R1, Option
B): ``run_task`` is a concrete template method, the abstract hook is
``_invoke_agent``, and the result model is
:class:`~coding_agent_playbook.evals.run.harness_runner.TaskResult` carrying an
:class:`~coding_agent_playbook.evaluators.types.EvaluationReport` (``CheckResult``
and ``programmatic_checks``/``rubric_scores`` are retired).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.judge import Judge
from coding_agent_playbook.evals.run.harness_runner import (
    AgentRun,
    EvalReport,
    HarnessRunner,
    TaskResult,
)
from coding_agent_playbook.evaluators import EvaluationReport

if TYPE_CHECKING:
    from pathlib import Path


def test_harness_runner_is_abstract() -> None:
    with pytest.raises(TypeError):
        HarnessRunner()  # type: ignore[abstract]


def test_judge_is_abstract() -> None:
    with pytest.raises(TypeError):
        Judge()  # type: ignore[abstract]


def test_invoke_agent_is_the_only_abstract_hook(tmp_path: Path) -> None:
    """A subclass only has to implement ``_invoke_agent``; ``run_task`` is concrete.

    Implementing the single hook makes the class instantiable (no abstract
    ``run_task`` left), proving the template method moved to ``_invoke_agent``.
    """

    class _Runner(HarnessRunner):
        name = "test"

        def _invoke_agent(self, prompt: str, scratch_dir: Path) -> AgentRun:
            return AgentRun(transcript="", returncode=0)

    runner = _Runner()
    assert runner.name == "test"


def test_judge_score_criterion_is_the_only_abstract_hook() -> None:
    """A subclass only has to implement ``score_criterion``; ``score`` is concrete."""

    class _Judge(Judge):
        name = "test"

        def score_criterion(self, criterion: str, artifact: object, n: int = 1) -> float:
            return 0.5

    judge = _Judge()  # instantiable => score_criterion is the only abstract hook
    assert judge.score_criterion("c", "art") == 0.5


def test_judge_score_batch_wraps_score_criterion() -> None:
    """``Judge.score`` maps the per-criterion primitive over a criteria list (Option A)."""

    class _Judge(Judge):
        name = "test"

        def __init__(self) -> None:
            self.seen: list[tuple[str, object, int]] = []

        def score_criterion(self, criterion: str, artifact: object, n: int = 1) -> float:
            self.seen.append((criterion, artifact, n))
            return {"A": 0.2, "B": 0.8}[criterion]

    judge = _Judge()
    scores = judge.score(["A", "B"], "transcript-text", {})
    assert scores == [0.2, 0.8]
    # The batch wrapper passes the transcript as the artifact, n=1 each.
    assert judge.seen == [("A", "transcript-text", 1), ("B", "transcript-text", 1)]


def test_task_result_carries_an_evaluation_report() -> None:
    """Option B: ``TaskResult.report`` is the unified :class:`EvaluationReport`."""
    report = EvaluationReport(findings=[], warn_count=0, fail_count=0, composite=None, passed=True)
    tr = TaskResult(
        task_id="t",
        harness="fake",
        report=report,
        passed=True,
        aggregate_score=1.0,
        duration_seconds=0.01,
        transcript="ok",
    )
    assert tr.report is report
    assert tr.passed is True


def test_eval_report_aggregate_pass_rate_reads_report_passed() -> None:
    """``EvalReport.aggregate_pass_rate`` is the mean of ``tr.passed``."""

    def _tr(passed: bool) -> TaskResult:
        report = EvaluationReport(
            findings=[], warn_count=0, fail_count=0, composite=None, passed=passed
        )
        return TaskResult(
            task_id="t",
            harness="fake",
            report=report,
            passed=report.passed,
            aggregate_score=1.0 if passed else 0.0,
            duration_seconds=0.0,
            transcript="",
        )

    results = [_tr(True), _tr(False), _tr(True)]
    rate = EvalReport.pass_rate(results)
    assert rate == pytest.approx(2 / 3)
    assert EvalReport.pass_rate([]) == 0.0
