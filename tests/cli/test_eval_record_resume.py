"""``playbook eval --record`` saves each finished sample and resumes it; ``--jobs`` runs in parallel.

Driven through ``cli.main`` on the ``fake`` runner, whose ``run_sample`` is
replaced by a canned result, so ``--all`` covers every shipped sample without
materializing any.
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.config.files import CONFIG_FILENAME
from coding_agent_playbook.evals.judge import JudgeError
from coding_agent_playbook.evals.run.fake_runner import FakeRunner
from coding_agent_playbook.evals.run.harness_runner import SampleResult
from coding_agent_playbook.evals.targets import TARGET_ENV_VAR
from coding_agent_playbook.grading.types import EvaluationReport

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.sample import EvalSample

_EVALS = """
[evals.targets.fake-pinned]
harness = "fake"
model = "fake-model-1"
"""


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A consumer repo whose committed config names a pinned fake target."""
    monkeypatch.delenv(TARGET_ENV_VAR, raising=False)
    make_synthetic_repo(tmp_path)
    committed = tmp_path / CONFIG_FILENAME
    committed.write_text(committed.read_text(encoding="utf-8") + _EVALS, encoding="utf-8")
    return tmp_path


class CannedRuns:
    """Stands in for ``FakeRunner.run_sample``: a passing result, or a judge refusal once."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, refuse: str | None = None) -> None:
        self.ran: list[str] = []
        self._refuse = refuse
        self._lock = threading.Lock()
        canned = self

        def run_sample(
            runner: FakeRunner, sample: EvalSample, *_args: Any, **_kwargs: Any
        ) -> SampleResult:
            return canned.run(runner, sample)

        monkeypatch.setattr(FakeRunner, "run_sample", run_sample)

    def run(self, runner: FakeRunner, sample: EvalSample) -> SampleResult:
        with self._lock:
            self.ran.append(sample.id)
            refuse = sample.id == self._refuse
            if refuse:
                self._refuse = None
        if refuse:
            raise JudgeError(f"the judge refused {sample.id}")
        report = EvaluationReport(
            findings=[], warn_count=0, fail_count=0, composite=1.0, passed=True
        )
        return SampleResult(sample.id, runner.name, report, True, 1.0, 0.1, "")


def _record(repo: Path, out_name: str, *flags: str) -> tuple[int, Path]:
    out = repo / "metrics" / out_name
    argv = ["eval", "--run", "--all", "--repo-root", str(repo), "--target", "fake-pinned"]
    return main([*argv, "--record", str(out), *flags]), out


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_a_written_record_removes_its_checkpoint(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    CannedRuns(monkeypatch)
    rc, out = _record(repo, "target.json")
    assert rc == 0
    assert out.is_file()
    assert not (out.parent / "target.json.partial.jsonl").exists()


def test_jobs_write_the_same_file_as_one_job(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    CannedRuns(monkeypatch)
    assert _record(repo, "serial.json")[0] == 0
    rc, parallel = _record(repo, "parallel.json", "--jobs", "4")
    assert rc == 0
    assert _text(parallel) == _text(repo / "metrics" / "serial.json")


def test_an_interrupted_record_resumes_only_what_did_not_finish(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    CannedRuns(monkeypatch)
    assert _record(repo, "whole.json")[0] == 0
    every = sorted(json.loads(_text(repo / "metrics" / "whole.json"))["samples"])
    failing = every[len(every) // 2]

    first = CannedRuns(monkeypatch, refuse=failing)
    rc, out = _record(repo, "target.json")
    assert rc == 2
    assert not out.exists()
    checkpoint = out.parent / "target.json.partial.jsonl"
    assert len(_text(checkpoint).splitlines()) == 1 + every.index(failing)  # header + finished
    assert first.ran == every[: every.index(failing) + 1]

    capsys.readouterr()
    second = CannedRuns(monkeypatch)
    rc, out = _record(repo, "target.json", "--resume")
    assert rc == 0
    assert second.ran == every[every.index(failing) :]
    assert (
        f"checkpoint: {every.index(failing)} finished sample(s) to reuse" in capsys.readouterr().out
    )
    assert _text(out) == _text(repo / "metrics" / "whole.json")
    assert not checkpoint.exists()


def test_without_resume_the_checkpoint_starts_over(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    CannedRuns(monkeypatch, refuse="refactor/extract-helper")
    assert _record(repo, "target.json")[0] == 2
    again = CannedRuns(monkeypatch)
    assert _record(repo, "target.json")[0] == 0
    assert "refactor/extract-helper" in again.ran
    assert len(again.ran) == len(json.loads(_text(repo / "metrics" / "target.json"))["samples"])


def test_an_explicit_checkpoint_path_is_used(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    CannedRuns(monkeypatch, refuse="refactor/extract-helper")
    elsewhere = tmp_path / "kept" / "run.jsonl"
    assert _record(repo, "target.json", "--checkpoint", str(elsewhere))[0] == 2
    assert elsewhere.is_file()
    assert not (repo / "metrics" / "target.json.partial.jsonl").exists()


def test_zero_jobs_are_refused(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _record(repo, "target.json", "--jobs", "0")[0] == 2
    assert "--jobs must be >= 1, got 0" in capsys.readouterr().err


@pytest.mark.parametrize("flags", [("--resume",), ("--jobs", "2"), ("--checkpoint", "c.jsonl")])
def test_record_only_flags_without_record_are_refused(
    repo: Path, capsys: pytest.CaptureFixture[str], flags: tuple[str, ...]
) -> None:
    rc = main(["eval", "--run", "--repo-root", str(repo), "refactor/extract-helper", *flags])
    assert rc == 2
    assert "belong to --record" in capsys.readouterr().err


_EFFORT_JUDGE = """
[evals.endpoints.openai]
api = "openai-responses"
base_url = "https://api.example/v1"
token_env = "FAKE_JUDGE_TOKEN"

[evals.judge]
endpoint = "openai"
model = "gpt-6-luna"
reasoning_effort = "high"
"""


def test_the_judge_reasoning_effort_is_a_recorded_setup_part(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    committed = repo / CONFIG_FILENAME
    committed.write_text(_text(committed) + _EFFORT_JUDGE, encoding="utf-8")
    monkeypatch.setenv("FAKE_JUDGE_TOKEN", "fake-judge-token-0000")
    CannedRuns(monkeypatch)
    out = repo / "metrics" / "judged.json"
    argv = ["eval", "--run", "--repo-root", str(repo), "refactor/extract-helper"]
    flags = ["--target", "fake-pinned", "--record", str(out), "--judge", "llm"]

    assert main([*argv, *flags]) == 0
    assert json.loads(_text(out))["setup"]["judge_reasoning_effort"] == "high"
