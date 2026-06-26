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
