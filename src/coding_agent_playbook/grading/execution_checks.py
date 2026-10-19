"""Convenience execution ``Check`` factories (T4a).

These are *thin* wrappers over the deterministic, metric-backed
:class:`~coding_agent_playbook.grading.check.ThresholdCheck` (T3) bound to the
execution :class:`~coding_agent_playbook.grading.metric.Metric` builtins
(``test_pass_rate``, ``coverage``). They add **no** measurement or threshold
logic of their own - the underlying metrics already reuse the cached
:class:`~coding_agent_playbook.grading.execution_metrics.project.ProjectHandle` run, and
``ThresholdCheck`` already owns the per-scope grading. Each wrapper just picks the
metric + the conventional default bounds so an eval author writes
``TestsPassCheck()`` / ``CoverageCheck()`` instead of repeating the metric lookup.

Because the bound metrics carry ``needs_project=True``, the resulting checks
auto-derive :attr:`~coding_agent_playbook.grading.scope.CostTier.EXECUTION`
(via ``ThresholdCheck.__init__`` reading ``metric.needs_project``), so a
``Rubric`` containing one flips its ``needs_project`` on and a cheapest-first
scheduler runs it after the deterministic checks.
"""

from __future__ import annotations

from coding_agent_playbook.grading.check import ThresholdCheck
from coding_agent_playbook.grading.check_registry import register_check
from coding_agent_playbook.grading.metric import get_metric


@register_check("tests_pass")
def TestsPassCheck(*, weight: float = 0.0, required: bool = True) -> ThresholdCheck:
    """A check requiring **every** test to pass (``test_pass_rate``, ``fail=1.0``).

    ``test_pass_rate`` is higher-is-better, so ``fail=1.0`` means a rate strictly
    below ``1.0`` fails (any failing test sinks the check) while exactly ``1.0``
    is ``ok``. Required by default - a broken suite should fail the gate. The
    EXECUTION cost tier is derived from the metric's ``needs_project``.
    """
    return ThresholdCheck(
        get_metric("test_pass_rate"),
        fail=1.0,
        weight=weight,
        required=required,
    )


@register_check("coverage")
def CoverageCheck(
    *,
    warn: float = 0.8,
    fail: float | None = None,
    weight: float = 0.0,
    required: bool = False,
) -> ThresholdCheck:
    """A check flagging files under a coverage floor (``coverage``, ``warn=0.8``).

    Higher-is-better: a file whose normalized score is below ``warn`` (default
    ``0.8``, i.e. under 80% coverage) warns, and below ``fail`` (unset by
    default) fails. The bounds are ``0-1`` cutoffs on the normalized score, not
    raw percentages: the old raw ``warn=80.0`` could never be met, since
    ``PercentNormalizer`` tops out at ``1.0`` (prK §F.1.1). Advisory by default
    (``required=False``) so a coverage dip is a warning, not a hard gate
    failure, unless the author opts in. The EXECUTION cost tier is derived from
    the metric's ``needs_project``.

    Example::

        >>> full = MeasurementSet([Measurement("coverage", "a.py", 100.0)])
        >>> CoverageCheck().grade(ctx, full).subresults[0].level  # doctest: +SKIP
        'ok'
    """
    return ThresholdCheck(
        get_metric("coverage"),
        warn=warn,
        fail=fail,
        weight=weight,
        required=required,
    )


__all__ = ["CoverageCheck", "TestsPassCheck"]
