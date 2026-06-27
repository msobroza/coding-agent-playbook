"""Grade coverage for higher-is-better evaluators (e.g. coverage/MI) (§C).

M1 ships no higher-is-better builtin (MI is M2), so these tests register a
temporary one to exercise the inverted absolute/regression branches that the
execution + MI evaluators will rely on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evaluators import registry as registry_mod
from coding_agent_playbook.evaluators.grade import grade
from coding_agent_playbook.evaluators.registry import Evaluator, register_evaluator
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    Measurement,
    MetricConfig,
    RegressionPolicy,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from coding_agent_playbook.evaluators.types import EvalContext

_NAME = "_coverage_like"


@pytest.fixture
def coverage_like() -> Iterator[None]:
    @register_evaluator
    class _CoverageLike(Evaluator):
        name = _NAME
        scope = Scope.FILE
        value_kind = ValueKind.NUMERIC
        determinism = Determinism.DETERMINISTIC
        higher_is_worse = False  # higher coverage is better
        default_absolute = AbsoluteThreshold(warn=80, fail=60)
        default_regression = RegressionPolicy(max_worsening=0.0)
        default_weight = 0.0

        def evaluate(self, ctx: EvalContext) -> list[Measurement]:
            return []

    try:
        yield
    finally:
        registry_mod._REGISTRY.pop(_NAME, None)


def _m(value: float) -> Measurement:
    return Measurement(evaluator=_NAME, scope_key="a.py", value=value)


def test_inverted_absolute_warn_and_fail(coverage_like: None) -> None:
    report = grade([_m(70)], None, MetricConfig(mode="absolute"))
    assert report.findings[0].level == "warn"  # 70 <= warn(80), > fail(60)
    report = grade([_m(55)], None, MetricConfig(mode="absolute"))
    assert report.findings[0].level == "fail"  # 55 <= fail(60)
    report = grade([_m(95)], None, MetricConfig(mode="absolute"))
    assert report.findings[0].level == "ok"  # above warn


def test_inverted_regression_detects_drop(coverage_like: None) -> None:
    # coverage dropped 90 -> 85: worsening = base - cand = 5 > 0 => regression.
    report = grade([_m(85)], [_m(90)], MetricConfig(mode="regression"))
    assert report.findings[0].level == "fail"
    assert report.findings[0].kind == "regression"


def test_inverted_regression_pass_on_improvement(coverage_like: None) -> None:
    report = grade([_m(95)], [_m(90)], MetricConfig(mode="regression"))
    assert report.findings[0].level == "ok"


# --- exact-boundary semantics (M4: strict < on higher-is-better) -------------
#
# These pin _absolute_level's boundary against the *real* builtin evaluators in
# absolute mode (no baseline). The higher-is-better cases below would each FAIL
# under the old inclusive ``<=`` logic (value AT the bound used to breach); the
# higher-is-worse case stays inclusive (``>=``) and pins that side too.


def _at(evaluator: str, scope: str, value: float) -> Measurement:
    return Measurement(evaluator=evaluator, scope_key=scope, value=value)


def test_boundary_cyclomatic_complexity_inclusive() -> None:
    # higher_is_worse=True, default warn=10 fail=20 -> inclusive ``>=``.
    candidate = [
        _at("cyclomatic_complexity", "a.py::fl", 20),  # == fail
        _at("cyclomatic_complexity", "a.py::wn", 10),  # == warn
        _at("cyclomatic_complexity", "a.py::ok", 9),  # below warn
    ]
    report = grade(candidate, None, MetricConfig(mode="absolute"))
    levels = {f.scope_key: f.level for f in report.findings}
    assert levels["a.py::fl"] == "fail"
    assert levels["a.py::wn"] == "warn"
    assert levels["a.py::ok"] == "ok"


def test_boundary_coverage_warn_is_strict() -> None:
    # higher_is_better, default warn=80 -> value AT warn is ok (old <= => warn).
    at_warn = grade([_at("coverage", "a.py", 80.0)], None, MetricConfig(mode="absolute"))
    assert at_warn.findings[0].level == "ok"  # 80 < 80 is False
    below_warn = grade([_at("coverage", "a.py", 79.0)], None, MetricConfig(mode="absolute"))
    assert below_warn.findings[0].level == "warn"  # 79 < 80


def test_boundary_test_pass_rate_fail_is_strict() -> None:
    # higher_is_better, default fail=1.0 -> a perfect run is ok (old <= => fail).
    perfect = grade([_at("test_pass_rate", "<project>", 1.0)], None, MetricConfig(mode="absolute"))
    assert perfect.findings[0].level == "ok"  # 1.0 < 1.0 is False
    imperfect = grade(
        [_at("test_pass_rate", "<project>", 0.99)],
        None,
        MetricConfig(mode="absolute"),
    )
    assert imperfect.findings[0].level == "fail"  # 0.99 < 1.0


def test_boundary_maintainability_index_fail_is_strict() -> None:
    # higher_is_better, default fail=65 -> value AT fail is ok (old <= => fail).
    at_fail = grade(
        [_at("maintainability_index", "a.py", 65.0)],
        None,
        MetricConfig(mode="absolute"),
    )
    assert at_fail.findings[0].level == "ok"  # 65 < 65 is False
    below_fail = grade(
        [_at("maintainability_index", "a.py", 64.0)],
        None,
        MetricConfig(mode="absolute"),
    )
    assert below_fail.findings[0].level == "fail"  # 64 < 65
