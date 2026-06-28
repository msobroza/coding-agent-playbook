"""Granularity of a metric-backed ``Check`` (T3).

A single :class:`~coding_agent_playbook.evaluators.check.ThresholdCheck` over a
:class:`~coding_agent_playbook.evaluators.check.MeasurementSet` with *N* function
scopes yields exactly **one** :class:`~coding_agent_playbook.evaluators.types.CheckResult`
carrying *N* :class:`~coding_agent_playbook.evaluators.types.ScopeDetail`
subresults - one check, N per-scope rows. ``passed`` is the AND over scopes (any
``fail`` sinks the check) and ``score`` is the mean of the per-scope ramps.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.evaluators.check import MeasurementSet, ThresholdCheck
from coding_agent_playbook.evaluators.metric import Metric
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import (
    CheckResult,
    EvalContext,
    Measurement,
    ScopeDetail,
)


class _CC(Metric):
    name = "cyclomatic_complexity"
    scope = Scope.FUNCTION
    higher_is_worse = True
    requires = None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return []


def _ctx() -> EvalContext:
    return EvalContext(module=None, source="", label="check")


def _cc(scope: str, value: float) -> Measurement:
    return Measurement(evaluator="cyclomatic_complexity", scope_key=scope, value=value)


def _details(result: CheckResult) -> list[ScopeDetail]:
    """Narrow ``subresults`` to leaf :class:`ScopeDetail` rows for the type checker."""
    out: list[ScopeDetail] = []
    for d in result.subresults:
        assert isinstance(d, ScopeDetail)
        out.append(d)
    return out


def test_one_check_n_subresults_with_a_failure() -> None:
    # Four function scopes: three ok (ramp 1.0), one fail (>= fail(20), ramp 0.0).
    check = ThresholdCheck(_CC(), warn=10, fail=20)
    ms = MeasurementSet(
        [
            _cc("m.py::a", 3),  # ok -> 1.0
            _cc("m.py::b", 5),  # ok -> 1.0
            _cc("m.py::c", 8),  # ok -> 1.0
            _cc("m.py::d", 25),  # fail -> 0.0
        ]
    )
    result = check.grade(_ctx(), ms)

    # ONE CheckResult with N per-scope subresults.
    assert len(result.subresults) == 4
    assert result.passed is False  # one scope failed
    # score == mean of per-scope ramps = (1 + 1 + 1 + 0) / 4.
    assert result.score == pytest.approx(0.75)
    levels = {d.scope_key: d.level for d in _details(result)}
    assert levels["m.py::d"] == "fail"
    assert levels["m.py::a"] == "ok"


def test_one_check_all_pass() -> None:
    check = ThresholdCheck(_CC(), warn=10, fail=20)
    ms = MeasurementSet([_cc("m.py::a", 3), _cc("m.py::b", 5), _cc("m.py::c", 9)])
    result = check.grade(_ctx(), ms)
    assert len(result.subresults) == 3
    assert result.passed is True
    assert result.score == pytest.approx(1.0)  # all ramps 1.0


def test_one_check_mixed_warns_still_passes() -> None:
    # Warns lower the score but do not fail the check (strict is Rubric-level).
    check = ThresholdCheck(_CC(), warn=10, fail=20)
    ms = MeasurementSet([_cc("m.py::a", 3), _cc("m.py::b", 15)])  # ok(1.0) + warn(0.5)
    result = check.grade(_ctx(), ms)
    assert result.passed is True
    assert result.score == pytest.approx(0.75)  # (1.0 + 0.5) / 2
    levels = {d.scope_key: d.level for d in _details(result)}
    assert levels["m.py::b"] == "warn"
