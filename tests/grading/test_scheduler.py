"""Tests for the cost-tiered short-circuit scheduler (T4b) - ``grading/scheduler.py``.

:func:`~coding_agent_playbook.grading.scheduler.schedule` is the Strategy a
:class:`~coding_agent_playbook.grading.rubric.Rubric` (and the boolean
composers) use to run a list of checks: ascending
:class:`~coding_agent_playbook.grading.scope.CostTier` (DETERMINISTIC ->
EXECUTION -> JUDGED), concurrent **within** a tier when ``max_workers > 1``,
results always returned in **authored order**, and a short-circuit that stops
descending into costlier tiers once the verdict is decided.

The headline guarantee: with ``op="and"`` a failing required DETERMINISTIC check
means the JUDGED tier is **never graded** - a :class:`~coding_agent_playbook.evals.judge.StubJudge`
records **zero** calls. These also cover ``op="or"`` early-out, the
``short_circuit=False`` "same verdict, more work" invariant, authored-order
stability under concurrency, and an unavailable check skipping cleanly.
"""

from __future__ import annotations

from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.grading.check import Check, MeasurementSet
from coding_agent_playbook.grading.judged import JudgeCheck
from coding_agent_playbook.grading.scheduler import schedule
from coding_agent_playbook.grading.scope import CostTier, Determinism
from coding_agent_playbook.grading.types import CheckResult, EvalContext


def _ctx(judge: StubJudge | None = None, *, samples: int = 1) -> EvalContext:
    return EvalContext(
        module=None,
        source="",
        label="scheduler",
        judge=judge,
        artifact="ART",
        samples=samples,
    )


def _empty() -> MeasurementSet:
    return MeasurementSet([], None)


class _Stub(Check):
    """A leaf check returning a fixed verdict, with a configurable cost tier.

    Records every ``grade`` call onto a shared ``ran`` list so tests can assert
    which checks were actually invoked (vs short-circuited / skipped).
    """

    determinism = Determinism.DETERMINISTIC

    def __init__(
        self,
        tag: str,
        *,
        passed: bool,
        cost: CostTier = CostTier.DETERMINISTIC,
        required: bool = True,
        weight: float = 0.0,
        avail: bool = True,
        ran: list[str] | None = None,
    ) -> None:
        self.id = tag
        self._passed = passed
        self.cost = cost
        self.required = required
        self.weight = weight
        self._avail = avail
        self._ran = ran if ran is not None else []

    def available(self, ctx: EvalContext) -> bool:
        return self._avail

    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
        self._ran.append(self.id)
        return CheckResult(
            check_id=self.id,
            passed=self._passed,
            score=1.0 if self._passed else 0.0,
            weight=self.weight,
            required=self.required,
            determinism=self.determinism,
            cost=self.cost,
            status="run",
            subresults=(),
        )


def _by_id(results: list[CheckResult]) -> dict[str, CheckResult]:
    return {r.check_id: r for r in results}


# --------------------------------------------------------------------------- #
# The headline guarantee: AND short-circuit never invokes the judge.
# --------------------------------------------------------------------------- #


def test_and_short_circuit_never_invokes_the_judge() -> None:
    judge = StubJudge({"well documented": 1.0})
    ran: list[str] = []
    det = _Stub("det", passed=False, required=True, ran=ran)
    judged = JudgeCheck("well documented", required=True)
    ctx = _ctx(judge=judge)

    results = schedule([det, judged], ctx, _empty(), op="and", short_circuit=True)

    by_id = _by_id(results)
    # The deterministic check ran and failed.
    assert by_id["det"].status == "run"
    assert by_id["det"].passed is False
    assert ran == ["det"]
    # The judged check was short-circuited away (costlier tier, never graded).
    assert by_id["judge:well-documented"].status == "skipped"
    assert by_id["judge:well-documented"].passed is False
    # Headline: the judge was NEVER invoked.
    assert judge.calls == []


def test_and_short_circuit_runs_judge_when_deterministic_tier_passes() -> None:
    # The complement: when the cheap tier passes, the judge IS reached.
    judge = StubJudge({"well documented": 1.0})
    det = _Stub("det", passed=True, required=True)
    judged = JudgeCheck("well documented", required=True)
    ctx = _ctx(judge=judge)

    results = schedule([det, judged], ctx, _empty(), op="and", short_circuit=True)

    by_id = _by_id(results)
    assert by_id["judge:well-documented"].status == "run"
    assert judge.calls == [("well documented", "ART", 1)]


def test_non_required_deterministic_failure_does_not_short_circuit_and() -> None:
    # AND only short-circuits on a *required* failure; a non-required fail does not.
    judge = StubJudge({"crit": 1.0})
    det = _Stub("det", passed=False, required=False)
    judged = JudgeCheck("crit", required=True)
    ctx = _ctx(judge=judge)

    results = schedule([det, judged], ctx, _empty(), op="and", short_circuit=True)

    by_id = _by_id(results)
    assert by_id["judge:crit"].status == "run"
    assert judge.calls == [("crit", "ART", 1)]


# --------------------------------------------------------------------------- #
# OR short-circuit: stop at the first pass.
# --------------------------------------------------------------------------- #


