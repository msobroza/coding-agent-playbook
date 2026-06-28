"""Weighted Methods per Class - sum of method cyclomatic complexity (§B)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.normalizer import RampNormalizer
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import Measurement

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext

_NAME = "wmc"


def _measure(ctx: EvalContext) -> list[Measurement]:
    """Shared compute: WMC = ``sum(cyclomatic(method) for method in class)``.

    Reuses the same per-method complexity the shared ``_cyclomatic`` helper
    stored on each :class:`FunctionScope`, so CC and WMC never diverge.
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


@register_metric
class WeightedMethodsPerClassMetric(Metric):
    """``wmc`` as a :class:`Metric` (shares :func:`_measure`)."""

    name = _NAME
    scope = Scope.CLASS
    normalizer = RampNormalizer(good=10, bad=60)
    requires = None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)
