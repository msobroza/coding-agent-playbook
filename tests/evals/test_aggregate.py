"""Tests for the across-trial aggregate layer (Track C8).

The ``[aggregate]`` layer adds reliability-across-``k``-trials on top of the
per-trial gate/rubric/verdict model: ``pass@k`` (probability a random ``k``-subset
contains ≥1 success) and ``pass^k`` (probability a random ``k``-subset is all
successes), reduced over a chosen ``over`` axis (``gate`` / ``rubric`` /
``verdict``) and graded against an absolute ``warn``/``fail`` floor.

These cover the two estimators on hand-verified ``(n, c, k)`` triples, the
:class:`~coding_agent_playbook.evaluators.checks.aggregate.AggregateCheck` grade
over synthetic trials (the ``over`` selector + threshold → pass/fail), and the
handle/compile wiring (the ``metric``-alone aggregate handle, ``trials_needed`` =
``max(k)``, and the no-aggregate degeneracy ⇒ ``None``/``1``).
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.evals._compile import compile_task
from coding_agent_playbook.evals._handles import build_handles
from coding_agent_playbook.evaluators.check import MeasurementSet
from coding_agent_playbook.evaluators.checks.aggregate import (
    AggregateCheck,
    PassAtK,
    PassPowK,
)
from coding_agent_playbook.evaluators.checks.compose import AllOf
from coding_agent_playbook.evaluators.checks.registry import get_check
from coding_agent_playbook.evaluators.scope import CostTier, Determinism
from coding_agent_playbook.evaluators.types import (
    CheckResult,
    EvalContext,
    EvaluationReport,
    ScopeDetail,
    TrialResult,
)

# --------------------------------------------------------------------------- #
# Synthetic trial builders
# --------------------------------------------------------------------------- #


def _layer_result(check_id: str, *, passed: bool) -> CheckResult:
    """A minimal layer :class:`CheckResult` row (``gate``/``rubric``)."""
    return CheckResult(
        check_id=check_id,
        passed=passed,
        score=1.0 if passed else 0.0,
        weight=0.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        status="run",
    )


def _trial(
    *,
    verdict: bool,
    gate: bool | None = None,
    rubric: bool | None = None,
) -> TrialResult:
    """A :class:`TrialResult` with a crafted verdict + optional gate/rubric layers."""
    checks: list[CheckResult] = []
    if gate is not None:
        checks.append(_layer_result("gate", passed=gate))
    if rubric is not None:
        checks.append(_layer_result("rubric", passed=rubric))
    report = EvaluationReport(
        findings=[],
        warn_count=0,
        fail_count=0,
        composite=None,
        passed=verdict,
        checks=checks,
    )
    return TrialResult(report=report, verdict=verdict)


def _rubric_skipped_trial(*, verdict: bool) -> TrialResult:
    """A trial whose rubric layer never ran (e.g. no judge configured)."""
    skipped = CheckResult(
        check_id="rubric",
        passed=False,
        score=None,
        weight=0.0,
        required=True,
        determinism=Determinism.JUDGED,
        cost=CostTier.JUDGED,
        status="skipped",
    )
    report = EvaluationReport(
        findings=[], warn_count=0, fail_count=0, composite=None, passed=verdict, checks=[skipped]
    )
    return TrialResult(report=report, verdict=verdict)


def _ctx(trials: list[TrialResult]) -> EvalContext:
    return EvalContext(module=None, source="", label="agg", trials=trials)


_EMPTY = MeasurementSet([], None)


# --------------------------------------------------------------------------- #
# Estimator correctness — hand-verified (n, c, k)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("n", "c", "k", "expected"),
    [
        (5, 3, 1, 0.6),  # pass@1 = c/n = 3/5
        (5, 2, 5, 1.0),  # 1 - C(3,5)/C(5,5) = 1 - 0/1 = 1.0  (C(3,5)=0)
        (5, 0, 1, 0.0),  # no successes => 0
        (5, 5, 1, 1.0),  # all successes => 1
        (4, 2, 2, 1 - 1 / 6),  # 1 - C(2,2)/C(4,2) = 1 - 1/6
        (3, 1, 2, 1 - 1 / 3),  # (n-c)=2 not < k=2 -> 1 - C(2,2)/C(3,2) = 1 - 1/3
    ],
)
def test_pass_at_k_estimator(n: int, c: int, k: int, expected: float) -> None:
    check = PassAtK(k=k, over="verdict")
    assert check._estimate(n=n, c=c, k=k) == pytest.approx(expected)


def test_pass_at_k_n_minus_c_below_k_is_one() -> None:
    # n=5, c=2, k=5 => (n-c)=3 < 5 => every 5-subset must contain a success => 1.0
    assert PassAtK(k=5, over="verdict")._estimate(n=5, c=2, k=5) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("n", "c", "k", "expected"),
    [
        (3, 2, 1, 2 / 3),  # pass^1 = c/n = 2/3
        (3, 3, 2, 1.0),  # C(3,2)/C(3,2) = 3/3 = 1
        (3, 1, 2, 0.0),  # c=1 < k=2 => 0
        (5, 5, 5, 1.0),  # all success, whole-set subset => 1
        (4, 2, 2, 1 / 6),  # C(2,2)/C(4,2) = 1/6
        (5, 0, 1, 0.0),  # no successes => 0
    ],
)
def test_pass_pow_k_estimator(n: int, c: int, k: int, expected: float) -> None:
    check = PassPowK(k=k, over="verdict")
    assert check._estimate(n=n, c=c, k=k) == pytest.approx(expected)


def test_estimators_n_zero_is_zero() -> None:
    assert PassAtK(k=1, over="verdict")._estimate(n=0, c=0, k=1) == 0.0
    assert PassPowK(k=1, over="verdict")._estimate(n=0, c=0, k=1) == 0.0


# --------------------------------------------------------------------------- #
# AggregateCheck.grade over synthetic trials
# --------------------------------------------------------------------------- #


def test_grade_pass_at_k_over_verdict_passes_above_fail() -> None:
    # 4 of 5 verdicts pass => pass@5 over verdict: (n-c)=1 < 5 => 1.0 >= fail 0.9.
    trials = [_trial(verdict=v) for v in (True, True, True, True, False)]
    check = PassAtK(k=5, over="verdict", fail=0.9)
    result = check.grade(_ctx(trials), _EMPTY)
    assert result.score == pytest.approx(1.0)
    assert result.passed is True
    assert result.check_id == "pass_at_k:verdict@5"


def test_grade_pass_pow_k_over_verdict_fails_below_fail() -> None:
    # 3 of 5 verdicts pass => pass^3 over verdict: C(3,3)/C(5,3) = 1/10 = 0.1 < 0.5.
    trials = [_trial(verdict=v) for v in (True, True, True, False, False)]
    check = PassPowK(k=3, over="verdict", fail=0.5)
    result = check.grade(_ctx(trials), _EMPTY)
    assert result.score == pytest.approx(0.1)
    assert result.passed is False


def test_grade_over_gate_reads_gate_layer() -> None:
    # verdicts all False but the gate layer passes 5/5 => pass@1 over gate = 1.0.
    trials = [_trial(verdict=False, gate=True) for _ in range(5)]
    check = PassAtK(k=1, over="gate", fail=0.9)
    result = check.grade(_ctx(trials), _EMPTY)
    assert result.score == pytest.approx(1.0)
    assert result.passed is True


def test_aggregate_over_a_layer_that_never_ran_is_unavailable() -> None:
    """Every trial skipped the rubric layer ⇒ there is nothing to aggregate.

    A skipped layer is neutral, so the aggregate must skip rather than count each
    skipped trial as a failure (``pass@k = 0``) — or as a success.
    """
    trials = [_rubric_skipped_trial(verdict=True) for _ in range(3)]
    check = PassAtK(k=1, over="rubric", fail=0.5)
    assert check.available(_ctx(trials)) is False


def test_aggregate_counts_only_trials_where_the_layer_ran() -> None:
    # 1 of the 2 trials whose rubric ran passed; the skipped trial does not vote.
    trials = [
        _trial(verdict=True, rubric=True),
        _trial(verdict=False, rubric=False),
        _rubric_skipped_trial(verdict=True),
    ]
    check = PassAtK(k=1, over="rubric", fail=0.5)
    assert check.available(_ctx(trials)) is True
    result = check.grade(_ctx(trials), _EMPTY)
    assert result.score == pytest.approx(0.5)


def test_aggregate_with_fewer_than_k_votes_is_unavailable() -> None:
    """Fewer than ``k`` voting trials is unavailable, never a silent ``pass@n``."""
    trials = [
        _trial(verdict=True, rubric=True),
        _trial(verdict=True, rubric=True),
        _rubric_skipped_trial(verdict=True),
    ]
    assert PassPowK(k=3, over="rubric", fail=0.5).available(_ctx(trials)) is False
    assert PassPowK(k=2, over="rubric", fail=0.5).available(_ctx(trials)) is True


def test_grade_over_rubric_reads_rubric_layer() -> None:
    # 2 of 4 rubric layers pass => pass@1 over rubric = 2/4 = 0.5.
    trials = [
        _trial(verdict=True, rubric=True),
        _trial(verdict=True, rubric=True),
        _trial(verdict=False, rubric=False),
        _trial(verdict=False, rubric=False),
    ]
    check = PassAtK(k=1, over="rubric", fail=0.6)
    result = check.grade(_ctx(trials), _EMPTY)
    assert result.score == pytest.approx(0.5)
    assert result.passed is False  # 0.5 < 0.6


def test_grade_warn_only_still_passes() -> None:
    # A pure warn gate never fails the check (a warn is Rubric-level strict).
    trials = [_trial(verdict=v) for v in (True, True, False, False, False)]
    # pass@1 over verdict = 2/5 = 0.4; warn=0.9 (warns), no fail => passed True.
    check = PassAtK(k=1, over="verdict", warn=0.9)
    result = check.grade(_ctx(trials), _EMPTY)
    assert result.score == pytest.approx(0.4)
    assert result.passed is True
    (detail,) = result.subresults
    assert isinstance(detail, ScopeDetail)
    assert detail.level == "warn"


def test_grade_over_unknown_axis_raises() -> None:
    # Construction guards the axis, so reach in to exercise the grade-time guard.
    check = PassAtK(k=1, over="verdict")
    check.over = "bogus"
    with pytest.raises(ValueError, match="over"):
        check.grade(_ctx([_trial(verdict=True)]), _EMPTY)


def test_grade_over_missing_layer_raises() -> None:
    check = PassAtK(k=1, over="gate")  # but trials carry no gate layer
    with pytest.raises(ValueError, match="gate"):
        check.grade(_ctx([_trial(verdict=True)]), _EMPTY)


def test_available_only_with_trials() -> None:
    check = PassAtK(k=1, over="verdict")
    assert check.available(EvalContext(module=None, source="", label="x")) is False
    assert check.available(_ctx([_trial(verdict=True)])) is True


def test_check_is_deterministic_on_both_axes() -> None:
    check = PassPowK(k=2, over="verdict")
    assert check.cost is CostTier.DETERMINISTIC
    assert check.determinism is Determinism.DETERMINISTIC


def test_construction_rejects_bad_k_and_over() -> None:
    with pytest.raises(ValueError, match="k must"):
        PassAtK(k=0, over="verdict")
    with pytest.raises(ValueError, match="over"):
        PassAtK(k=1, over="bogus")


# --------------------------------------------------------------------------- #
# Handle builder: the metric-alone aggregate handle
# --------------------------------------------------------------------------- #


def test_aggregate_handle_builds_pass_at_k() -> None:
    bind = {"reliable": {"metric": "pass_at_k", "k": 5, "over": "verdict", "fail": 0.9}}
    handles = build_handles(bind, layer="aggregate")
    check = handles["reliable"]
    assert isinstance(check, PassAtK)
    assert check.k == 5
    assert check.over == "verdict"
    assert check.id == "pass_at_k:verdict@5"


def test_aggregate_handle_builds_pass_pow_k() -> None:
    bind = {"consistent": {"metric": "pass_pow_k", "k": 3, "over": "gate", "warn": 0.8}}
    check = build_handles(bind, layer="aggregate")["consistent"]
    assert isinstance(check, PassPowK)
    assert check.k == 3


def test_get_check_aggregate_swallows_max_worsening() -> None:
    # max_worsening is accepted (validator allows it) but ignored in C8.
    check = get_check("pass_at_k", k=2, over="verdict", fail=0.5, max_worsening=0.1)
    assert isinstance(check, PassAtK)


def test_check_with_metric_kwarg_is_still_a_check_shape() -> None:
    # A binding with BOTH check and metric is the standard 'check' shape; metric is
    # its kwarg (a threshold over a metric), NOT an aggregate handle.
    bind = {"cc": {"check": "threshold", "metric": "cyclomatic_complexity", "fail": 0.5}}
    check = build_handles(bind, layer="gate")["cc"]
    assert not isinstance(check, AggregateCheck)


# --------------------------------------------------------------------------- #
# compile_task: aggregate layer + trials_needed
# --------------------------------------------------------------------------- #

_GATE_BIND = {"build": {"check": "file_exists", "path": "x.py"}}


def test_compile_aggregate_composed_with_and() -> None:
    aggregate_bind = {
        "reliable": {"metric": "pass_at_k", "k": 5, "over": "verdict", "fail": 0.9},
        "consistent": {"metric": "pass_pow_k", "k": 3, "over": "verdict", "fail": 0.5},
    }
    compiled = compile_task(
        gate_bind=_GATE_BIND,
        gate_expr="build",
        verdict_trial="gate",
        aggregate_bind=aggregate_bind,
        aggregate_expr="reliable and consistent",
    )
    assert isinstance(compiled.aggregate, AllOf)
    assert compiled.trials_needed == 5  # max(5, 3)


def test_compile_single_aggregate_handle_defaults_expr() -> None:
    aggregate_bind = {"rel": {"metric": "pass_at_k", "k": 4, "over": "gate", "fail": 0.8}}
    compiled = compile_task(
        gate_bind=_GATE_BIND,
        gate_expr="build",
        verdict_trial="gate",
        aggregate_bind=aggregate_bind,
    )
    assert isinstance(compiled.aggregate, PassAtK)
    assert compiled.trials_needed == 4


def test_compile_no_aggregate_is_degenerate() -> None:
    compiled = compile_task(gate_bind=_GATE_BIND, gate_expr="build", verdict_trial="gate")
    assert compiled.aggregate is None
    assert compiled.trials_needed == 1


def test_compile_multi_aggregate_handle_no_expr_raises() -> None:
    aggregate_bind = {
        "a": {"metric": "pass_at_k", "k": 5, "over": "verdict", "fail": 0.9},
        "b": {"metric": "pass_pow_k", "k": 2, "over": "verdict", "fail": 0.5},
    }
    with pytest.raises(ValueError, match="compose"):
        compile_task(
            gate_bind=_GATE_BIND,
            gate_expr="build",
            verdict_trial="gate",
            aggregate_bind=aggregate_bind,
        )


# --------------------------------------------------------------------------- #
# short_circuit_safe: when the cross-layer short-circuit may skip work
# --------------------------------------------------------------------------- #

_SC_GATE_BIND = {"made": {"check": "file_exists", "path": "made.py"}}
_SC_RUBRIC_BIND = {"q": {"fail": 0.5, "rubric": [{"judge": "clear", "weight": 1.0}]}}


def _agg_bind(**handles: tuple[str, int]) -> dict[str, dict[str, object]]:
    return {
        name: {"metric": "pass_at_k", "k": k, "over": over, "fail": 0.5}
        for name, (over, k) in handles.items()
    }


@pytest.mark.parametrize(
    ("verdict", "safe"),
    [
        ("gate and rubric", True),
        ("rubric and gate", True),
        ("gate or rubric", False),
        ("rubric", False),
        ("gate and not rubric", False),
    ],
)
def test_short_circuit_is_safe_only_for_a_full_conjunction(verdict: str, safe: bool) -> None:
    compiled = compile_task(
        gate_bind=_SC_GATE_BIND, rubric_bind=_SC_RUBRIC_BIND, verdict_trial=verdict
    )
    assert compiled.short_circuit_safe is safe


def test_weighted_verdict_is_not_short_circuit_safe() -> None:
    compiled = compile_task(
        gate_bind=_SC_GATE_BIND,
        rubric_bind=_SC_RUBRIC_BIND,
        verdict_weights={"gate": 0.5, "rubric": 0.5},
        verdict_fail=0.5,
    )
    assert compiled.short_circuit_safe is False


@pytest.mark.parametrize(
    ("over", "safe"),
    [("verdict", True), ("gate", True), ("rubric", False)],
)
def test_aggregate_breaks_short_circuit_safety_only_over_a_skippable_layer(
    over: str, safe: bool
) -> None:
    """The judged rubric sits behind the deterministic gate, so only it is skippable."""
    compiled = compile_task(
        gate_bind=_SC_GATE_BIND,
        rubric_bind=_SC_RUBRIC_BIND,
        aggregate_bind=_agg_bind(a=(over, 2)),
    )
    assert compiled.aggregate_overs == {over}
    assert compiled.short_circuit_safe is safe


def test_composed_aggregate_collects_every_over_axis() -> None:
    compiled = compile_task(
        gate_bind=_SC_GATE_BIND,
        rubric_bind=_SC_RUBRIC_BIND,
        aggregate_bind=_agg_bind(a=("verdict", 3), b=("rubric", 2)),
        aggregate_expr="a and not b",
    )
    assert compiled.aggregate_overs == {"verdict", "rubric"}
    assert compiled.trials_needed == 3
    assert compiled.short_circuit_safe is False