def test_or_short_circuit_stops_at_first_pass() -> None:
    judge = StubJudge({"crit": 1.0})
    ran: list[str] = []
    det = _Stub("det", passed=True, required=False, ran=ran)
    judged = JudgeCheck("crit", required=False)
    ctx = _ctx(judge=judge)

    results = schedule([det, judged], ctx, _empty(), op="or", short_circuit=True)

    by_id = _by_id(results)
    assert by_id["det"].status == "run"
    assert by_id["det"].passed is True
    assert ran == ["det"]
    # The later (costlier) check is skipped once a pass is seen.
    assert by_id["judge:crit"].status == "skipped"
    assert judge.calls == []


def test_or_continues_when_first_tier_fails() -> None:
    judge = StubJudge({"crit": 1.0})
    det = _Stub("det", passed=False, required=False)
    judged = JudgeCheck("crit", required=False)
    ctx = _ctx(judge=judge)

    results = schedule([det, judged], ctx, _empty(), op="or", short_circuit=True)

    by_id = _by_id(results)
    assert by_id["det"].passed is False
    assert by_id["judge:crit"].status == "run"
    assert judge.calls == [("crit", "ART", 1)]


# --------------------------------------------------------------------------- #
# short_circuit=False does the same verdict, just more work.
# --------------------------------------------------------------------------- #


def _and_verdict(results: list[CheckResult]) -> bool:
    run_required = [r for r in results if r.required and r.status == "run"]
    return all(r.passed for r in run_required)


def test_short_circuit_false_runs_everything_same_verdict() -> None:
    judge = StubJudge({"crit": 1.0})
    det = _Stub("det", passed=False, required=True)
    judged = JudgeCheck("crit", required=True)

    short = schedule(
        [det, JudgeCheck("crit", required=True)],
        _ctx(judge=StubJudge({"crit": 1.0})),
        _empty(),
        op="and",
        short_circuit=True,
    )
    full = schedule(
        [_Stub("det", passed=False, required=True), judged],
        _ctx(judge=judge),
        _empty(),
        op="and",
        short_circuit=False,
    )

    # Short-circuit skipped the judge; full ran it.
    assert _by_id(short)["judge:crit"].status == "skipped"
    assert _by_id(full)["judge:crit"].status == "run"
    assert judge.calls == [("crit", "ART", 1)]
    # Verdict is identical: a required det failure sinks AND either way.
    assert _and_verdict(short) is False
    assert _and_verdict(full) is False


# --------------------------------------------------------------------------- #
# Concurrency preserves authored order.
# --------------------------------------------------------------------------- #


def test_max_workers_preserves_authored_order() -> None:
    tags = [f"c{i}" for i in range(8)]
    for _ in range(5):  # repeat: order must be stable across runs
        checks: list[Check] = [_Stub(t, passed=True) for t in tags]
        results = schedule(
            checks,
            _ctx(),
            _empty(),
            op="and",
            short_circuit=False,
            max_workers=4,
        )
        assert [r.check_id for r in results] == tags


def test_max_workers_one_is_sequential_authored_order() -> None:
    tags = ["a", "b", "c"]
    checks: list[Check] = [_Stub(t, passed=True) for t in tags]
    results = schedule(checks, _ctx(), _empty(), op="and", short_circuit=False, max_workers=1)
    assert [r.check_id for r in results] == tags


# --------------------------------------------------------------------------- #
# Unavailable checks skip; tiering; empty input.
# --------------------------------------------------------------------------- #


def test_unavailable_check_is_skipped_not_run() -> None:
    ran: list[str] = []
    avail = _Stub("avail", passed=True, ran=ran)
    unavail = _Stub("unavail", passed=True, avail=False, ran=ran)

    results = schedule([avail, unavail], _ctx(), _empty(), op="and", short_circuit=True)

    by_id = _by_id(results)
    assert by_id["avail"].status == "run"
    assert by_id["unavail"].status == "skipped"
    assert by_id["unavail"].passed is False
    assert by_id["unavail"].score is None
    assert ran == ["avail"]  # the unavailable check was never graded


def test_skipped_result_carries_check_descriptors() -> None:
    unavail = _Stub(
        "u",
        passed=True,
        cost=CostTier.JUDGED,
        required=True,
        weight=2.5,
        avail=False,
    )
    (result,) = schedule([unavail], _ctx(), _empty(), op="and")
    assert result.status == "skipped"
    assert result.check_id == "u"
    assert result.weight == 2.5
    assert result.required is True
    assert result.determinism is Determinism.DETERMINISTIC
    assert result.cost is CostTier.JUDGED


def test_tiers_run_cheapest_first() -> None:
    ran: list[str] = []
    judged = _Stub("j", passed=True, cost=CostTier.JUDGED, ran=ran)
    deterministic = _Stub("d", passed=True, cost=CostTier.DETERMINISTIC, ran=ran)
    execution = _Stub("e", passed=True, cost=CostTier.EXECUTION, ran=ran)

    # Authored order is judged-first, but execution order is by ascending tier.
    results = schedule(
        [judged, execution, deterministic],
        _ctx(),
        _empty(),
        op="and",
        short_circuit=False,
    )
    assert ran == ["d", "e", "j"]
    # Returned order is the AUTHORED order, regardless of run order.
    assert [r.check_id for r in results] == ["j", "e", "d"]


def test_empty_check_list_returns_empty() -> None:
    assert schedule([], _ctx(), _empty(), op="and") == []
