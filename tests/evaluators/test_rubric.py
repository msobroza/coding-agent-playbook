"""Tests for the ``Rubric`` aggregator (T4a) - ``evaluators/rubric.py``.

:class:`Rubric` is the "aggregate" layer of the Metric->Check->Rubric split: it
evaluates its checks **sequentially in authored order** (the concurrent
short-circuit scheduler is a later track, T4b), folds their
:class:`~coding_agent_playbook.evaluators.types.CheckResult` rows into one
:class:`~coding_agent_playbook.evaluators.types.EvaluationReport`, and applies the
gate / weighted composite / strict-mode rules. These exercise:

* the gate (all required pass -> True; one required fail -> False; a *skipped*
  judged check when ``ctx.judge is None`` does **not** sink the gate),
* the composite as the weighted mean of the run checks' scores (a golden value),
* ``strict`` promoting a warn-bearing required check to a gate failure,
* a ``None`` composite when no run check carries weight, and
* ``findings`` flattening the leaf :class:`ScopeDetail` rows.
"""

from __future__ import annotations

from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.evaluators.check import (
    Check,
    MeasurementSet,
    ThresholdCheck,
)
from coding_agent_playbook.evaluators.checks.judged import JudgeCheck
from coding_agent_playbook.evaluators.metric import Metric
from coding_agent_playbook.evaluators.rubric import Rubric
from coding_agent_playbook.evaluators.scope import CostTier, Determinism, Scope
from coding_agent_playbook.evaluators.types import (
    CheckResult,
    EvalContext,
    Measurement,
    ScopeDetail,
)


class _CC(Metric):
    """A higher-is-worse (CC-like) metric: thresholds live on the Check.

    ``available`` is forced ``True`` so the Rubric never skips this check on a
    bare ``ctx`` (no ``module``); these tests exercise the *aggregation* logic,
    not the metric's ctx-slot gating (covered in ``test_metric.py``).
    """

    name = "cyclomatic_complexity"
    scope = Scope.FUNCTION
    higher_is_worse = True
    requires = None

    def available(self, ctx: EvalContext) -> bool:
        return True

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return []


class _Cov(Metric):
    """A higher-is-better (coverage-like) metric (always available, see ``_CC``)."""

    name = "coverage"
    scope = Scope.FILE
    higher_is_worse = False
    requires = None

    def available(self, ctx: EvalContext) -> bool:
        return True

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return []


def _ctx(judge: StubJudge | None = None, *, samples: int = 1) -> EvalContext:
    return EvalContext(
        module=None,
        source="",
        label="rubric",
        judge=judge,
        artifact="ART",
        samples=samples,
    )


def _cc(scope: str, value: float) -> Measurement:
    return Measurement(evaluator="cyclomatic_complexity", scope_key=scope, value=value)


def _cov(scope: str, value: float) -> Measurement:
    return Measurement(evaluator="coverage", scope_key=scope, value=value)


def test_gate_passes_when_all_required_run_checks_pass() -> None:
    # CC under fail=20 ⇒ ok; coverage at/above 80 (strict-below) ⇒ ok.
    rubric = Rubric(
        [
            ThresholdCheck(_CC(), fail=20.0, required=True),
            ThresholdCheck(_Cov(), warn=80.0, required=True),
        ]
    )
    ms = MeasurementSet([_cc("f", 5.0), _cov("a.py", 95.0)], None)
    report = rubric.evaluate(_ctx(), ms)
    assert report.passed is True
    assert report.fail_count == 0


def test_gate_fails_when_a_required_check_fails() -> None:
    rubric = Rubric(
        [
            ThresholdCheck(_CC(), fail=20.0, required=True),  # 25 ⇒ fail
            ThresholdCheck(_Cov(), warn=80.0, required=True),
        ]
    )
    ms = MeasurementSet([_cc("f", 25.0), _cov("a.py", 95.0)], None)
    report = rubric.evaluate(_ctx(), ms)
    assert report.passed is False
    assert report.fail_count == 1


