"""``playbook eval --record`` writes each fresh run's answers beside the metrics file (spec D8).

Driven through ``cli.main`` on the ``fake`` runner. :class:`JudgedRuns` replaces
``FakeRunner.run_sample``: it grades the sample's own rubric criteria with the
judge the record hands it, on an artifact naming the sample, so each answer line
shows which judge calls it captured.
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands import _eval_record
from coding_agent_playbook.commands._eval_record_answers import judge_free_checks
from coding_agent_playbook.config.files import CONFIG_FILENAME
from coding_agent_playbook.evals.answers_store import read_answers
from coding_agent_playbook.evals.judge import Judge, JudgeError
from coding_agent_playbook.evals.rejudge import rubric_criteria
from coding_agent_playbook.evals.run.fake_runner import FakeRunner
from coding_agent_playbook.evals.run.harness_runner import SampleResult
from coding_agent_playbook.evals.targets import TARGET_ENV_VAR
from coding_agent_playbook.evals.task_registry import TaskRegistry
from coding_agent_playbook.grading.scope import CostTier, Determinism
from coding_agent_playbook.grading.types import CheckResult, EvaluationReport
from coding_agent_playbook.validation.context import SyncContext
from tests.edition_fixtures import SAMPLE_ID

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.answers_store import StoredRun
    from coding_agent_playbook.evals.sample import EvalSample

_EXTRACT = "refactor/extract-helper"
_RENAME = "refactor/rename-for-clarity"
#: Each refactor sample's judge score, so a mixed-up line shows.
_SCORES = {_EXTRACT: 0.25, _RENAME: 0.75}

_EVALS = """
[evals.targets.fake-pinned]
harness = "fake"
model = "fake-model-1"

[evals.endpoints.openai]
api = "openai-responses"
base_url = "https://api.example/v1"
token_env = "FAKE_JUDGE_TOKEN"

[evals.judge]
endpoint = "openai"
model = "gpt-6-luna"
samples = 2
"""


class ArtifactScoredJudge(Judge):
    """Scores by the sample its artifact names; makes no call."""

    name = "artifact-scored"

    def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
        return _SCORES.get(str(artifact).removeprefix("diff of "), 0.5)


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A consumer repo with a pinned fake target and a judge whose calls stay in-process."""
    monkeypatch.delenv(TARGET_ENV_VAR, raising=False)
    monkeypatch.setenv("FAKE_JUDGE_TOKEN", "fake-judge-token-0000")
    make_synthetic_repo(tmp_path)
    committed = tmp_path / CONFIG_FILENAME
    committed.write_text(committed.read_text(encoding="utf-8") + _EVALS, encoding="utf-8")
    monkeypatch.setattr(
        _eval_record, "build_judge", lambda *_args, **_kwargs: ArtifactScoredJudge()
    )
    return tmp_path


