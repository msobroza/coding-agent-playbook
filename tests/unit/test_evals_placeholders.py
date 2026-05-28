"""Tests for the v2 placeholder ABCs (SPEC §15.3).

These ship in v1's tree so the module layout doesn't change when v2 lands
(SPEC §15.4). The interfaces are abstract and any attempt to actually invoke
``run_task`` / ``score`` raises :exc:`NotImplementedError` with a pointer
to SPEC §15.3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent_playbook.evals.judge import Judge
from coding_agent_playbook.evals.runner import (
    CheckResult,
    EvalReport,
    HarnessRunner,
    TaskResult,
)
from coding_agent_playbook.evals.task import EvalTask, Rubric


def test_harness_runner_is_abstract() -> None:
    with pytest.raises(TypeError):
        HarnessRunner()  # type: ignore[abstract]


def test_judge_is_abstract() -> None:
    with pytest.raises(TypeError):
        Judge()  # type: ignore[abstract]


def test_run_task_raises_with_v2_pointer(tmp_path: Path) -> None:
    """A concrete subclass that calls back into the abstract body must raise
    NotImplementedError with a pointer to SPEC §15.3 so users get a
    one-line breadcrumb when they wire a custom runner before v2."""

    class _Runner(HarnessRunner):
        name = "test"

        def run_task(self, task: EvalTask, scratch_dir: Path) -> TaskResult:
            return super().run_task(task, scratch_dir)  # type: ignore[safe-super]

    runner = _Runner()
    task = EvalTask(
        id="x",
        prompt_id="p",
        description="d",
        source_path=tmp_path / "task.toml",
        source_package="<test>",
    )
    with pytest.raises(NotImplementedError, match="15.3"):
        runner.run_task(task, tmp_path)


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
    with pytest.raises(NotImplementedError, match="15.3"):
        judge.score(Rubric(criteria=["A"]), "", {})


def test_check_result_is_a_dataclass() -> None:
    result = CheckResult(name="files_must_contain[0]", passed=True, detail="ok")
    assert result.name == "files_must_contain[0]"
    assert result.passed is True
    assert result.detail == "ok"


def test_task_result_and_eval_report_are_dataclasses() -> None:
    check = CheckResult(name="files_created[0]", passed=True, detail="")
    tr = TaskResult(
        task_id="t",
        harness="claude_code",
        programmatic_checks=[check],
        rubric_scores=None,
        aggregate_score=1.0,
        passed=True,
        duration_seconds=0.01,
        transcript="ok",
    )
    report = EvalReport(
        engine_version="0.1.0",
        harness="claude_code",
        task_results=[tr],
        aggregate_pass_rate=1.0,
        timestamp="2026-01-01T00:00:00Z",
    )
    assert report.task_results[0].task_id == "t"
