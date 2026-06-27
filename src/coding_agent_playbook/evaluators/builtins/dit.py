"""DIT - depth of inheritance tree (SPEC prM §B, approximate).

Depth is the longest resolvable base chain. A base that names another class in
the same module recurses (``depth = 1 + base_depth``); a base the parser cannot
resolve (external, cross-module) is treated as depth ``1``; a class with no
bases is depth ``0``. Cross-module bases are approximated - low signal in
idiomatic Python (see §I).
"""

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
class DepthOfInheritance(Evaluator):
    """DIT - depth of the inheritance tree for each class."""

    name = "dit"
    scope = Scope.CLASS
    value_kind = ValueKind.NUMERIC
    determinism = Determinism.DETERMINISTIC
    higher_is_worse = True
    requires = None
    default_absolute = AbsoluteThreshold(warn=5)
    default_regression = RegressionPolicy(max_worsening=0.0)
    default_weight = 0.0

    def evaluate(self, ctx: EvalContext) -> list[Measurement]:
        if ctx.module is None:
            return []
        bases_by_qualname = {cls.qualname: cls.bases for cls in ctx.module.classes}
        results: list[Measurement] = []
        for cls in ctx.module.classes:
            depth = _dit(cls.qualname, bases_by_qualname, set())
            results.append(
                Measurement(evaluator=self.name, scope_key=cls.scope_key, value=float(depth))
            )
        return results


def _dit(qualname: str, bases_by_qualname: dict[str, list[str]], seen: set[str]) -> int:
    bases = bases_by_qualname.get(qualname, [])
    if not bases or qualname in seen:
        return 0
    seen = seen | {qualname}
    best = 0
    for base in bases:
        if base in bases_by_qualname:
            best = max(best, 1 + _dit(base, bases_by_qualname, seen))
        else:
            # External / unresolvable base: the chain has depth 1.
            best = max(best, 1)
    return best
