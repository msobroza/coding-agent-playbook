"""Building and validating a release metrics file from fake run results (spec #281 ticket 07).

No runner and no CLI: each :class:`SampleResult` is built by hand, so the file's
numbers can be checked exactly.
"""

from __future__ import annotations

import dataclasses
import json
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.evals.endpoints import Endpoint
from coding_agent_playbook.evals.record_checkpoint import RecordCheckpoint
from coding_agent_playbook.evals.release_carry import merge_carried, plan_carry
from coding_agent_playbook.evals.release_metrics import (
    GRADED_HEAD,
    RecordedTarget,
    SampleRuns,
    build_release_metrics,
    build_release_metrics_from_records,
    entries_summary,
    sample_record,
)
from coding_agent_playbook.evals.release_metrics_schema import (
    SCHEMA_VERSION,
    SETUP_PART_TYPES,
    ReleaseMetricsError,
    validate_release_metrics,
)
from coding_agent_playbook.evals.run.harness_runner import SampleResult
from coding_agent_playbook.evals.setup_digest import SetupParts
from coding_agent_playbook.evals.targets import EvalTarget
from coding_agent_playbook.evals.token_usage import TokenPrice, TokenUsage
from coding_agent_playbook.grading.scope import CostTier, Determinism
from coding_agent_playbook.grading.types import CheckResult, EvaluationReport
from tests.evals.release_metrics_files import metrics_file, sample_entry

if TYPE_CHECKING:
    from pathlib import Path

_USAGE = TokenUsage(1000, 500)
_PRICED = EvalTarget(
    "coder", "opencode", "my-org/coder-32b", price=TokenPrice(1.0, 2.0), label="Coder"
)


def _check(
    check_id: str, score: float | None, *, children: tuple[CheckResult, ...] = ()
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        passed=bool(score),
        score=score,
        weight=1.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        subresults=children,
    )


def _result(
    score: float,
    *,
    passed: bool,
    usage: TokenUsage | None = _USAGE,
    reported: str | None = "my-org/coder-32b",
) -> SampleResult:
    leaf = _check("file_exists:src/a.py", score)
    gate = _check("gate", score, children=(_check("gate", score, children=(leaf,)),))
    report = EvaluationReport(
        findings=[], warn_count=0, fail_count=0, composite=score, passed=passed, checks=[gate]
    )
    return SampleResult(
        sample_id="s",
        harness="opencode",
        report=report,
        passed=passed,
        aggregate_score=score,
        duration_seconds=10.0,
        transcript="",
        reported_model=reported,
        usage=usage,
    )


def _runs(sample_id: str, *results: SampleResult) -> SampleRuns:
    return SampleRuns(sample_id, "review", GRADED_HEAD, "p" * 64, "s" * 64, results=list(results))


def _build(target: EvalTarget, *samples: SampleRuns) -> dict[str, object]:
    recorded = RecordedTarget(target, harness_version="1.2.3", judge_model=None, runs=2)
    return build_release_metrics(
        release="9.9.9", commit="abc123", recorded=recorded, samples=samples
    )


def _sample_entry(metrics: dict[str, object], sample_id: str) -> dict[str, object]:
    samples = metrics["samples"]
    assert isinstance(samples, dict)
    entry: dict[str, object] = samples[sample_id]
    return entry


def test_per_sample_entry_aggregates_the_runs() -> None:
    metrics = _build(
        _PRICED, _runs("review/a", _result(1.0, passed=True), _result(0.5, passed=False))
    )
    entry = _sample_entry(metrics, "review/a")
    assert entry == {
        "prompt_id": "review",
        "graded": "head",
        "prompt_digest": "p" * 64,
        "sample_digest": "s" * 64,
        "passes": 1,
        "runs": 2,
        "mean_score": 0.75,
        "stdev": 0.25,
        "checks": {"file_exists:src/a.py": 0.75, "gate": 0.75},
        "duration_seconds_mean": 10.0,
        "tokens_mean": 1500.0,
        # 1000 input x 1.0 + 500 output x 2.0 per million tokens.
        "cost_usd_mean": 0.002,
    }


def test_file_carries_the_target_block_and_summary_and_validates() -> None:
    metrics = _build(
        _PRICED,
        _runs("review/a", _result(1.0, passed=True), _result(1.0, passed=True)),
        _runs("review/b", _result(0.0, passed=False), _result(0.5, passed=False)),
    )
    validate_release_metrics(json.loads(json.dumps(metrics)))
    assert metrics["schema_version"] == SCHEMA_VERSION
    assert (metrics["release"], metrics["previous"], metrics["commit"]) == ("9.9.9", None, "abc123")
    assert metrics["target"] == {
        "name": "coder",
        "harness": "opencode",
        "harness_version": "1.2.3",
        "model": "my-org/coder-32b",
        "reported_model": "my-org/coder-32b",
        "label": "Coder",
        "endpoint": None,
        "price": {"input": 1.0, "output": 2.0},
        "judge_model": None,
        "runs": 2,
    }
    assert metrics["summary"] == {
        "samples": 2,
        "runs": 4,
        "pass_rate": 0.5,
        "mean_score": 0.625,
        "tokens": 6000,
        "cost_usd": 0.008,
    }


