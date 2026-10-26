"""Hermetic C2 check: the worked-example fixture runs green under the fake runner."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.evals.run.harness_runner import capture, materialize
from coding_agent_playbook.evals.run.scoring import score
from coding_agent_playbook.evals.sample import Verdict
from coding_agent_playbook.evals.task_registry import load_task_sample
from tests._catalog import CORE_ROOT
from tests.integration.ccv_answers import CORRECT_ANSWER

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SAMPLES_ROOT = CORE_ROOT / "eval_samples"
_FIXTURE = _SAMPLES_ROOT / "find-injected-vulnerability" / "modoboa-cmdi"


@pytest.fixture
def stub_uv_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    real_run = subprocess.run

    def _stub_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "uv":
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, **kwargs)

    monkeypatch.setattr("coding_agent_playbook.evals.run.harness_runner.subprocess.run", _stub_run)
    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.harness_runner.shutil.which", lambda _b: "/fake/uv"
    )


def _sample() -> Any:
    return load_task_sample(_FIXTURE, source_package="coding_agent_playbook")


def test_fixture_compiles_gate_and_rubric() -> None:
    sample = _sample()
    compiled = sample.compiled()
    assert compiled.layers == frozenset({"gate", "rubric"})
    assert sample.verdict == Verdict(mode="boolean", trial="gate and rubric")


def test_fixture_runs_with_stub_judge(tmp_path: Path, stub_uv_sync: None) -> None:
    sample = _sample()
    baseline = materialize(sample, tmp_path / "scratch")
    candidate = capture(baseline.repo_root, baseline, CORRECT_ANSWER[sample.id])
    report = score(sample, baseline, candidate, judge=StubJudge(default=0.9))
    gate = next(c for c in report.checks if c.check_id == "gate")
    rubric = next(c for c in report.checks if c.check_id == "rubric")
    # The no-op fake runner leaves the files unchanged and the answer names CWE-78.
    assert gate.passed is True
    assert rubric.status == "run"
    assert rubric.passed is True  # composite 0.9 >= 0.5 fail floor
