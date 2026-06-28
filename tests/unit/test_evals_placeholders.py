"""Tests for the evals ABCs after the R1 runner activation.

The :class:`~coding_agent_playbook.evals.judge.Judge` ABC is still a v2
placeholder (SPEC §15.3): abstract, and calling :meth:`Judge.score` raises
:exc:`NotImplementedError`. The :class:`~coding_agent_playbook.evals.runner.HarnessRunner`
is now **live** (PR R1, Option B): ``run_task`` is a concrete template method (no
longer raises), the abstract hook is ``_invoke_agent``, and the result model is
:class:`~coding_agent_playbook.evals.runner.TaskResult` carrying an
:class:`~coding_agent_playbook.evaluators.types.EvaluationReport` (``CheckResult``
and ``programmatic_checks``/``rubric_scores`` are retired).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.judge import Judge
from coding_agent_playbook.evals.runner import (
    AgentRun,
    EvalReport,
    HarnessRunner,
    TaskResult,
)
from coding_agent_playbook.evals.task import Rubric
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


def test_judge_score_raises_with_v2_pointer() -> None:
    class _Judge(Judge):
        name = "test"

        def score(
            self,
            rubric: Rubric,
            transcript: str,
            scratch_dir_state: dict[str, str],
        ) -> list[float]:
            return super().score(rubric, transcript, scratch_dir_state)  # type: ignore[safe-super]

    judge = _Judge()
    with pytest.raises(NotImplementedError, match=r"15\.3"):
        judge.score(Rubric(criteria=["A"]), "", {})


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
