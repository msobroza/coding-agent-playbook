"""``file_sloc``: radon's source lines of code, one value per file (prK §F.2.1).

It fills the one gap ruff lacks (there is no too-many-lines rule) without new
metric code: ``radon.raw.analyze(source).sloc``. radon is the engine's one
optional extra, so the metric declares ``requires="radon"``, imports it lazily
inside :func:`_measure`, and is unavailable without it, like
``maintainability_index``.

It is opt-in (``OPT_IN_METRICS``) and regression-exempt (``max_worsening =
1.0``): a growing legacy file is never a regression. A new file is graded only
when a band is configured, e.g. ``[metrics.thresholds.file_sloc] warn = 1.0``
(over 300 SLOC) and ``fail = 0.6`` (over 500).
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.normalizer import RampNormalizer
from coding_agent_playbook.evaluators.parse import scope_key
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import Measurement

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext

__all__ = ["FileSlocMetric"]

_NAME: Final = "file_sloc"


def _measure(ctx: EvalContext) -> list[Measurement]:
    """One FILE measurement: radon's raw SLOC (radon imported only here)."""
    if ctx.module is None:
        return []
    from radon.raw import analyze

    return [Measurement(_NAME, scope_key(ctx.label, None), float(analyze(ctx.source).sloc))]


@register_metric
class FileSlocMetric(Metric):
    """``file_sloc`` as a :class:`Metric`: falls from 1.0 at 300 SLOC to 0.0 at 800."""

    name = _NAME
    scope = Scope.FILE
    normalizer = RampNormalizer(good=300, bad=800)
    requires = "radon"

    def available(self, ctx: EvalContext) -> bool:
        """Only with radon importable and a parsed module."""
        return importlib.util.find_spec("radon") is not None and ctx.module is not None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)
