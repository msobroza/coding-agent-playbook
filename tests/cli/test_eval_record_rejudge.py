"""``playbook eval --record --carry-from RELEASES`` re-grades stored answers after a judge change (spec D9).

Driven through ``cli.main`` on the ``fake`` runner (``tests.cli.test_eval_record_answers``):
a first record with a judge writes the metrics and answers that a hand-made
release ``9.9.2`` reuses, its setup changed in the judge model only. The second
record's judge is a :class:`ScoringJudge`, so each test can count its calls.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands import _eval_record
from coding_agent_playbook.evals.answers_store import (
    ArtifactRef,
    StoredCriterion,
    StoredRun,
    answers_path,
    read_answers,
    write_answers,
)
from coding_agent_playbook.evals.judge import Judge, JudgeError
from coding_agent_playbook.evals.rejudge import rubric_criteria
from coding_agent_playbook.evals.run.fake_runner import FakeRunner
from coding_agent_playbook.evals.run.harness_runner import SampleResult
from coding_agent_playbook.grading.types import EvaluationReport
from tests.cli.test_eval_record_answers import _EXTRACT, _RENAME, JudgedRuns, _sample, repo

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    import pytest

    from coding_agent_playbook.evals.sample import EvalSample

__all__ = ["repo"]  # the fixture, imported so pytest finds it here

_RELEASE = "9.9.2"
_TARGET = "fake-pinned"
_OLD_JUDGE = "gpt-6-old"


class ScoringJudge(Judge):
    """Scores every criterion ``score`` and logs each artifact; raises on ``refuse``."""

    name = "scoring"

    def __init__(self, score: float, refuse: str | None = None) -> None:
        self.value = score
        self.refuse = refuse
        self.artifacts: list[str] = []

    def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
        if artifact == self.refuse:
            raise JudgeError(f"the judge refused {artifact}")
        self.artifacts.append(str(artifact))
        return self.value


def _argv(repo: Path, out: Path, *flags: str) -> list[str]:
    argv = ["eval", "--run", "--all", "--repo-root", str(repo), "--target", _TARGET]
    return [*argv, "--judge", "llm", "--runs", "2", "--record", str(out), *flags]


def _base(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A judged record of every sample, the source of the hand-made release."""
    JudgedRuns(monkeypatch)
    base = repo / "metrics" / "base.json"
    assert main(_argv(repo, base)) == 0
    return base


def _release(base: Path, *, keep: Sequence[str] | None, answers: bool = True) -> Path:
    """``base`` as release 9.9.2 judged by another model, holding ``keep`` (``None``: all)."""
    releases = base.parent.parent / "releases"
    data: dict[str, Any] = json.loads(base.read_text(encoding="utf-8"))
    data["release"] = _RELEASE
    data["setup"]["judge_model"] = _OLD_JUDGE
    if keep is not None:
        data["samples"] = {sample_id: data["samples"][sample_id] for sample_id in keep}
    path = releases / _RELEASE / "metrics" / f"{_TARGET}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    if answers:
        lines = read_answers(base.with_name(base.name + ".answers.jsonl.gz"))
        kept = [line for line in lines if keep is None or line.sample in keep]
        write_answers(answers_path(releases, _RELEASE, _TARGET), kept)
    return releases


def _rerecord(
    repo: Path, releases: Path, monkeypatch: pytest.MonkeyPatch, judge: Judge, *flags: str
) -> tuple[int, Path]:
    monkeypatch.setattr(_eval_record, "build_judge", lambda *_args, **_kwargs: judge)
    out = repo / "metrics" / "next.json"
    return main(_argv(repo, out, "--carry-from", str(releases), *flags)), out


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _criteria_count(repo: Path, sample_id: str) -> int:
    return len(rubric_criteria(_sample(repo, sample_id)))