def test_skipped_judged_check_does_not_fail_the_gate() -> None:
    # No judge ⇒ the JudgeCheck is unavailable and recorded skipped, not failed.
    rubric = Rubric(
        [
            ThresholdCheck(_CC(), fail=20.0, required=True),
            JudgeCheck("well documented", required=True),
        ]
    )
    ms = MeasurementSet([_cc("f", 5.0)], None)
    report = rubric.evaluate(_ctx(judge=None), ms)

    assert report.passed is True
    # The judged check is present but skipped.
    judged = next(c for c in report.checks if c.check_id == "judge:well-documented")
    assert judged.status == "skipped"
    assert judged.passed is False
    assert judged.score is None


def test_available_judged_check_runs_and_can_fail_the_gate() -> None:
    judge = StubJudge({"well documented": 0.1})
    rubric = Rubric([JudgeCheck("well documented", threshold=0.5, required=True)])
    report = rubric.evaluate(_ctx(judge=judge), MeasurementSet([], None))

    judged = report.checks[0]
    assert judged.status == "run"
    assert judged.passed is False
    assert report.passed is False


def test_composite_is_the_weighted_mean_of_scores() -> None:
    # CC=5 under warn=10/fail=20 ramps to 1.0; coverage=60 under warn=80/fail=40
    # ramps to (60-40)/(80-40) = 0.5. Weighted mean: (1*1.0 + 3*0.5)/4 = 0.625.
    rubric = Rubric(
        [
            ThresholdCheck(_CC(), warn=10.0, fail=20.0, weight=1.0, required=False),
            ThresholdCheck(_Cov(), warn=80.0, fail=40.0, weight=3.0, required=False),
        ]
    )
    ms = MeasurementSet([_cc("f", 5.0), _cov("a.py", 60.0)], None)
    report = rubric.evaluate(_ctx(), ms)
    assert report.composite == 0.625


def test_composite_none_with_no_weighted_checks() -> None:
    rubric = Rubric(
        [
            ThresholdCheck(_CC(), fail=20.0, required=True),  # weight 0
            ThresholdCheck(_Cov(), warn=80.0, required=True),  # weight 0
        ]
    )
    ms = MeasurementSet([_cc("f", 5.0), _cov("a.py", 95.0)], None)
    report = rubric.evaluate(_ctx(), ms)
    assert report.composite is None


def test_strict_promotes_a_warn_bearing_required_check_to_failure() -> None:
    # coverage=70 under warn=80 (no fail) ⇒ warn level, check.passed True.
    rubric = Rubric([ThresholdCheck(_Cov(), warn=80.0, required=True)])
    ms = MeasurementSet([_cov("a.py", 70.0)], None)

    lenient = rubric.evaluate(_ctx(), ms, strict=False)
    assert lenient.passed is True
    assert lenient.warn_count == 1

    strict = rubric.evaluate(_ctx(), ms, strict=True)
    assert strict.passed is False
    assert strict.warn_count == 1


def test_findings_flatten_leaf_scope_details() -> None:
    rubric = Rubric(
        [
            ThresholdCheck(_CC(), fail=20.0, required=True),
            ThresholdCheck(_Cov(), warn=80.0, required=True),
        ]
    )
    ms = MeasurementSet([_cc("f", 5.0), _cov("a.py", 95.0)], None)
    report = rubric.evaluate(_ctx(), ms)

    assert all(isinstance(f, ScopeDetail) for f in report.findings)
    keys = {(f.evaluator, f.scope_key) for f in report.findings}
    assert keys == {("cyclomatic_complexity", "f"), ("coverage", "a.py")}


def test_warn_and_fail_counts_aggregate_across_run_checks() -> None:
    rubric = Rubric(
        [
            ThresholdCheck(_CC(), warn=10.0, fail=20.0, required=False),  # 25 ⇒ fail
            ThresholdCheck(_Cov(), warn=80.0, required=False),  # 70 ⇒ warn
        ]
    )
    ms = MeasurementSet([_cc("f", 25.0), _cov("a.py", 70.0)], None)
    report = rubric.evaluate(_ctx(), ms)
    assert report.fail_count == 1
    assert report.warn_count == 1