class JudgedRuns:
    """Stands in for ``FakeRunner.run_sample``: grades the rubric, or fails one sample once."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        fail: str | None = None,
        barrier: threading.Barrier | None = None,
    ) -> None:
        self.ran: list[str] = []
        self._fail = fail
        self._barrier = barrier
        self._lock = threading.Lock()
        canned = self

        def run_sample(
            runner: FakeRunner, sample: EvalSample, _scratch: Path, **kwargs: Any
        ) -> SampleResult:
            return canned.run(runner, sample, kwargs["judge"], kwargs["judge_samples"])

        monkeypatch.setattr(FakeRunner, "run_sample", run_sample)

    def run(
        self, runner: FakeRunner, sample: EvalSample, judge: Judge | None, n: int
    ) -> SampleResult:
        with self._lock:
            self.ran.append(sample.id)
            fail = sample.id == self._fail
            if fail:
                self._fail = None
        if fail:
            raise JudgeError(f"the judge refused {sample.id}")
        if self._barrier is not None:
            self._barrier.wait()  # both samples are running at once
        for criterion, _weight in rubric_criteria(sample):
            if judge is not None:
                judge.score_criterion(criterion, f"diff of {sample.id}", n=n)
        return _result(runner, sample)


def _result(runner: FakeRunner, sample: EvalSample) -> SampleResult:
    gate = CheckResult(
        "gate", True, 1.0, 0.0, True, Determinism.DETERMINISTIC, CostTier.DETERMINISTIC
    )
    judged = CheckResult("rubric", True, 1.0, 0.0, False, Determinism.JUDGED, CostTier.JUDGED)
    report = EvaluationReport(
        findings=[], warn_count=0, fail_count=0, composite=1.0, passed=True, checks=[gate, judged]
    )
    return SampleResult(sample.id, runner.name, report, True, 1.0, 0.1, "")


def _record(repo: Path, selection: str, *flags: str) -> tuple[int, Path]:
    out = repo / "metrics" / "target.json"
    argv = ["eval", "--run", "--repo-root", str(repo), "--target", "fake-pinned"]
    return main([*argv, *selection.split(), "--record", str(out), *flags]), out


def _answers(out: Path) -> list[StoredRun]:
    return read_answers(out.with_name(out.name + ".answers.jsonl.gz"))


def _sample(repo: Path, sample_id: str) -> EvalSample:
    ctx = SyncContext.from_repo(repo)
    registry = TaskRegistry.from_catalog(ctx.artifact_source, ctx.prompts_resolved)
    return next(iter(registry.select(sample_id)))


def test_record_writes_one_answer_line_per_run(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    JudgedRuns(monkeypatch)
    rc, out = _record(repo, "refactor", "--runs", "3", "--judge", "llm")
    assert rc == 0
    lines = _answers(out)
    assert [(line.sample, line.run) for line in lines] == [
        (sample, run) for sample in (_EXTRACT, _RENAME) for run in range(3)
    ]
    metrics = json.loads(out.read_text(encoding="utf-8"))
    first = lines[0]
    assert first.inputs_digest == metrics["samples"][_EXTRACT]["inputs_digest"]
    assert first.artifact == f"diff of {_EXTRACT}"
    assert first.checks == {"gate": 1.0}  # the judged rubric layer is left out
    criteria = rubric_criteria(_sample(repo, _EXTRACT))
    assert [(c.criterion, c.weight, c.score, c.n) for c in first.criteria] == [
        (text, weight, 0.25, 2) for text, weight in criteria
    ]
    assert first.judge == {
        key: metrics["setup"].get(key)
        for key in (
            "judge_model",
            "judge_endpoint_fingerprint",
            "judge_samples",
            "judge_version",
            "judge_reasoning_effort",
        )
    }
    assert first.judge["judge_model"] == "gpt-6-luna"


def test_a_run_without_a_judge_stores_no_artifact_and_no_scores(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    JudgedRuns(monkeypatch)
    rc, out = _record(repo, _EXTRACT)
    assert rc == 0
    (line,) = _answers(out)
    assert line.artifact is None
    assert line.criteria
    assert {(c.score, c.n) for c in line.criteria} == {(None, 0)}


def test_answers_flag_names_the_answers_file(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    JudgedRuns(monkeypatch)
    elsewhere = tmp_path / "kept" / "answers.jsonl.gz"
    rc, out = _record(repo, _EXTRACT, "--answers", str(elsewhere))
    assert rc == 0
    assert [line.sample for line in read_answers(elsewhere)] == [_EXTRACT]
    assert not out.with_name(out.name + ".answers.jsonl.gz").exists()


def test_carried_samples_write_no_answer_lines(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    JudgedRuns(monkeypatch)
    baseline = repo / "baseline.json"
    argv = ["eval", "--run", "--all", "--repo-root", str(repo), "--target", "fake-pinned"]
    assert main([*argv, "--record", str(baseline)]) == 0
    every = json.loads(baseline.read_text(encoding="utf-8"))["samples"]

    rc, out = _record(repo, "--all", "--carry-from", str(baseline))
    assert rc == 0
    assert len(json.loads(out.read_text(encoding="utf-8"))["samples"]) == len(every)
    assert _answers(out) == []


def test_answers_of_parallel_runs_are_not_mixed(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review Focus 2: one judge per run, so two samples grading at once keep their own calls.
    JudgedRuns(monkeypatch, barrier=threading.Barrier(2, timeout=10))
    rc, out = _record(repo, "refactor", "--judge", "llm", "--jobs", "2")
    assert rc == 0
    lines = _answers(out)
    assert [line.sample for line in lines] == [_EXTRACT, _RENAME]
    for line in lines:
        assert line.artifact == f"diff of {line.sample}"
        assert {c.score for c in line.criteria} == {_SCORES[line.sample]}


def test_a_resumed_record_writes_the_checkpointed_answers(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review Focus 3: the first sample's answers come back from the checkpoint.
    first = JudgedRuns(monkeypatch, fail=_RENAME)
    rc, out = _record(repo, "refactor", "--judge", "llm")
    assert rc == 2
    assert first.ran == [_EXTRACT, _RENAME]

    second = JudgedRuns(monkeypatch)
    rc, out = _record(repo, "refactor", "--judge", "llm", "--resume")
    assert rc == 0
    assert second.ran == [_RENAME]
    lines = _answers(out)
    assert [(line.sample, line.artifact) for line in lines] == [
        (_EXTRACT, f"diff of {_EXTRACT}"),
        (_RENAME, f"diff of {_RENAME}"),
    ]
    assert {c.score for c in lines[0].criteria} == {_SCORES[_EXTRACT]}


def test_controls_write_no_answer_lines(engine_catalog: Path, repo: Path) -> None:
    rc, out = _record(repo, SAMPLE_ID, "--runs", "2")
    assert rc == 0
    assert json.loads(out.read_text(encoding="utf-8"))["controls"][SAMPLE_ID]["runs"] == 2
    assert [(line.sample, line.run) for line in _answers(out)] == [(SAMPLE_ID, 0), (SAMPLE_ID, 1)]


def test_rubric_criteria_are_the_sample_rubric_texts_and_weights(repo: Path) -> None:
    criteria = rubric_criteria(_sample(repo, _EXTRACT))
    assert [weight for _, weight in criteria] == [0.3, 0.4, 0.15, 0.15]
    assert criteria[0][0].startswith("The extracted helper has a name")


def test_judge_free_checks_drop_judged_layers_and_their_leaves() -> None:
    leaf = CheckResult("judge:x", True, 0.5, 1.0, False, Determinism.JUDGED, CostTier.JUDGED)
    rubric = CheckResult(
        "rubric", True, 0.5, 0.0, False, Determinism.JUDGED, CostTier.JUDGED, subresults=(leaf,)
    )
    gate = CheckResult(
        "gate", False, 0.0, 0.0, True, Determinism.DETERMINISTIC, CostTier.DETERMINISTIC
    )
    report = EvaluationReport(
        findings=[], warn_count=0, fail_count=1, composite=0.0, passed=False, checks=[gate, rubric]
    )
    result = SampleResult("s", "fake", report, False, 0.0, 0.1, "")
    assert judge_free_checks(result) == {"gate": 0.0}
