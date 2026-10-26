"""Building and validating a release metrics file from fake run results (spec #281 ticket 07).

No runner and no CLI: each :class:`SampleResult` is built by hand, so the file's
numbers can be checked exactly.
"""

from __future__ import annotations

import json

import pytest

from coding_agent_playbook.evals.endpoints import Endpoint
from coding_agent_playbook.evals.release_metrics import (
    GRADED_HEAD,
    RecordedTarget,
    SampleRuns,
    build_release_metrics,
)
from coding_agent_playbook.evals.release_metrics_schema import (
    SCHEMA_VERSION,
    ReleaseMetricsError,
    validate_release_metrics,
)
from coding_agent_playbook.evals.run.harness_runner import SampleResult
from coding_agent_playbook.evals.targets import EvalTarget
from coding_agent_playbook.evals.token_usage import TokenPrice, TokenUsage
from coding_agent_playbook.grading.scope import CostTier, Determinism
from coding_agent_playbook.grading.types import CheckResult, EvaluationReport

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