def test_checks_run_in_authored_order() -> None:
    order: list[str] = []

    class _Recorder(Check):
        cost = CostTier.DETERMINISTIC
        determinism = Determinism.DETERMINISTIC

        def __init__(self, tag: str) -> None:
            self.id = tag
            self.weight = 0.0
            self.required = False
            self._tag = tag

        def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
            order.append(self._tag)
            return CheckResult(
                check_id=self.id,
                passed=True,
                score=None,
                weight=self.weight,
                required=self.required,
                determinism=self.determinism,
                cost=self.cost,
                status="run",
                subresults=(),
            )

    rubric = Rubric([_Recorder("first"), _Recorder("second"), _Recorder("third")])
    rubric.evaluate(_ctx(), MeasurementSet([], None))
    assert order == ["first", "second", "third"]


# --------------------------------------------------------------------------- #
# of() / define() / CRITERIA — the code-defined-rubric constructors
# --------------------------------------------------------------------------- #


def test_of_builds_judge_checks_with_normalized_weights() -> None:
    rubric = Rubric.of(
        ("Findings prioritized correctly", 1.0),
        ("Each finding proposes a concrete fix", 3.0),
        name="review",
    )
    assert isinstance(rubric, Rubric)
    assert rubric.name == "review"
    assert all(isinstance(c, JudgeCheck) for c in rubric.checks)
    criteria = [c.criterion for c in rubric.checks]  # type: ignore[attr-defined]
    assert criteria == [
        "Findings prioritized correctly",
        "Each finding proposes a concrete fix",
    ]
    # 1:3 ⇒ normalized to 0.25 / 0.75 (sum 1.0).
    weights = [c.weight for c in rubric.checks]
    assert weights == [0.25, 0.75]
    assert sum(weights) == 1.0
    # JudgeChecks built by of() are non-gating (feed the composite, don't gate).
    assert all(c.required is False for c in rubric.checks)


def test_of_threshold_is_threaded_to_each_check() -> None:
    rubric = Rubric.of(("a", 1.0), ("b", 1.0), threshold=0.8)
    assert [c.threshold for c in rubric.checks] == [0.8, 0.8]  # type: ignore[attr-defined]


def test_of_normalize_false_keeps_raw_weights() -> None:
    rubric = Rubric.of(("a", 1.0), ("b", 3.0), normalize=False)
    assert [c.weight for c in rubric.checks] == [1.0, 3.0]


def test_of_empty_is_an_empty_rubric() -> None:
    rubric = Rubric.of(name="empty")
    assert rubric.checks == []
    assert rubric.name == "empty"


def test_of_all_zero_weights_are_left_untouched() -> None:
    # The all-zero guard must not divide by zero — weights stay 0.0.
    rubric = Rubric.of(("a", 0.0), ("b", 0.0))
    assert [c.weight for c in rubric.checks] == [0.0, 0.0]


class _DemoRubric(Rubric):
    CRITERIA = (
        ("Tests use parametrize", 1.0),
        ("No mocking on pure functions", 1.0),
    )


def test_define_uses_class_criteria_and_class_name() -> None:
    rubric = _DemoRubric.define()
    assert isinstance(rubric, _DemoRubric)
    assert rubric.name == "_DemoRubric"
    assert [c.criterion for c in rubric.checks] == [  # type: ignore[attr-defined]
        "Tests use parametrize",
        "No mocking on pure functions",
    ]
    # Two equal weights ⇒ normalized to 0.5 / 0.5.
    assert [c.weight for c in rubric.checks] == [0.5, 0.5]


def test_define_forwards_threshold_kwarg() -> None:
    rubric = _DemoRubric.define(threshold=0.9)
    assert [c.threshold for c in rubric.checks] == [0.9, 0.9]  # type: ignore[attr-defined]
