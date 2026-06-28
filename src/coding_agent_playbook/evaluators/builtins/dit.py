"""DIT - depth of inheritance tree (SPEC prM §B, approximate).

Depth is the longest resolvable base chain. A base that names another class in
the same module recurses (``depth = 1 + base_depth``); a base the parser cannot
resolve (external, cross-module) is treated as depth ``1``; a class with no
bases is depth ``0``. Cross-module bases are approximated - low signal in
idiomatic Python (see §I).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import Measurement

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext

_NAME = "dit"


def _measure(ctx: EvalContext) -> list[Measurement]:
    """Shared compute: one DIT (inheritance depth) measurement per class scope.

    The per-class depth is resolved by the module-level :func:`_dit` helper.
    """
    if ctx.module is None:
        return []
    bases_by_qualname = {cls.qualname: cls.bases for cls in ctx.module.classes}
    results: list[Measurement] = []
    for cls in ctx.module.classes:
        depth = _dit(cls.qualname, bases_by_qualname, set())
        results.append(Measurement(evaluator=_NAME, scope_key=cls.scope_key, value=float(depth)))
    return results


@register_metric
class DepthOfInheritanceMetric(Metric):
    """``dit`` as a :class:`Metric` (shares :func:`_measure`)."""

    name = _NAME
    scope = Scope.CLASS
    higher_is_worse = True
    requires = None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)


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