def test_without_stored_answers_the_sample_reruns(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    releases = _release(_base(repo, monkeypatch), keep=[_EXTRACT], answers=False)
    runs = JudgedRuns(monkeypatch)
    capsys.readouterr()

    rc, out = _rerecord(repo, releases, monkeypatch, ScoringJudge(0.9))

    assert rc == 0
    assert f"  {_EXTRACT}: answers not stored" in capsys.readouterr().out
    assert _EXTRACT in runs.ran
    assert "rejudged_from" not in _load(out)["samples"][_EXTRACT]
    assert _load(out)["summary"]["rejudged"] == 0
    assert "judge_change" not in _load(out)


def test_rejudge_calls_the_judge_but_never_the_runner(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _base(repo, monkeypatch)
    releases = _release(base, keep=None)
    stored = read_answers(answers_path(releases, _RELEASE, _TARGET))

    def control_only(runner: FakeRunner, sample: EvalSample, *_a: Any, **kw: Any) -> SampleResult:
        # Edition controls always rerun (spec D1); a sample on the current text must not.
        assert kw.get("edition") is not None, f"the runner ran {sample.id}"
        report = EvaluationReport(
            findings=[], warn_count=0, fail_count=0, composite=1.0, passed=True
        )
        return SampleResult(sample.id, runner.name, report, True, 1.0, 0.1, "")

    monkeypatch.setattr(FakeRunner, "run_sample", control_only)
    judge = ScoringJudge(0.9)

    rc, out = _rerecord(repo, releases, monkeypatch, judge)

    assert rc == 0
    expected = sum(len(line.criteria) for line in stored if line.artifact is not None)
    assert len(judge.artifacts) == expected
    summary = _load(out)["summary"]
    assert (summary["rerun"], summary["carried"]) == (0, 0)
    assert summary["rejudged"] == len(_load(base)["samples"])


def test_a_rejudged_entry_records_its_sources(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = _base(repo, monkeypatch)
    releases = _release(base, keep=[_EXTRACT])
    runs = JudgedRuns(monkeypatch)
    capsys.readouterr()

    rc, out = _rerecord(repo, releases, monkeypatch, ScoringJudge(0.1))

    assert rc == 0
    assert _EXTRACT not in runs.ran
    printed = capsys.readouterr().out
    assert "1 rejudged" in printed
    assert f"  rejudged from {_RELEASE} ({_TARGET}): 1" in printed
    data = _load(out)
    entry = data["samples"][_EXTRACT]
    commit = _load(base)["commit"]
    assert entry["rejudged_from"]["release"] == _RELEASE
    assert entry["rejudged_from"]["commit"] == commit
    assert entry["rejudged_from"]["judge"]["judge_model"] == _OLD_JUDGE
    assert entry["measured_in"] == {"release": _RELEASE, "commit": commit, "target": _TARGET}
    assert data["summary"]["rejudged"] == 1
    # The canned base runs all passed; the new judge's 0.1 fails the rubric of each.
    assert (_load(base)["samples"][_EXTRACT]["passes"], entry["passes"]) == (2, 0)
    lines = read_answers(out.with_name(out.name + ".answers.jsonl.gz"))
    mine = [line for line in lines if line.sample == _EXTRACT]
    assert [line.run for line in mine] == [0, 1]
    for line in mine:
        assert (line.artifact, line.artifact_ref) == (None, ArtifactRef(_RELEASE, _TARGET))
        assert {criterion.score for criterion in line.criteria} == {0.1}
        assert line.judge["judge_model"] == "gpt-6-luna"


def test_a_fail_fast_gate_failure_is_not_regraded(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    releases = _release(_base(repo, monkeypatch), keep=[_EXTRACT])
    path = answers_path(releases, _RELEASE, _TARGET)
    first, second = read_answers(path)
    skipped = tuple(StoredCriterion(c.criterion, c.weight, None, 0) for c in first.criteria)
    gate_lost = StoredRun(
        first.sample, first.inputs_digest, 0, None, {"gate": 0.0}, skipped, first.judge
    )
    write_answers(path, [gate_lost, second])
    JudgedRuns(monkeypatch)
    judge = ScoringJudge(0.9)

    rc, out = _rerecord(repo, releases, monkeypatch, judge)

    assert rc == 0
    assert judge.artifacts.count(f"diff of {_EXTRACT}") == _criteria_count(repo, _EXTRACT)
    entry = _load(out)["samples"][_EXTRACT]
    assert (entry["passes"], entry["runs"]) == (1, 2)
    lines = read_answers(out.with_name(out.name + ".answers.jsonl.gz"))
    run0 = next(line for line in lines if (line.sample, line.run) == (_EXTRACT, 0))
    assert {criterion.score for criterion in run0.criteria} == {None}
    assert run0.checks == {"gate": 0.0}


def test_an_unreadable_answers_file_reruns_its_samples(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    releases = _release(_base(repo, monkeypatch), keep=[_EXTRACT])
    path = answers_path(releases, _RELEASE, _TARGET)
    path.write_bytes(b"not a gzip file")
    runs = JudgedRuns(monkeypatch)
    capsys.readouterr()

    rc, _out = _rerecord(repo, releases, monkeypatch, ScoringJudge(0.9))

    assert rc == 0
    assert f"  {_EXTRACT}: answers unreadable: {path}" in capsys.readouterr().out
    assert _EXTRACT in runs.ran


def test_a_judge_error_while_regrading_refuses_the_record(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    releases = _release(_base(repo, monkeypatch), keep=[_EXTRACT, _RENAME])
    JudgedRuns(monkeypatch)

    refusing = ScoringJudge(0.9, refuse=f"diff of {_RENAME}")
    rc, out = _rerecord(repo, releases, monkeypatch, refusing)

    assert rc == 2
    assert not out.exists()
    checkpoint = out.with_name(out.name + ".partial.jsonl")
    rows = [json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()]
    kept = {(row["kind"], row["sample_id"]) for row in rows[1:]}
    assert ("rejudge", _EXTRACT) in kept
    assert ("rejudge", _RENAME) not in kept

    runs = JudgedRuns(monkeypatch)
    judge = ScoringJudge(0.9)
    rc, out = _rerecord(repo, releases, monkeypatch, judge, "--resume")

    assert rc == 0
    assert runs.ran == []
    assert set(judge.artifacts) == {f"diff of {_RENAME}"}
    assert _load(out)["summary"]["rejudged"] == 2
    # The checkpoint's re-judged record counts toward the agreement too (D10).
    assert _load(out)["judge_change"]["runs"] == 4


def test_a_rejudged_record_writes_judge_change_and_prints_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The old judge scored every criterion 0.25 (extract) and 0.75 (rename): the
    # new judge's 0.9 flips extract's rubric verdict only (spec D10).
    releases = _release(_base(repo, monkeypatch), keep=[_EXTRACT, _RENAME])
    JudgedRuns(monkeypatch)
    capsys.readouterr()

    rc, out = _rerecord(repo, releases, monkeypatch, ScoringJudge(0.9))

    assert rc == 0
    change = _load(out)["judge_change"]
    assert [part["judge_model"] for part in change["from"]] == [_OLD_JUDGE]
    assert change["to"]["judge_model"] == "gpt-6-luna"
    assert (change["runs"], change["pass_agreement"]) == (4, 0.5)
    assert change["mean_abs_score_diff"] == 0.4
    assert change["tasks"] == {
        "refactor": {"runs": 4, "pass_agreement": 0.5, "mean_abs_score_diff": 0.4}
    }
    expected = (
        f"judge change: {_OLD_JUDGE} -> gpt-6-luna: pass agreement 50% over 4 runs, mean |Δ| 0.40"
    )
    assert expected in capsys.readouterr().out
