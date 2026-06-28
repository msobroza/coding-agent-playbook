"""Cyclomatic complexity per function/method (SPEC prM §B)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.normalizer import RampNormalizer
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import Measurement

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext

_NAME = "cyclomatic_complexity"


def _measure(ctx: EvalContext) -> list[Measurement]:
    """Shared compute: one CC measurement per function/method scope.

    :class:`CyclomaticComplexityMetric` calls this; the value is computed once in
    :func:`parse_module` via the shared ``_cyclomatic`` helper, so this just
    surfaces it per scope.
    """
    if ctx.module is None:
        return []
    return [
        Measurement(evaluator=_NAME, scope_key=fn.scope_key, value=float(fn.complexity))
        for fn in ctx.module.functions
    ]


@register_metric
class CyclomaticComplexityMetric(Metric):
    """``cyclomatic_complexity`` as a :class:`Metric` (shares :func:`_measure`)."""

    name = _NAME
    scope = Scope.FUNCTION
    normalizer = RampNormalizer(good=5, bad=20)
    requires = None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)
