"""Shared metric-policy defaults + the metric-backed ``Check`` builder.

The single home for the per-metric default grading policy and the
:func:`metric_check` factory that turns a metric name + a
:class:`~coding_agent_playbook.evaluators.types.MetricConfig` into the
metric-backed :class:`~coding_agent_playbook.evaluators.check.Check`
(:class:`~coding_agent_playbook.evaluators.check.ThresholdCheck` /
:class:`~coding_agent_playbook.evaluators.check.NonRegressionCheck`). Both
:func:`coding_agent_playbook.evals.task.rubric_for_task` (the eval-task compiler)
and :mod:`coding_agent_playbook.commands.metrics` (the standalone gate) build
their checks through here, so the two consumers never drift.

Living in the ``evaluators`` layer keeps ``commands`` from importing ``evals``
just for the shared default thresholds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.check import Check
    from coding_agent_playbook.evaluators.types import MetricConfig

#: Per-metric default grading policy. The ``Check`` layer carries the policy on
#: the *check*, not the metric, so :func:`metric_check` falls back to these when
#: ``config`` has no override for a metric.
#:
#: ``(warn, fail, max_worsening)`` as **0-1 cutoffs on the normalized score**
#: (higher = better): a scope ``warn``\ s when its score drops below ``warn`` and
#: ``fail``\ s when it drops below ``fail``; ``None`` means "no bound at that
#: stage". Because the score is already direction-normalized, the cutoffs no
#: longer carry the metric's raw units - e.g. CC's raw ``warn=10``/``fail=20``
#: become ``warn=0.5``/``fail=0.25`` under ``RampNormalizer(good=5, bad=20)``,
#: while ``coverage``/``maintainability_index``/``test_pass_rate`` land exactly on
#: their old raw boundaries under Percent/Identity (cov ``80 -> 0.8``, MI ``65 ->
#: 0.65``, tpr ``1.0 -> 1.0``).
METRIC_DEFAULTS: dict[str, tuple[float | None, float | None, float]] = {
    "cyclomatic_complexity": (0.5, 0.25, 0.0),
    "wmc": (None, 0.2, 0.0),
    "lcom4": (0.5, None, 0.0),
    "dit": (0.5, None, 0.0),
    "cbo": (0.5, None, 0.0),
    "maintainability_index": (None, 0.65, 0.0),
    "coverage": (0.8, None, 0.0),
    "test_pass_rate": (None, 1.0, 0.0),
}


def metric_check(name: str, config: MetricConfig) -> Check | None:
    """Build the metric-backed :class:`Check` for ``name`` under ``config``.

    Resolves the metric via
    :func:`~coding_agent_playbook.evaluators.metric.get_metric` (``None`` when the
    name is unknown, so the caller skips it the way the eval-task compiler does).
    The absolute warn/fail bounds and regression tolerance come from ``config``'s
    per-metric override when present, else the metric's ported default
    (:data:`METRIC_DEFAULTS`) so the resulting check grades exactly as the retired
    ``grade()``'s ``resolve_policy`` did. ``config.mode`` picks the check family:
    ``"regression"`` → :class:`~coding_agent_playbook.evaluators.check.NonRegressionCheck`,
    ``"absolute"``/``"both"`` →
    :class:`~coding_agent_playbook.evaluators.check.ThresholdCheck` (``mode="both"``
    lets a regression fail before the absolute bound, matching ``grade()``'s
    ``_decide``).
    """
    from coding_agent_playbook.evaluators.check import (
        NonRegressionCheck,
        ThresholdCheck,
    )
    from coding_agent_playbook.evaluators.metric import get_metric

    try:
        metric = get_metric(name)
    except KeyError:
        # Unknown names are surfaced by the validator; skip here so the compiler
        # never raises on an otherwise-loadable task.
        return None

    default_warn, default_fail, default_worsening = METRIC_DEFAULTS.get(name, (None, None, 0.0))
    absolute = config.thresholds.get(name)
    warn = absolute.warn if absolute is not None else default_warn
    fail = absolute.fail if absolute is not None else default_fail
    regression = config.regression.get(name)
    max_worsening = regression.max_worsening if regression is not None else default_worsening
    weight = config.weights.get(name, 0.0)

    if config.mode == "regression":
        return NonRegressionCheck(
            metric,
            max_worsening=max_worsening,
            warn=warn,
            fail=fail,
            weight=weight,
            required=True,
        )
    # "absolute" or "both": a ThresholdCheck whose mode flags whether a baseline
    # regression also gates (only under "both").
    return ThresholdCheck(
        metric,
        warn=warn,
        fail=fail,
        weight=weight,
        required=True,
        mode=config.mode,
    )


__all__ = ["METRIC_DEFAULTS", "metric_check"]
