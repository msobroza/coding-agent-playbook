"""``playbook eval --run --all --record OUT --carry-from PREVIOUS.json`` (#329 ticket 05).

Driven through ``cli.main`` with the ``fake`` runner, whose ``run_sample`` is
replaced by a canned passing result that records each sample it ran, so a test
can tell exactly which samples reran. No harness CLI and no judge run.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

import coding_agent_playbook
from coding_agent_playbook.cli import main
from coding_agent_playbook.commands import _eval_record
from coding_agent_playbook.config.files import CONFIG_FILENAME
from coding_agent_playbook.evals.prompting import render_prompt
from coding_agent_playbook.evals.release_metrics_schema import validate_release_metrics
from coding_agent_playbook.evals.run.fake_runner import FakeRunner
from coding_agent_playbook.evals.run.harness_runner import SampleResult
from coding_agent_playbook.evals.targets import TARGET_ENV_VAR
from coding_agent_playbook.grading.types import EvaluationReport
from coding_agent_playbook.validation.context import SyncContext
from tests.edition_fixtures import SAMPLE_ID, TAG

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.sample import EvalSample

_EVALS = """
[evals.targets.fake-pinned]
harness = "fake"
model = "fake-model-1"

[evals.targets.fake-other]
harness = "fake"
model = "fake-model-1"
"""

#: A rule only some prompts include (``refactor``), so editing it reruns a strict subset.
_RULE = "core/skills/python-coding/rules/python-pure-core.md"
_MARKER = "Carry-from marker line (#329 ticket 05)."


class _RunLog:
    """Replaces the fake runner's ``run_sample``: a canned pass, logging ``(sample id, edition)``."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[tuple[str, str | None]] = []
        calls = self.calls

        def canned_run(runner: FakeRunner, sample: EvalSample, *_a: Any, **kw: Any) -> SampleResult:
            edition = kw.get("edition")
            calls.append((sample.id, edition.tag if edition is not None else None))
            report = EvaluationReport(
                findings=[], warn_count=0, fail_count=0, composite=1.0, passed=True
            )
            return SampleResult(sample.id, runner.name, report, True, 1.0, 0.1, "")

        monkeypatch.setattr(FakeRunner, "run_sample", canned_run)

    def heads(self) -> set[str]:
        """The samples that ran on the current text."""
        return {sample_id for sample_id, edition in self.calls if edition is None}

    def controls(self) -> set[str]:
        """The samples that ran on their edition."""
        return {sample_id for sample_id, edition in self.calls if edition is not None}


