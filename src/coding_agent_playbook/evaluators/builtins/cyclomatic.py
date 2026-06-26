"""Cyclomatic complexity per function/method (SPEC prM §B)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.registry import Evaluator, register_evaluator
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    Measurement,
    RegressionPolicy,
)

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext


@register_evaluator
class CyclomaticComplexity(Evaluator):
    """McCabe cyclomatic complexity, one measurement per function/method.

    The value is computed once in :func:`parse_module` via the shared
    ``_cyclomatic`` helper; this evaluator just surfaces it per scope.
    """

    name = "cyclomatic_complexity"
    scope = Scope.FUNCTION
    value_kind = ValueKind.NUMERIC
    determinism = Determinism.DETERMINISTIC
    higher_is_worse = True
    requires = None
    default_absolute = AbsoluteThreshold(warn=10, fail=20)
    default_regression = RegressionPolicy(max_worsening=0.0)
    default_weight = 0.0

    def evaluate(self, ctx: EvalContext) -> list[Measurement]:
        if ctx.module is None:
            return []
        return [
            Measurement(evaluator=self.name, scope_key=fn.scope_key, value=float(fn.complexity))
            for fn in ctx.module.functions
        ]