def test_endpoint_target_records_the_name_and_fingerprint_never_the_url() -> None:
    endpoint = Endpoint("internal", "anthropic", "https://llm.internal.example", token_env="T")
    target = EvalTarget("internal-claude", "claude_code", "internal-opus", endpoint=endpoint)
    metrics = _build(target, _runs("review/a", _result(1.0, passed=True)))
    validate_release_metrics(json.loads(json.dumps(metrics)))
    block = metrics["target"]
    assert isinstance(block, dict)
    assert block["endpoint"] == {"name": "internal", "fingerprint": endpoint.fingerprint}
    assert "llm.internal.example" not in json.dumps(metrics)


def test_cost_is_null_without_a_price_even_when_tokens_are_known() -> None:
    unpriced = EvalTarget("opus", "claude_code", "claude-opus-5-5")
    metrics = _build(unpriced, _runs("review/a", _result(1.0, passed=True)))
    assert _sample_entry(metrics, "review/a")["cost_usd_mean"] is None
    summary = metrics["summary"]
    assert isinstance(summary, dict)
    assert (summary["cost_usd"], summary["tokens"]) == (None, 1500)


def test_tokens_and_cost_are_null_when_a_run_reported_no_usage() -> None:
    metrics = _build(
        _PRICED, _runs("review/a", _result(1.0, passed=True), _result(1.0, passed=True, usage=None))
    )
    entry = _sample_entry(metrics, "review/a")
    assert (entry["tokens_mean"], entry["cost_usd_mean"]) == (None, None)
    validate_release_metrics(metrics)


def test_reported_model_is_null_when_the_harness_reports_none() -> None:
    metrics = _build(_PRICED, _runs("review/a", _result(1.0, passed=True, reported=None)))
    target = metrics["target"]
    assert isinstance(target, dict)
    assert target["reported_model"] is None


def test_validation_names_every_problem() -> None:
    metrics = _build(_PRICED, _runs("review/a", _result(1.0, passed=True)))
    metrics["schema_version"] = 2
    entry = _sample_entry(metrics, "review/a")
    entry["passes"] = "one"
    del entry["stdev"]
    with pytest.raises(ReleaseMetricsError) as caught:
        validate_release_metrics(metrics)
    message = str(caught.value)
    assert "schema_version: expected 1, got 2" in message
    assert "samples.review/a.passes: expected int, got 'one'" in message
    assert "samples.review/a.stdev: missing" in message


def test_validation_rejects_a_non_object() -> None:
    with pytest.raises(ReleaseMetricsError, match="expected a JSON object"):
        validate_release_metrics([])


def test_controls_hold_the_pinned_runs_and_stay_out_of_the_summary() -> None:
    # Ticket 15: a pinned sample runs on the current text and, as a control, on its edition.
    recorded = RecordedTarget(_PRICED, harness_version="1.2.3", judge_model=None, runs=1)
    head = _runs("review/a", _result(1.0, passed=True))
    control = SampleRuns(
        "review/a", "review", "v9.9.8", "e" * 64, "s" * 64, results=[_result(0.0, passed=False)]
    )
    metrics = build_release_metrics(
        release="9.9.9", commit=None, recorded=recorded, samples=[head], controls=[control]
    )
    validate_release_metrics(json.loads(json.dumps(metrics)))
    controls = metrics["controls"]
    assert isinstance(controls, dict)
    assert (controls["review/a"]["graded"], controls["review/a"]["passes"]) == ("v9.9.8", 0)
    summary = metrics["summary"]
    assert isinstance(summary, dict)
    assert (summary["samples"], summary["runs"], summary["pass_rate"]) == (1, 1, 1.0)


def test_a_file_without_controls_still_validates() -> None:
    metrics = _build(_PRICED, _runs("review/a", _result(1.0, passed=True)))
    del metrics["controls"]  # files recorded before ticket 15
    validate_release_metrics(metrics)


def test_validation_checks_each_control_entry() -> None:
    metrics = _build(_PRICED, _runs("review/a", _result(1.0, passed=True)))
    metrics["controls"] = {"review/a": {"graded": "v9.9.8"}}
    with pytest.raises(ReleaseMetricsError, match=r"controls\.review/a\.passes: missing"):
        validate_release_metrics(metrics)
    metrics["controls"] = []
    with pytest.raises(ReleaseMetricsError, match="controls: expected dict"):
        validate_release_metrics(metrics)


