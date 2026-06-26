"""Tests for the evaluator dataclasses + policy types (SPEC prM §E)."""

from __future__ import annotations

import dataclasses

from coding_agent_playbook.evaluators.parse import parse_module
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    EvalContext,
    EvaluationReport,
    Finding,
    GradePolicy,
    Measurement,
    MetricConfig,
    RegressionPolicy,
    ResolvedPolicy,
)


def test_absolute_threshold_defaults_none_and_frozen() -> None:
    t = AbsoluteThreshold()
    assert t.warn is None and t.fail is None
    t2 = AbsoluteThreshold(warn=10, fail=20)
    assert (t2.warn, t2.fail) == (10, 20)
    assert dataclasses.is_dataclass(t) and _is_frozen(AbsoluteThreshold)


def test_regression_policy_default_zero() -> None:
    assert RegressionPolicy().max_worsening == 0.0
    assert _is_frozen(RegressionPolicy)


def test_measurement_fields_frozen() -> None:
    m = Measurement(evaluator="cyclomatic_complexity", scope_key="f.py::g", value=12.0)
    assert (m.evaluator, m.scope_key, m.value) == ("cyclomatic_complexity", "f.py::g", 12.0)
    assert _is_frozen(Measurement)


def test_finding_fields() -> None:
    f = Finding(
        evaluator="cc",
        scope_key="f.py::g",
        value=12.0,
        baseline=10.0,
        bound=10.0,
        score=0.5,
        level="warn",
        kind="absolute",
    )
    assert f.level == "warn"
    assert f.kind == "absolute"
    assert _is_frozen(Finding)


def test_evaluation_report_defaults_and_mutable() -> None:
    report = EvaluationReport(
        findings=[],
        warn_count=0,
        fail_count=0,
        composite=None,
        passed=True,
    )
    assert report.passed is True
    # EvaluationReport is mutable (not frozen) per §E.
    report.passed = False
    assert report.passed is False


def test_metric_config_defaults() -> None:
    cfg = MetricConfig()
    assert cfg.mode == "regression"
    assert cfg.fail_on_breach is True
    assert cfg.strict is False
    assert cfg.thresholds == {}
    assert cfg.regression == {}
    assert cfg.weights == {}


def test_metric_config_satisfies_grade_policy_protocol() -> None:
    cfg = MetricConfig()
    policy: GradePolicy = cfg  # structural check at type+runtime level
    assert policy.mode == "regression"


def test_resolved_policy_carries_effective_values() -> None:
    rp = ResolvedPolicy(
        absolute=AbsoluteThreshold(warn=10, fail=20),
        regression=RegressionPolicy(max_worsening=0.0),
        weight=1.0,
    )
    assert rp.weight == 1.0
    assert rp.absolute.fail == 20


def test_eval_context_static_fields_and_reserved() -> None:
    model = parse_module("def f():\n    return 1\n", "f.py")
    ctx = EvalContext(module=model, source="def f():\n    return 1\n", label="f.py")
    assert ctx.label == "f.py"
    # Reserved-for-later fields default to None/defaults.
    assert ctx.project is None
    assert ctx.judge is None
    assert ctx.artifact is None
    assert ctx.samples == 1


def _is_frozen(cls: type) -> bool:
    params = getattr(cls, "__dataclass_params__", None)
    return bool(params and params.frozen)
