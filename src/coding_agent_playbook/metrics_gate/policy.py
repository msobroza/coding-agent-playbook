"""Shared metric-policy defaults + the metric-backed ``Check`` builder.

The single home for the per-metric default grading policy and the
:func:`metric_check` factory that turns a metric name + a
:class:`~coding_agent_playbook.metrics_gate.config.MetricConfig` into the
metric-backed :class:`~coding_agent_playbook.grading.check.Check`
(:class:`~coding_agent_playbook.grading.check.ThresholdCheck` /
:class:`~coding_agent_playbook.grading.check.NonRegressionCheck`).
:mod:`coding_agent_playbook.commands.metrics` (the standalone static gate) builds
its checks through here from its ``[metrics]`` engine config, so the metric-policy
defaults live in exactly one place.

Living in ``metrics_gate`` rather than ``evals`` keeps ``commands`` from
importing ``evals`` just for the shared default thresholds.

Which metrics a gate run measures is policy too (prK §F.0.3 item 2), so the
ruff-shaped selection (:data:`METRIC_FAMILIES`, :data:`OPT_IN_METRICS`,
:func:`resolve_metric_selection`) lives here beside the defaults; a ``Metric``
carries only measurement descriptors.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from coding_agent_playbook.grading.check import Check
    from coding_agent_playbook.grading.metric import Metric
    from coding_agent_playbook.metrics_gate.config import MetricConfig

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
    # prK §F.1.1: changed lines must be >= 80% executed; max_worsening is moot,
    # since a diff-based metric is never compared with a baseline value.
    "diff_coverage": (None, 0.8, 0.0),
    # prK §F.2.1/§F.3.1: no band by default (non-regression only); file_sloc is
    # regression-exempt, since a score drop can never exceed 1.0.
    "ruff_violations": (None, None, 0.0),
    "file_sloc": (None, None, 1.0),
    "docstring_example": (None, None, 0.0),
    # The standard limit, 15 per function (SonarSource S3776, complexipy's own
    # default): the score is 1.0 up to 15, so fail=1.0 fails a function over it.
    "cognitive_complexity": (None, 1.0, 0.0),
}


def metric_check(name: str, config: MetricConfig) -> Check | None:
    """Build the metric-backed :class:`Check` for ``name`` under ``config``.

    Resolves the metric via
    :func:`~coding_agent_playbook.grading.metric.get_metric` (``None`` when the
    name is unknown, so the caller skips it the way the eval-sample compiler does).
    The absolute warn/fail bounds and regression tolerance come from ``config``'s
    per-metric override when present, else the metric's ported default
    (:data:`METRIC_DEFAULTS`) so the resulting check grades exactly as the retired
    ``grade()``'s ``resolve_policy`` did. ``config.mode`` picks the check family:
    ``"regression"`` → :class:`~coding_agent_playbook.grading.check.NonRegressionCheck`,
    ``"absolute"``/``"both"`` →
    :class:`~coding_agent_playbook.grading.check.ThresholdCheck` (``mode="both"``
    lets a regression fail before the absolute bound, matching ``grade()``'s
    ``_decide``).
    """
    from coding_agent_playbook.grading.check import (
        NonRegressionCheck,
        ThresholdCheck,
    )
    from coding_agent_playbook.grading.metric import get_metric

    try:
        metric = get_metric(name)
    except KeyError:
        # Unknown names are surfaced by the validator; skip here so the compiler
        # never raises on an otherwise-loadable sample.
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


#: Selection families (prK §F.0.3 item 2): a ``select`` / ``extend_select`` name
#: that stands for its members. ``ruff_violations`` sits in two families because
#: it measures per ruff code family; a Stop stage keeps only its own scope keys.
#: Members no step has registered yet are skipped, never an error.
METRIC_FAMILIES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "quality": (
            "cyclomatic_complexity",
            "cognitive_complexity",
            "wmc",
            "lcom4",
            "dit",
            "cbo",
            "maintainability_index",
            "file_sloc",
            "ruff_violations",
        ),
        "docstrings": ("ruff_violations", "docstring_example"),
        "testing": ("test_pass_rate", "coverage", "diff_coverage"),
    }
)

#: Metrics enabled only **by name** (prK §F.2.1): never by default and never
#: through a family. ``ruff_violations`` is available wherever ruff is on PATH
#: (``cognitive_complexity`` wherever complexipy is), so default-selecting it
#: would change every consumer's pre-commit results on upgrade.
OPT_IN_METRICS: Final = frozenset(
    {"ruff_violations", "cognitive_complexity", "file_sloc", "docstring_example"}
)


def resolve_metric_selection(
    available: Sequence[Metric],
    *,
    select: Iterable[str] | None = None,
    extend_select: Iterable[str] = (),
    ignore: Iterable[str] = (),
    run_tests: bool = False,
) -> list[Metric]:
    """The metrics of ``available`` a gate run measures, in ``available``'s order.

    ``select=None`` means the default: every static metric except
    :data:`OPT_IN_METRICS`, plus the non-opt-in execution metrics under
    ``run_tests``. A ``select`` list replaces the default, ``extend_select``
    adds and ``ignore`` removes. A family name expands to its non-opt-in members
    (in ``ignore``: to all of them), so an opt-in metric is enabled only by name.

    Raises ``ValueError`` for a name that is neither a family nor a metric
    (registered or a family member), and for an execution metric selected
    without ``run_tests``: running tests is never implied.

    Example::

        >>> [m.name for m in resolve_metric_selection(all_metrics(), select=["wmc"])]
        ['wmc']
    """
    select_names = None if select is None else tuple(select)
    extend_names, ignore_names = tuple(extend_select), tuple(ignore)
    _check_known([*(select_names or ()), *extend_names, *ignore_names], available)
    if select_names is None:
        chosen = {m.name for m in available if _in_default(m, run_tests=run_tests)}
    else:
        chosen = _expand(select_names)
    chosen = (chosen | _expand(extend_names)) - _expand(ignore_names, opt_ins=True)
    picked = [metric for metric in available if metric.name in chosen]
    _check_runnable(picked, run_tests=run_tests)
    return picked


def stop_stage_selection(
    available: Sequence[Metric],
    config: MetricConfig,
    *,
    families: Iterable[str] = ("quality", "docstrings"),
    by_name: Iterable[str] = ("ruff_violations",),
) -> tuple[list[Metric], frozenset[str]]:
    """What the Stop stages' one shared gate pass measures, and what ``[metrics]`` itself selects.

    The pass measures the consumer's selection restricted to ``families``, plus
    ``by_name`` (prK §F.2.2: the stages always count ruff); never an execution
    metric. The second value is the consumer's own selection (suite metrics
    included): a stage is deny-eligible on a metric only when it is in there,
    so a hook is never stricter than its pre-commit twin. Raises ``ValueError``
    for an unknown name in ``[metrics]``.

    Example::

        >>> picked, own = stop_stage_selection(static_metrics(), MetricConfig())
        >>> "ruff_violations" in [m.name for m in picked], "ruff_violations" in own
        (True, False)
    """
    own = resolve_metric_selection(
        available,
        select=config.select,
        extend_select=config.extend_select,
        ignore=config.ignore,
        run_tests=True,
    )
    names = frozenset(metric.name for metric in own)
    members = {member for family in families for member in METRIC_FAMILIES.get(family, ())}
    wanted = (names & members) | set(by_name)
    return [m for m in available if m.name in wanted and not m.needs_project], names


def _in_default(metric: Metric, *, run_tests: bool) -> bool:
    if metric.name in OPT_IN_METRICS:
        return False
    return run_tests or not metric.needs_project


def _expand(names: Iterable[str], *, opt_ins: bool = False) -> set[str]:
    """Metric names for ``names``: a family becomes its (non-opt-in) members."""
    out: set[str] = set()
    for name in names:
        members = METRIC_FAMILIES.get(name)
        if members is None:
            out.add(name)
        else:
            out.update(m for m in members if opt_ins or m not in OPT_IN_METRICS)
    return out


def _check_known(names: Iterable[str], available: Sequence[Metric]) -> None:
    registered = {metric.name for metric in available} | set(METRIC_FAMILIES)
    members = {member for family in METRIC_FAMILIES.values() for member in family}
    unknown = [name for name in names if name not in registered | members]
    if unknown:
        valid = ", ".join(sorted(registered))
        raise ValueError(f"unknown metric or family {unknown[0]!r}; expected one of: {valid}")


def _check_runnable(picked: Sequence[Metric], *, run_tests: bool) -> None:
    execution = [metric.name for metric in picked if metric.needs_project]
    if execution and not run_tests:
        raise ValueError(
            f"execution metric(s) {', '.join(execution)} selected without --run-tests; "
            "running the suite is never implied"
        )


__all__ = [
    "METRIC_DEFAULTS",
    "METRIC_FAMILIES",
    "OPT_IN_METRICS",
    "metric_check",
    "resolve_metric_selection",
    "stop_stage_selection",
]
