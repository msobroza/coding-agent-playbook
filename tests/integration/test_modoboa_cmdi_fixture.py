"""Hermetic C2 check: the worked-example fixture runs green under the fake runner."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.evals.loader import load_eval_task_from_dir
from coding_agent_playbook.evals.runner import capture, materialize
from coding_agent_playbook.evals.scoring import score
from coding_agent_playbook.evals.task import Verdict

_TASKS_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "coding_agent_playbook"
    / "resources"
    / "eval_tasks"
)
_FIXTURE = _TASKS_ROOT / "find-injected-vuln-modoboa-cmdi"


@pytest.fixture
def stub_uv_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    real_run = subprocess.run

    def _stub_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "uv":
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, **kwargs)

    monkeypatch.setattr("coding_agent_playbook.evals.runner.subprocess.run", _stub_run)
    monkeypatch.setattr("coding_agent_playbook.evals.runner.shutil.which", lambda _b: "/fake/uv")


def _task() -> Any:
    return load_eval_task_from_dir(_FIXTURE, source_package="coding_agent_playbook")


def test_fixture_compiles_gate_and_rubric() -> None:
    task = _task()
    compiled = task.compiled()
    assert compiled.layers == frozenset({"gate", "rubric"})
    assert task.verdict == Verdict(mode="boolean", trial="gate and rubric")


def test_fixture_runs_with_stub_judge(tmp_path: Path, stub_uv_sync: None) -> None:
    task = _task()
    baseline = materialize(task, tmp_path / "scratch")
    candidate = capture(baseline.repo_root, baseline, "transcript")
    report = score(task, baseline, candidate, judge=StubJudge(default=0.9))
    gate = next(c for c in report.checks if c.check_id == "gate")
    rubric = next(c for c in report.checks if c.check_id == "rubric")
    assert gate.passed is True  # no-op fake runner leaves files unchanged
    assert rubric.status == "run"
    assert rubric.passed is True  # composite 0.9 >= 0.5 fail floor