def test_entries_record_the_inputs_digest_of_head_and_control_runs() -> None:
    # #329 ticket 03: each entry records the digest of what its agent received.
    recorded = RecordedTarget(_PRICED, harness_version="1.2.3", judge_model=None, runs=1)
    head = SampleRuns(
        "review/a", "review", GRADED_HEAD, "p" * 64, "s" * 64, [_result(1.0, passed=True)], "h" * 64
    )
    control = SampleRuns(
        "review/a", "review", "v9.9.8", "e" * 64, "s" * 64, [_result(1.0, passed=True)], "c" * 64
    )
    metrics = build_release_metrics(
        release="9.9.9", commit=None, recorded=recorded, samples=[head], controls=[control]
    )
    validate_release_metrics(json.loads(json.dumps(metrics)))
    controls = metrics["controls"]
    assert isinstance(controls, dict)
    assert _sample_entry(metrics, "review/a")["inputs_digest"] == "h" * 64
    assert controls["review/a"]["inputs_digest"] == "c" * 64


def test_an_entry_without_an_inputs_digest_leaves_the_key_out_and_validates() -> None:
    metrics = _build(_PRICED, _runs("review/a", _result(1.0, passed=True)))
    assert "inputs_digest" not in _sample_entry(metrics, "review/a")
    validate_release_metrics(metrics)  # files recorded before #329 ticket 03


def test_validation_rejects_an_inputs_digest_that_is_not_a_string() -> None:
    metrics = _build(_PRICED, _runs("review/a", _result(1.0, passed=True)))
    _sample_entry(metrics, "review/a")["inputs_digest"] = None
    with pytest.raises(
        ReleaseMetricsError, match=r"samples\.review/a\.inputs_digest: expected str"
    ):
        validate_release_metrics(metrics)


def test_hand_written_files_with_and_without_inputs_digests_validate() -> None:
    with_digest = sample_entry(0.9, inputs="i" * 64)
    without = sample_entry(0.9)
    validate_release_metrics(metrics_file("9.9.9", {"review/a": with_digest, "review/b": without}))
    assert with_digest["inputs_digest"] == "i" * 64
    assert "inputs_digest" not in without


def test_an_isolated_record_says_so_in_the_target_block() -> None:
    # #329 ticket 02: a record run's harness and judge ran without personal settings.
    recorded = RecordedTarget(
        _PRICED, harness_version="1.2.3", judge_model=None, runs=1, isolated=True
    )
    metrics = build_release_metrics(release="9.9.9", commit=None, recorded=recorded, samples=[])
    validate_release_metrics(json.loads(json.dumps(metrics)))
    target = metrics["target"]
    assert isinstance(target, dict)
    assert target["isolated"] is True


def test_a_target_block_without_isolation_leaves_the_key_out_and_validates() -> None:
    metrics = _build(_PRICED, _runs("review/a", _result(1.0, passed=True)))
    target = metrics["target"]
    assert isinstance(target, dict)
    assert "isolated" not in target
    validate_release_metrics(metrics)  # files recorded before #329 ticket 02


def test_validation_rejects_an_isolated_key_that_is_not_a_bool() -> None:
    metrics = metrics_file("9.9.9", {"review/a": sample_entry(0.9)})
    metrics["target"]["isolated"] = "yes"
    with pytest.raises(ReleaseMetricsError, match=r"target\.isolated: expected bool"):
        validate_release_metrics(metrics)
    metrics["target"]["isolated"] = False
    validate_release_metrics(metrics)


_SETUP = SetupParts(
    harness="opencode",
    harness_version="1.2.3",
    model="my-org/coder-32b",
    endpoint_fingerprint=None,
    small_model=None,
    runs=1,
    judge_model=None,
    judge_endpoint_fingerprint=None,
    judge_samples=None,
    judge_version=None,
    fail_fast=True,
    isolated=True,
    scoring_digest="d" * 64,
)


def test_a_record_with_setup_parts_writes_the_setup_digest_and_its_parts() -> None:
    # #329 ticket 04: the file names its setup, so a later record can say which part changed.
    recorded = RecordedTarget(
        _PRICED, harness_version="1.2.3", judge_model=None, runs=1, isolated=True, setup=_SETUP
    )
    metrics = build_release_metrics(release="9.9.9", commit=None, recorded=recorded, samples=[])
    validate_release_metrics(json.loads(json.dumps(metrics)))
    assert metrics["setup_digest"] == _SETUP.digest
    assert metrics["setup"] == _SETUP.as_dict()


