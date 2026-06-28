"""``test_pass_rate`` — fraction of (non-skipped) tests that pass (M4).

A MODULE-scope SCORE over a single suite run: ``passed / (total - skipped)``
(skips are excluded from the denominator - a skipped test is neither a pass nor a
failure; see :meth:`JunitSummary.pass_rate`). Higher is better, so
``higher_is_worse=False``; the absolute default ``fail=1.0`` means *every* test
must pass, and ``max_worsening=0`` means no newly-failing test versus baseline.

``needs_project=True`` ⇒ this is an *execution* metric, excluded from
``static_metrics()`` and only run under ``--run-tests``; :meth:`available`
returns ``True`` only when ``ctx.project`` is present.

**Flaky-retry (optional, OFF by default).** ``test_pass_rate`` is DETERMINISTIC,
but a single project run can be flaky. When configured (``flaky_retries > 0`` via
``ctx.project.flaky_retries``) the handle reruns and the *best* observed pass
rate across attempts is used, so a test that passes on retry no longer counts as
a failure. The default is ``0`` (single run, fully deterministic).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.parse import scope_key
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import Measurement

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext

_NAME = "test_pass_rate"


def _measure(ctx: EvalContext) -> list[Measurement]:
    """Shared compute: run the suite (cached) and emit one MODULE pass-rate SCORE.

    Uses the handle's flaky-tolerant ``best_pass_rate`` so an enabled
    ``flaky_retries`` is honoured; with the default (``0``) it is exactly the
    single cached run's rate.
    """
    if ctx.project is None:
        return []
    rate = ctx.project.best_pass_rate()
    return [
        Measurement(
            evaluator=_NAME,
            scope_key=scope_key(ctx.label, None),
            value=float(rate),
        )
    ]


@register_metric
class TestPassRateMetric(Metric):
    """``test_pass_rate`` as a :class:`Metric`.

    ``needs_project=True`` ⇒ the inherited :meth:`Metric.available` requires
    ``ctx.project`` (the project-handle gate).
    """

    name = _NAME
    scope = Scope.MODULE
    higher_is_worse = False
    requires = None
    needs_project = True

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)
