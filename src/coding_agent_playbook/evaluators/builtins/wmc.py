"""Weighted Methods per Class - sum of method cyclomatic complexity (§B)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.registry import Evaluator, register_evaluator
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    Measurement,
    RegressionPolicy,
)

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext

_NAME = "wmc"


def _measure(ctx: EvalContext) -> list[Measurement]:
    """Shared compute: WMC = ``sum(cyclomatic(method) for method in class)``.

    Reuses the same per-method complexity the shared ``_cyclomatic`` helper
    stored on each :class:`FunctionScope`, so CC and WMC never diverge; both the
    Evaluator and the Metric call this so the two layers stay in lockstep.
    """
    if ctx.module is None:
        return []
    return [
        Measurement(
            evaluator=_NAME,
            scope_key=cls.scope_key,
            value=float(sum(m.complexity for m in cls.methods)),
        )
        for cls in ctx.module.classes
    ]


@register_evaluator
class WeightedMethodsPerClass(Evaluator):
    """WMC = ``sum(cyclomatic(method) for method in class)``."""

    name = _NAME
    scope = Scope.CLASS
    value_kind = ValueKind.NUMERIC
    determinism = Determinism.DETERMINISTIC
    higher_is_worse = True
    requires = None
    default_absolute = AbsoluteThreshold(fail=50)
    default_regression = RegressionPolicy(max_worsening=0.0)
    default_weight = 0.0

    def evaluate(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)


@register_metric
class WeightedMethodsPerClassMetric(Metric):
    """``wmc`` as a :class:`Metric` (shares :func:`_measure`)."""

    name = _NAME
    scope = Scope.CLASS
    higher_is_worse = True
    requires = None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)