@pytest.fixture
def consumer(tmp_path: Path, make_synthetic_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A consumer repo naming two fake targets; the engine catalog is the shipped one."""
    monkeypatch.delenv(TARGET_ENV_VAR, raising=False)
    (tmp_path / "consumer").mkdir()
    repo: Path = make_synthetic_repo(tmp_path / "consumer")
    committed = repo / CONFIG_FILENAME
    committed.write_text(committed.read_text(encoding="utf-8") + _EVALS, encoding="utf-8")
    return repo


def _record(repo: Path, name: str, *flags: str, target: str = "fake-pinned") -> tuple[int, Path]:
    out = repo / "metrics" / f"{name}.json"
    argv = ["eval", "--run", "--all", "--repo-root", str(repo), "--record", str(out)]
    rc = main([*argv, "--target", target, *flags])
    return rc, out


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    validate_release_metrics(data)
    return data


def _carry(repo: Path, name: str, baseline: Path, *flags: str) -> tuple[int, Path]:
    return _record(repo, name, "--carry-from", str(baseline), *flags)


def _all_ids(repo: Path) -> set[str]:
    return {s.id for s in SyncContext.from_repo(repo).artifact_source.list_eval_samples()}


def test_an_unchanged_catalog_and_setup_runs_nothing_and_copies_the_baseline(
    consumer: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    log = _RunLog(monkeypatch)
    rc, base = _record(consumer, "base")
    assert rc == 0
    log.calls.clear()
    capsys.readouterr()

    rc, out = _carry(consumer, "next", base)
    assert rc == 0
    assert log.calls == []
    baseline, carried = _load(base), _load(out)
    for sample_id, entry in carried["samples"].items():
        assert entry.pop("measured_in") == {
            "release": baseline["release"],
            "commit": baseline["commit"],
        }
        assert entry == baseline["samples"][sample_id]
    assert set(carried["samples"]) == set(baseline["samples"])
    for key in ("target", "setup_digest", "setup", "controls"):
        assert carried[key] == baseline[key]
    summary = carried["summary"]
    assert (summary["rerun"], summary["carried"]) == (0, len(baseline["samples"]))
    for key in ("samples", "runs", "pass_rate", "mean_score"):
        assert summary[key] == baseline["summary"][key]
    assert f"0 rerun, {len(baseline['samples'])} carried" in capsys.readouterr().out


def _prompts_with_marker(repo: Path) -> set[str]:
    samples = SyncContext.from_repo(repo).artifact_source.list_eval_samples()
    return {s.id for s in samples if _MARKER in render_prompt(s, strict=False)}


def test_changing_one_included_rule_reruns_exactly_the_samples_that_include_it(
    engine_catalog: Path,
    consumer: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = _RunLog(monkeypatch)
    rc, base = _record(consumer, "base")
    assert rc == 0
    rule = engine_catalog / _RULE
    rule.write_text(rule.read_text(encoding="utf-8") + f"\n{_MARKER}\n", encoding="utf-8")
    expected = _prompts_with_marker(consumer)
    assert expected
    assert expected < _all_ids(consumer)
    log.calls.clear()
    capsys.readouterr()

    rc, out = _carry(consumer, "next", base)
    assert rc == 0
    assert log.heads() == expected
    data = _load(out)
    assert {i for i, e in data["samples"].items() if "measured_in" not in e} == expected
    printed = capsys.readouterr().out
    for sample_id in expected:
        assert f"  {sample_id}: inputs digest changed" in printed


def test_edition_controls_always_rerun(
    engine_catalog: Path,
    consumer: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = _RunLog(monkeypatch)
    rc, base = _record(consumer, "base")
    assert rc == 0
    log.calls.clear()
    capsys.readouterr()

    rc, out = _carry(consumer, "next", base)
    assert rc == 0
    assert log.heads() == set()
    assert log.controls() == {SAMPLE_ID}
    data = _load(out)
    assert data["controls"][SAMPLE_ID]["graded"] == TAG
    assert "measured_in" not in data["controls"][SAMPLE_ID]
    printed = capsys.readouterr().out
    assert f"{SAMPLE_ID} (edition control): edition controls always rerun" in printed


def test_a_setup_change_reruns_every_sample_and_names_the_part(
    consumer: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    log = _RunLog(monkeypatch)
    rc, base = _record(consumer, "base", "--runs", "1")
    assert rc == 0
    log.calls.clear()
    capsys.readouterr()

    rc, out = _carry(consumer, "next", base, "--runs", "2")
    assert rc == 0
    assert log.heads() == _all_ids(consumer)
    printed = capsys.readouterr().out
    assert "every sample reruns, the setup differs from the baseline in runs" in printed
    data = _load(out)
    assert all("measured_in" not in entry for entry in data["samples"].values())
    assert (data["summary"]["rerun"], data["summary"]["carried"]) == (len(data["samples"]), 0)


def test_a_baseline_without_the_digests_reruns_every_sample_and_says_why(
    consumer: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    log = _RunLog(monkeypatch)
    rc, base = _record(consumer, "base")
    assert rc == 0
    keyless = _load(base)
    del keyless["setup_digest"], keyless["setup"]
    for entry in keyless["samples"].values():
        del entry["inputs_digest"]
    base.write_text(json.dumps(keyless), encoding="utf-8")
    log.calls.clear()
    capsys.readouterr()

    rc, _out = _carry(consumer, "next", base)
    assert rc == 0
    assert log.heads() == _all_ids(consumer)
    assert "every sample reruns, the baseline records no setup digest" in capsys.readouterr().out


def test_measured_in_survives_two_carry_hops(
    consumer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _RunLog(monkeypatch)
    monkeypatch.setattr(_eval_record, "_head_commit", lambda _root: "c0ffee1")
    monkeypatch.setattr(coding_agent_playbook, "__version__", "9.9.1")
    rc, first = _record(consumer, "first")
    assert rc == 0
    monkeypatch.setattr(_eval_record, "_head_commit", lambda _root: "c0ffee2")
    monkeypatch.setattr(coding_agent_playbook, "__version__", "9.9.2")
    rc, second = _carry(consumer, "second", first)
    assert rc == 0
    monkeypatch.setattr(_eval_record, "_head_commit", lambda _root: "c0ffee3")
    monkeypatch.setattr(coding_agent_playbook, "__version__", "9.9.3")
    rc, third = _carry(consumer, "third", second)
    assert rc == 0

    data = _load(third)
    assert data["release"] == "9.9.3"
    measured = {json.dumps(e["measured_in"], sort_keys=True) for e in data["samples"].values()}
    assert measured == {json.dumps({"commit": "c0ffee1", "release": "9.9.1"}, sort_keys=True)}


def test_a_baseline_for_another_target_is_refused_before_any_run(
    consumer: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    log = _RunLog(monkeypatch)
    rc, base = _record(consumer, "base", target="fake-other")
    assert rc == 0
    log.calls.clear()

    rc, out = _carry(consumer, "next", base)
    assert rc == 2
    assert log.calls == []
    assert not out.exists()
    assert "the baseline is for target 'fake-other', not 'fake-pinned'" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (
            ["eval", "--run", "--all", "--carry-from", "b.json", "--target", "fake-pinned"],
            "pass --record too",
        ),
        (
            [
                "eval",
                "refactor/extract-helper",
                "--run",
                "--record",
                "x.json",
                "--carry-from",
                "b.json",
                "--target",
                "fake-pinned",
            ],
            "--carry-from needs --all",
        ),
        (
            ["eval", "--all", "--record", "x.json", "--carry-from", "b.json"],
            "need --run",
        ),
    ],
)
def test_carry_from_without_record_or_all_is_a_usage_error(
    consumer: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    message: str,
) -> None:
    log = _RunLog(monkeypatch)
    assert main([*argv, "--repo-root", str(consumer)]) == 2
    assert message in capsys.readouterr().err
    assert log.calls == []
