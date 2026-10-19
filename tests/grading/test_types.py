"""Tests for the evaluator dataclasses + policy types (SPEC prM §E)."""

from __future__ import annotations

import dataclasses

from coding_agent_playbook.grading.parse import parse_module
from coding_agent_playbook.grading.scope import CostTier, Determinism
from coding_agent_playbook.grading.types import (
    AbsoluteThreshold,
    CheckResult,
    EvalContext,
    EvaluationReport,
    Measurement,
    RegressionPolicy,
    ResolvedPolicy,
    ScopeDetail,
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


def test_scope_detail_fields() -> None:
    f = ScopeDetail(
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
    assert _is_frozen(ScopeDetail)


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


def test_cost_tier_ordering() -> None:
    # T1: cheapest-first ordering so the scheduler can sort.
    assert CostTier.DETERMINISTIC < CostTier.EXECUTION < CostTier.JUDGED
    assert sorted(CostTier) == [
        CostTier.DETERMINISTIC,
        CostTier.EXECUTION,
        CostTier.JUDGED,
    ]


def test_scope_detail_construction() -> None:
    detail = ScopeDetail(
        evaluator="cc",
        scope_key="f.py::g",
        value=12.0,
        baseline=10.0,
        bound=10.0,
        score=0.5,
        level="warn",
        kind="absolute",
    )
    assert detail.level == "warn"
    assert detail.kind == "absolute"
    assert _is_frozen(ScopeDetail)


def test_check_result_defaults() -> None:
    cr = CheckResult(
        check_id="expected::file_exists",
        passed=True,
        score=1.0,
        weight=1.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
    )
    assert cr.status == "run"
    assert cr.subresults == ()
    assert cr.detail == ""
    assert cr.score == 1.0


def test_check_result_recursive_subresults() -> None:
    leaf_detail = ScopeDetail(
        evaluator="cc",
        scope_key="f.py::g",
        value=12.0,
        baseline=None,
        bound=10.0,
        score=0.0,
        level="fail",
        kind="absolute",
    )
    child = CheckResult(
        check_id="child",
        passed=True,
        score=1.0,
        weight=0.5,
        required=False,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
    )
    parent = CheckResult(
        check_id="rubric::root",
        passed=False,
        score=None,
        weight=1.0,
        required=True,
        determinism=Determinism.JUDGED,
        cost=CostTier.JUDGED,
        status="run",
        subresults=(child, leaf_detail),
        detail="composite of one child check + one scope detail",
    )
    assert parent.subresults == (child, leaf_detail)
    assert isinstance(parent.subresults[0], CheckResult)
    assert isinstance(parent.subresults[1], ScopeDetail)
    assert parent.score is None


def test_check_result_skipped_status() -> None:
    cr = CheckResult(
        check_id="judged::clarity",
        passed=False,
        score=None,
        weight=1.0,
        required=False,
        determinism=Determinism.JUDGED,
        cost=CostTier.JUDGED,
        status="skipped",
        detail="no judge configured",
    )
    assert cr.status == "skipped"


def test_evaluation_report_accepts_checks() -> None:
    # Additive: findings stays, checks is a new defaulted field.
    empty = EvaluationReport(
        findings=[],
        warn_count=0,
        fail_count=0,
        composite=None,
        passed=True,
    )
    assert empty.checks == []
    cr = CheckResult(
        check_id="c",
        passed=True,
        score=1.0,
        weight=1.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
    )
    report = EvaluationReport(
        findings=[],
        warn_count=0,
        fail_count=0,
        composite=1.0,
        passed=True,
        checks=[cr],
    )
    assert report.checks == [cr]


def _is_frozen(cls: type) -> bool:
    params = getattr(cls, "__dataclass_params__", None)
    return bool(params and params.frozen)
