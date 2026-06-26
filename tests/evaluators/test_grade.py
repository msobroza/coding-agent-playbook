"""Tests for grade() - gate + composite aggregation (SPEC prM §C)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.evaluators.grade import grade
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    Measurement,
    MetricConfig,
    RegressionPolicy,
)


def _cc(scope: str, value: float) -> Measurement:
    return Measurement(evaluator="cyclomatic_complexity", scope_key=scope, value=value)


def _cov(scope: str, value: float) -> Measurement:
    # coverage doesn't exist as a builtin in M1; use a higher_is_better builtin? none.
    # Use 'dit' (higher_is_worse) only for deterministic builtins available in M1.
    return Measurement(evaluator="dit", scope_key=scope, value=value)


# --- regression mode ---------------------------------------------------------


def test_regression_detected_on_worsened_scope() -> None:
    baseline = [_cc("a.py::f", 5)]
    candidate = [_cc("a.py::f", 8)]  # worsened by 3 > max_worsening 0
    report = grade(candidate, baseline, MetricConfig(mode="regression"))
    finding = report.findings[0]
    assert finding.level == "fail"
    assert finding.kind == "regression"
    assert finding.baseline == 5
    assert report.passed is False
    assert report.fail_count == 1


def test_regression_pass_when_improved_or_equal() -> None:
    baseline = [_cc("a.py::f", 8)]
    candidate = [_cc("a.py::f", 5)]  # improved
    report = grade(candidate, baseline, MetricConfig(mode="regression"))
    assert report.findings[0].level == "ok"
    assert report.passed is True
    assert report.fail_count == 0


def test_regression_respects_tolerance() -> None:
    baseline = [_cc("a.py::f", 5)]
    candidate = [_cc("a.py::f", 6)]  # worsened by 1
    policy = MetricConfig(
        mode="regression",
        regression={"cyclomatic_complexity": RegressionPolicy(max_worsening=2)},
    )
    report = grade(candidate, baseline, policy)
    assert report.findings[0].level == "ok"  # within tolerance


def test_new_scope_falls_back_to_absolute() -> None:
    baseline: list[Measurement] = []
    candidate = [_cc("a.py::new", 25)]  # > fail(20)
    report = grade(candidate, baseline, MetricConfig(mode="regression"))
    finding = report.findings[0]
    assert finding.kind == "new"
    assert finding.level == "fail"
    assert finding.baseline is None


def test_new_scope_ok_under_warn() -> None:
    candidate = [_cc("a.py::new", 3)]
    report = grade(candidate, [], MetricConfig(mode="regression"))
    finding = report.findings[0]
    assert finding.kind == "new"
    assert finding.level == "ok"


def test_removed_scope_is_ignored() -> None:
    baseline = [_cc("a.py::gone", 30), _cc("a.py::stay", 5)]
    candidate = [_cc("a.py::stay", 5)]
    report = grade(candidate, baseline, MetricConfig(mode="regression"))
    scope_keys = {f.scope_key for f in report.findings}
    assert scope_keys == {"a.py::stay"}


# --- absolute mode -----------------------------------------------------------


def test_absolute_mode_warn_and_fail() -> None:
    candidate = [_cc("a.py::warn", 12), _cc("a.py::fl", 25), _cc("a.py::ok", 3)]
    report = grade(candidate, None, MetricConfig(mode="absolute"))
    levels = {f.scope_key: f.level for f in report.findings}
    assert levels["a.py::warn"] == "warn"
    assert levels["a.py::fl"] == "fail"
    assert levels["a.py::ok"] == "ok"
    assert report.warn_count == 1
    assert report.fail_count == 1


def test_absolute_mode_ignores_baseline() -> None:
    baseline = [_cc("a.py::f", 25)]  # worse baseline
    candidate = [_cc("a.py::f", 3)]  # well under warn
    report = grade(candidate, baseline, MetricConfig(mode="absolute"))
    assert report.findings[0].level == "ok"  # baseline irrelevant in absolute


# --- both mode ---------------------------------------------------------------


def test_both_mode_fails_on_regression_even_if_absolute_ok() -> None:
    baseline = [_cc("a.py::f", 2)]
    candidate = [_cc("a.py::f", 6)]  # under warn(10) but worsened by 4
    report = grade(candidate, baseline, MetricConfig(mode="both"))
    finding = report.findings[0]
    assert finding.level == "fail"
    assert finding.kind == "regression"


def test_both_mode_fails_on_absolute_even_if_no_regression() -> None:
    baseline = [_cc("a.py::f", 25)]
    candidate = [_cc("a.py::f", 25)]  # no change, but over fail
    report = grade(candidate, baseline, MetricConfig(mode="both"))
    finding = report.findings[0]
    assert finding.level == "fail"
    assert finding.kind == "absolute"


# --- strict + gate -----------------------------------------------------------


def test_strict_promotes_warning_to_gate_failure() -> None:
    candidate = [_cc("a.py::f", 12)]  # warn
    lenient = grade(candidate, None, MetricConfig(mode="absolute", strict=False))
    assert lenient.passed is True  # warnings don't fail by default
    strict = grade(candidate, None, MetricConfig(mode="absolute", strict=True))
    assert strict.passed is False


# --- composite ---------------------------------------------------------------


def test_weighted_composite_over_weighted_evaluators() -> None:
    # cc weight 1, dit weight 3 -> weighted mean of their to_score values.
    candidate = [_cc("a.py::f", 10), _cov("a.py::C", 5)]
    policy = MetricConfig(
        mode="absolute",
        weights={"cyclomatic_complexity": 1.0, "dit": 3.0},
    )
    report = grade(candidate, None, policy)
    # cc=10 at warn(10) => score 1.0 ; dit=5 at warn(5), no fail bound => to_score?
    # dit default_absolute is warn=5, fail=None -> no ramp -> score 1.0.
    assert report.composite == pytest.approx(1.0)


def test_composite_none_without_weights() -> None:
    candidate = [_cc("a.py::f", 5)]
    report = grade(candidate, None, MetricConfig(mode="absolute"))
    assert report.composite is None


def test_composite_reflects_partial_scores() -> None:
    candidate = [_cc("a.py::f", 15)]  # midway warn(10)/fail(20) => score 0.5
    policy = MetricConfig(mode="absolute", weights={"cyclomatic_complexity": 1.0})
    report = grade(candidate, None, policy)
    assert report.composite == pytest.approx(0.5)


def test_config_threshold_override_changes_level() -> None:
    candidate = [_cc("a.py::f", 12)]
    policy = MetricConfig(
        mode="absolute",
        thresholds={"cyclomatic_complexity": AbsoluteThreshold(warn=20, fail=40)},
    )
    report = grade(candidate, None, policy)
    assert report.findings[0].level == "ok"  # 12 now under the raised warn
