"""``coverage`` — line-coverage percentage per file + a suite total (M4).

A FILE-scope NUMERIC metric (percentage ``0-100``): one measurement per source
file coverage.py reported, plus one MODULE-scope measurement for the overall
total. Higher is better (``higher_is_worse=False``); the absolute default
``warn=80`` flags files under 80% coverage, and ``max_worsening=0`` means coverage
must not drop versus baseline.

Reads the **same** :meth:`ProjectHandle.run` cache the ``test_pass_rate``
metric uses, so enabling both under ``--run-tests`` still runs the suite only
once. ``needs_project=True`` ⇒ execution metric, excluded from
``static_metrics()``; :meth:`available` requires ``ctx.project``.

Scope keys: per-file measurements key on the coverage.py ``filename`` (a path
relative to the project root, e.g. ``pkg/a.py``) so they match across baseline
and candidate runs; the MODULE total keys on the bare ``ctx.label``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.parse import scope_key
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import Measurement

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext

_NAME = "coverage"


def _measure(ctx: EvalContext) -> list[Measurement]:
    """Shared compute: one FILE coverage measurement per file + one MODULE total.

    Reads :meth:`ProjectHandle.run` (cached), so the suite never re-runs even when
    ``test_pass_rate`` already triggered it.
    """
    if ctx.project is None:
        return []
    report = ctx.project.run().coverage
    measurements = [
        Measurement(
            evaluator=_NAME,
            scope_key=scope_key(filename, None),
            value=float(pct),
        )
        for filename, pct in sorted(report.per_file.items())
    ]
    measurements.append(
        Measurement(
            evaluator=_NAME,
            scope_key=scope_key(ctx.label, None),
            value=float(report.total),
        )
    )
    return measurements


@register_metric
class CoverageMetric(Metric):
    """``coverage`` as a :class:`Metric` over per-file + MODULE-total coverage.

    ``needs_project=True`` ⇒ the inherited :meth:`Metric.available` requires
    ``ctx.project`` (the project-handle gate).
    """

    name = _NAME
    scope = Scope.FILE
    higher_is_worse = False
    requires = None
    needs_project = True

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)
