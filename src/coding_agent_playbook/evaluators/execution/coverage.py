"""``coverage`` — line-coverage percentage per file + a suite total (M4).

A FILE-scope NUMERIC metric (percentage ``0-100``): one measurement per source
file coverage.py reported, plus one MODULE-scope measurement for the overall
total. Higher is better, so it normalizes through
:class:`~coding_agent_playbook.evaluators.normalizer.PercentNormalizer`
(``80 -> 0.8``); the absolute default ``warn=0.8`` flags files whose normalized
score drops below ``0.8`` (under 80% coverage), and ``max_worsening=0`` means
coverage must not drop versus baseline.

Reads the **same** :meth:`ProjectHandle.run` cache the ``test_pass_rate``
metric uses, so enabling both under ``--run-tests`` still runs the suite only
once. ``needs_project=True`` ⇒ execution metric, excluded from
``static_metrics()``; :meth:`available` requires ``ctx.project``.

Scope keys: per-file measurements key on the file's path relative to the
project root (e.g. ``pkg/a.py``) so they match across baseline and candidate
runs; the MODULE total keys on the bare ``ctx.label``. With the default bare
``--cov`` that path *is* coverage.py's ``filename``; in source mode
(``--cov=src``, which ``diff_coverage`` turns on) coverage.py writes it relative
to the source, so it is mapped back through
:func:`~coding_agent_playbook.evaluators.execution.coverage_xml.repo_relative`
and the keys stay the same whichever mode ran (prK §F.1.1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.execution.coverage_xml import repo_relative
from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.normalizer import PercentNormalizer
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
    root = ctx.project.root
    per_file = {
        repo_relative(filename, report.sources, root) or filename: pct
        for filename, pct in report.per_file.items()
    }
    measurements = [
        Measurement(
            evaluator=_NAME,
            scope_key=scope_key(filename, None),
            value=float(pct),
        )
        for filename, pct in sorted(per_file.items())
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
    normalizer = PercentNormalizer()
    requires = None
    needs_project = True

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)
