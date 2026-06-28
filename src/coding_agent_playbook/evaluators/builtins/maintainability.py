"""Radon-backed Maintainability Index, one value per file (SPEC prM §B, M2).

The Maintainability Index (MI) is the lone static metric that radon - not the
stdlib ``ast`` core - computes, so this evaluator declares ``requires="radon"``
and is the engine's only **optional extra** (``pip install
'coding-agent-playbook[metrics]'``). It is registered like every other builtin,
but :meth:`available` returns ``False`` when radon is not importable, so the gate
transparently skips it and the engine still loads with nothing extra installed.

``radon`` is imported **lazily inside** :meth:`evaluate` - never at module
top-level - so importing this module (which happens on every registry load)
never requires the optional dependency. Higher MI is *better* (more
maintainable), hence ``higher_is_worse=False`` and the ``fail=65`` floor.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.parse import scope_key
from coding_agent_playbook.evaluators.registry import Evaluator, register_evaluator
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    Measurement,
    RegressionPolicy,
)

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext

_NAME = "maintainability_index"


def _available(ctx: EvalContext) -> bool:
    """True only when radon is importable *and* a parsed module is present.

    Shared by both the Evaluator and the Metric so the radon-absent skip behaves
    identically on each layer. Mirrors the ABC's dependency probe (``find_spec``)
    but also requires a parsed module, so the gate skips MI both when the optional
    extra is missing and when there is nothing static to measure.
    """
    if importlib.util.find_spec("radon") is None:
        return False
    return ctx.module is not None


def _measure(ctx: EvalContext) -> list[Measurement]:
    """Shared compute: one FILE-scope MI measurement (radon imported lazily here).

    Both the Evaluator and the Metric call this. ``radon`` is imported lazily so
    importing this module never requires the optional dependency.
    """
    if ctx.module is None:
        return []
    from radon.metrics import mi_visit

    value = mi_visit(ctx.source, multi=True)
    return [
        Measurement(
            evaluator=_NAME,
            scope_key=scope_key(ctx.label, None),
            value=float(value),
        )
    ]


@register_evaluator
class MaintainabilityIndex(Evaluator):
    """Maintainability Index over a whole file via :func:`radon.metrics.mi_visit`.

    FILE scope => a single measurement keyed by the bare label. The value is the
    SEI 0-100 MI variant (``multi=True``); larger means *more* maintainable, so
    ``higher_is_worse`` is ``False`` and the absolute bound is a ``fail`` floor.
    """

    name = _NAME
    scope = Scope.FILE
    value_kind = ValueKind.NUMERIC
    determinism = Determinism.DETERMINISTIC
    higher_is_worse = False
    requires = "radon"
    default_absolute = AbsoluteThreshold(fail=65.0)
    default_regression = RegressionPolicy(max_worsening=0.0)
    default_weight = 0.0

    def available(self, ctx: EvalContext) -> bool:
        return _available(ctx)

    def evaluate(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)


@register_metric
class MaintainabilityIndexMetric(Metric):
    """``maintainability_index`` as a :class:`Metric` (shares :func:`_measure`).

    Keeps ``requires="radon"`` and the lazy import; :meth:`available` returns
    ``False`` when radon is absent so the metric layer skips MI on an air-gapped
    install exactly like the Evaluator does.
    """

    name = _NAME
    scope = Scope.FILE
    higher_is_worse = False
    requires = "radon"

    def available(self, ctx: EvalContext) -> bool:
        return _available(ctx)

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)