def test_a_file_without_setup_digest_leaves_the_keys_out_and_validates() -> None:
    metrics = _build(_PRICED, _runs("review/a", _result(1.0, passed=True)))
    assert "setup_digest" not in metrics
    assert "setup" not in metrics
    validate_release_metrics(metrics)  # files recorded before #329 ticket 04
    validate_release_metrics(metrics_file("9.9.9", {"review/a": sample_entry(0.9)}))


def test_validation_types_the_setup_digest_and_each_part() -> None:
    metrics = metrics_file("9.9.9", {"review/a": sample_entry(0.9)})
    metrics["setup_digest"] = None
    metrics["setup"] = _SETUP.as_dict() | {"runs": "one", "fail_fast": 1}
    del metrics["setup"]["harness"]
    with pytest.raises(ReleaseMetricsError) as caught:
        validate_release_metrics(metrics)
    message = str(caught.value)
    assert "setup_digest: expected str, got None" in message
    assert "setup.runs: expected int, got 'one'" in message
    assert "setup.fail_fast: expected bool, got 1" in message
    assert "setup.harness: missing" in message
    metrics["setup"] = "parts"
    with pytest.raises(ReleaseMetricsError, match="setup: expected dict, got 'parts'"):
        validate_release_metrics(metrics)


def test_the_schema_types_every_setup_part() -> None:
    assert set(SETUP_PART_TYPES) == {field.name for field in dataclasses.fields(SetupParts)}


def test_an_unpriced_target_with_no_run_records_an_unknown_cost() -> None:
    # An unpriced target's cost is unknown even when nothing ran (a fully carried record).
    recorded = RecordedTarget(EvalTarget("t", "fake", "m"), None, None, runs=1)
    metrics = build_release_metrics(release="9.9.9", commit=None, recorded=recorded, samples=[])
    assert metrics["summary"]["cost_usd"] is None  # type: ignore[index]
    assert metrics["summary"]["tokens"] == 0  # type: ignore[index]


def _scored(sample_id: str, *scores: float) -> SampleRuns:
    results = [_result(score, passed=score >= 0.5) for score in scores]
    return dataclasses.replace(_runs(sample_id, *results), inputs_digest="i" * 64)


def test_a_fully_carried_record_keeps_the_baseline_mean_score_to_the_last_digit() -> None:
    # Per-sample means 1/6, 5/12 and 0: folding the unrounded means gave 0.194444,
    # folding the recorded (rounded) ones 0.194445, so carrying moved the summary.
    recorded = RecordedTarget(_PRICED, "1.2.3", None, runs=3, setup=_SETUP)
    samples = [_scored("review/a", 0.5, 0, 0), _scored("review/b", 0.5, 0.25, 0.5)]
    samples.append(_scored("review/c", 0, 0, 0))
    baseline = build_release_metrics(
        release="9.9.9", commit=None, recorded=recorded, samples=samples
    )
    entries: Any = baseline["samples"]
    assert baseline["summary"]["mean_score"] == entries_summary(entries)["mean_score"]  # type: ignore[index]
    plan = plan_carry(baseline, setup=_SETUP.as_dict(), inputs=dict.fromkeys(entries, "i" * 64))
    fresh = build_release_metrics(release="9.9.10", commit=None, recorded=recorded, samples=[])
    carried = merge_carried(fresh, plan)
    assert len(plan.carried) == 3
    assert carried["summary"]["mean_score"] == baseline["summary"]["mean_score"]  # type: ignore[index]


def test_records_saved_to_a_checkpoint_fold_into_the_same_file(tmp_path: Path) -> None:
    # A resumed record must write exactly what the uninterrupted run would have.
    samples = tuple(
        dataclasses.replace(runs, inputs_digest="i" * 64)
        for runs in (
            _runs("review/b", _result(0.5, passed=False), _result(1.0, passed=True, reported="x")),
            _runs("review/a", _result(1.0, passed=True), _result(0.0, passed=False, usage=None)),
        )
    )
    recorded = RecordedTarget(_PRICED, harness_version="1.2.3", judge_model=None, runs=2)
    direct = build_release_metrics(
        release="9.9.9", commit="abc123", recorded=recorded, samples=samples
    )
    checkpoint = RecordCheckpoint.open(tmp_path / "c.jsonl", setup_digest="d", resume=False)
    for runs in samples:
        checkpoint.append("sample", sample_record(runs, _PRICED.price))
    reopened = RecordCheckpoint.open(tmp_path / "c.jsonl", setup_digest="d", resume=True)
    records = [
        reopened.resumed("sample", runs.sample_id, inputs_digest="i" * 64, graded=GRADED_HEAD)
        for runs in samples
    ]
    assert all(record is not None for record in records)
    folded = build_release_metrics_from_records(
        release="9.9.9",
        commit="abc123",
        recorded=recorded,
        samples=[record for record in records if record is not None],
    )
    assert folded == direct
