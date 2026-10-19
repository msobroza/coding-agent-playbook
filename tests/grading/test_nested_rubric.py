"""Tests for ``Rubric``-as-``Metric`` composition (T4a) - ``grading/rubric.py``.

A :class:`~coding_agent_playbook.grading.rubric.Rubric` is *also* a
:class:`~coding_agent_playbook.grading.metric.Metric`: its :meth:`measure`
self-builds a :class:`~coding_agent_playbook.grading.check.MeasurementSet`
from ``ctx`` (the additive ``candidate_measurements``/``baseline_measurements``
fields), runs :meth:`evaluate`, and surfaces the composite as one MODULE-scope
:class:`~coding_agent_playbook.grading.types.Measurement` keyed on the
rubric's ``name``. That single measurement can then be graded by a
:class:`~coding_agent_playbook.grading.check.ThresholdCheck` in a *parent*
rubric - rubrics nest.

These assert the child's ``measure`` shape, the parent's higher-is-better gate
(strict-below: a child composite ``< 0.8`` fails, ``>= 0.8`` passes), and that a
self-referential rubric (a rubric measuring itself) raises ``ValueError`` rather
than recursing forever.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.grading.check import Check, MeasurementSet, ThresholdCheck
from coding_agent_playbook.grading.metric import Metric
from coding_agent_playbook.grading.normalizer import Identity, PercentNormalizer, RampNormalizer
from coding_agent_playbook.grading.rubric import Rubric
from coding_agent_playbook.grading.scope import CostTier, Determinism, Scope
from coding_agent_playbook.grading.types import CheckResult, EvalContext, Measurement


class _CC(Metric):
    name = "cyclomatic_complexity"
    scope = Scope.FUNCTION
    normalizer = RampNormalizer(good=5, bad=20)
    requires = None

    def available(self, ctx: EvalContext) -> bool:
        return True

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return []


class _Cov(Metric):
    name = "coverage"
    scope = Scope.FILE
    normalizer = PercentNormalizer()
    requires = None

    def available(self, ctx: EvalContext) -> bool:
        # Forced True so the child Rubric's ThresholdCheck runs on a bare ctx
        # (no module/project) - these tests exercise nesting, not ctx-slot gating.
        return self.needs_project is False or ctx.project is not None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return []


def _ctx(
    candidate: list[Measurement] | None = None,
    baseline: list[Measurement] | None = None,
) -> EvalContext:
    return EvalContext(
        module=None,
        source="",
        label="nested",
        candidate_measurements=candidate,
        baseline_measurements=baseline,
    )


def _cov(scope: str, value: float) -> Measurement:
    return Measurement(evaluator="coverage", scope_key=scope, value=value)


def _cc(scope: str, value: float) -> Measurement:
    return Measurement(evaluator="cyclomatic_complexity", scope_key=scope, value=value)


def test_rubric_is_a_metric() -> None:
    child = Rubric(
        [ThresholdCheck(_Cov(), warn=0.8, fail=0.4, weight=1.0, required=False)],
        name="child",
    )
    assert child.scope is Scope.MODULE
    # A rubric's composite is already a 0-1 goodness ⇒ Identity normalizer.
    assert isinstance(child.normalizer, Identity)
    assert child.score(0.5) == 0.5
    assert child.requires is None
    assert child.name == "child"
    # No execution check ⇒ the rubric metric does not need a project.
    assert child.needs_project is False


def test_needs_project_when_a_child_check_is_execution_tier() -> None:
    # A TestsPassCheck-equivalent execution-tier check flips needs_project on.
    class _ExecCheck(ThresholdCheck):
        pass

    exec_metric = _Cov()
    exec_metric.needs_project = True
    rubric = Rubric([_ExecCheck(exec_metric, warn=0.8)])
    assert any(c.cost == CostTier.EXECUTION for c in rubric.checks)
    assert rubric.needs_project is True


def test_child_measure_returns_one_composite_measurement() -> None:
    child = Rubric(
        [ThresholdCheck(_Cov(), warn=0.8, fail=0.4, weight=1.0, required=False)],
        name="child",
    )
    # coverage=60 -> PercentNormalizer score 0.6; that is the child composite.
    ctx = _ctx(candidate=[_cov("a.py", 60.0)])
    out = child.measure(ctx)
    assert len(out) == 1
    (m,) = out
    assert m.evaluator == "child"
    assert m.scope_key == "child"
    assert m.value == 0.6


def test_parent_gate_fails_when_child_composite_below_bound() -> None:
    child = Rubric(
        [ThresholdCheck(_Cov(), warn=0.8, fail=0.4, weight=1.0, required=False)],
        name="child",
    )
    # Child composite = 0.6 (< 0.8).
    child_measurement = child.measure(_ctx(candidate=[_cov("a.py", 60.0)]))
    ms = MeasurementSet(child_measurement, None)

    # Parent grades the child composite (Identity-normalized) with fail=0.8.
    parent = Rubric([ThresholdCheck(child, fail=0.8, required=True)])
    report = parent.evaluate(_ctx(), ms)
    assert report.passed is False
    assert report.fail_count == 1


def test_parent_gate_passes_when_child_composite_at_or_above_bound() -> None:
    child = Rubric(
        [ThresholdCheck(_Cov(), warn=0.8, fail=0.4, weight=1.0, required=False)],
        name="child",
    )
    # coverage=100 -> score 1.0 (>= 0.8).
    child_measurement = child.measure(_ctx(candidate=[_cov("a.py", 100.0)]))
    ms = MeasurementSet(child_measurement, None)

    parent = Rubric([ThresholdCheck(child, fail=0.8, required=True)])
    report = parent.evaluate(_ctx(), ms)
    assert report.passed is True
    assert report.fail_count == 0


def test_measure_uses_baseline_measurements_from_ctx() -> None:
    # A non-regression-style child reads ctx.baseline_measurements too.
    child = Rubric(
        [ThresholdCheck(_Cov(), warn=0.8, fail=0.4, weight=1.0, required=False)],
        name="child",
    )
    ctx = _ctx(candidate=[_cov("a.py", 100.0)], baseline=[_cov("a.py", 50.0)])
    (m,) = child.measure(ctx)
    # ThresholdCheck is absolute ⇒ baseline is ignored, score is 1.0.
    assert m.value == 1.0


def test_self_referential_rubric_raises() -> None:
    # A pathological check that re-enters the *same* rubric's measure() during
    # grade - the cycle the guard exists to catch. (No deterministic check does
    # this; ThresholdCheck reads the MeasurementSet, it never calls measure.)
    rubric = Rubric([], name="self")

    class _ReentrantCheck(Check):
        cost = CostTier.DETERMINISTIC
        determinism = Determinism.DETERMINISTIC

        def __init__(self) -> None:
            self.id = "reentrant"
            self.weight = 0.0
            self.required = False

        def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
            # Re-measure the enclosing rubric mid-grade ⇒ re-entrancy.
            rubric.measure(ctx)
            raise AssertionError("unreachable: measure() should have raised")

    rubric.checks.append(_ReentrantCheck())
    with pytest.raises(ValueError, match="re-entrant"):
        rubric.measure(_ctx(candidate=[]))


def test_measure_memoizes_per_ctx() -> None:
    calls: list[int] = []

    class _Counting(Metric):
        name = "counting"
        scope = Scope.MODULE
        normalizer = Identity()
        requires = None

        def measure(self, ctx: EvalContext) -> list[Measurement]:
            calls.append(1)
            return []

    # A child whose only check carries no weight ⇒ composite None ⇒ value falls
    # back to float(passed). The point is that two measure() calls on the SAME
    # ctx do not rebuild the report twice.
    child = Rubric([ThresholdCheck(_Counting(), warn=1.0, required=False)], name="memo")
    ctx = _ctx(candidate=[])
    first = child.measure(ctx)
    second = child.measure(ctx)
    assert first == second
    assert first is second  # memoized object identity per ctx
