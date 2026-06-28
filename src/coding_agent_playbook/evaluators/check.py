"""The ``Check`` ABC + the deterministic metric-backed checks.

The ``Check`` layer is the "grade" stage of the
:class:`~coding_agent_playbook.evaluators.metric.Metric` (measure) ->
:class:`Check` (grade) -> ``Rubric`` (aggregate) stack. A :class:`Metric`
produces raw
:class:`~coding_agent_playbook.evaluators.types.Measurement` rows; a :class:`Check`
turns those rows (or, for file/judge checks, ``ctx``) into one
:class:`~coding_agent_playbook.evaluators.types.CheckResult` carrying the per-scope
:class:`~coding_agent_playbook.evaluators.types.ScopeDetail` rows.

This module holds the **deterministic, metric-backed checks**
(:class:`ThresholdCheck`, :class:`NonRegressionCheck`); the file checks live in
:mod:`coding_agent_playbook.evaluators.checks.files`. The per-scope decision here
(``to_score``/``_decide``/``_absolute_level``/``_regressed``) is the canonical
deterministic grading logic.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.scope import CostTier, Determinism
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    CheckResult,
    RegressionPolicy,
    ScopeDetail,
)

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.metric import Metric
    from coding_agent_playbook.evaluators.types import (
        EvalContext,
        Kind,
        Level,
        Measurement,
        Mode,
    )

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slug(text: str, *, fallback: str = "criterion") -> str:
    """Lowercase ``text`` to a hyphen-separated slug for a stable check id.

    Collapses every run of non-alphanumeric characters to a single ``-`` and
    strips leading/trailing hyphens; returns ``fallback`` when the input slugs to
    the empty string (e.g. ``""`` or ``"???"``) so the resulting ``<prefix>:<slug>``
    id is always well-formed. This is the single home for the slug helper the
    ``Check`` families share (the file checks and the judged check both import it).
    """
    cleaned = _SLUG_NON_ALNUM.sub("-", text.lower()).strip("-")
    return cleaned or fallback


class MeasurementSet:
    """A candidate measurement list paired with an optional baseline.

    Wraps the two measurement lists a deterministic check grades over and
    provides :meth:`pairs`, which indexes both lists by
    ``(evaluator == metric_name, scope_key)`` the way the deterministic checks
    consume them: it iterates the **candidate** scopes for one metric and attaches
    the matching baseline value
    (``None`` for a new scope), so removed baseline-only scopes are ignored.
    """

    def __init__(
        self,
        candidate: list[Measurement],
        baseline: list[Measurement] | None = None,
    ) -> None:
        self.candidate = candidate
        self.baseline = baseline

    def pairs(self, metric_name: str) -> list[tuple[str, float, float | None]]:
        """``(scope_key, value, baseline_value | None)`` for ``metric_name``.

        Mirrors ``grade()``: the baseline is indexed by
        ``(evaluator, scope_key)`` and a candidate scope with no baseline match
        gets ``None`` (a *new* scope). Baseline-only scopes (removed in the
        candidate) never appear - only candidate scopes are iterated.
        """
        baseline_index: dict[tuple[str, str], float] = {
            (m.evaluator, m.scope_key): m.value
            for m in (self.baseline or [])
            if m.evaluator == metric_name
        }
        out: list[tuple[str, float, float | None]] = []
        for m in self.candidate:
            if m.evaluator != metric_name:
                continue
            base = baseline_index.get((m.evaluator, m.scope_key))
            out.append((m.scope_key, m.value, base))
        return out


class Check(ABC):
    """A grader: turns measurements (or ``ctx``) into one :class:`CheckResult`.

    Class attrs :attr:`cost` (cheapest-first scheduling) and
    :attr:`determinism` (routing) describe the check; instance attrs :attr:`id`,
    :attr:`weight`, and :attr:`required` describe this concrete check. A
    ``Rubric`` schedules checks cheapest-first and applies strict-mode by
    inspecting per-scope levels in the result's ``subresults`` - the check itself
    does **not** know about strict (a warn never fails the check here).
    """

    cost: CostTier
    determinism: Determinism

    id: str
    weight: float
    required: bool

    def available(self, ctx: EvalContext) -> bool:
        """True when this check can run in ``ctx`` (default: always)."""
        return True

    @abstractmethod
    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
        """Grade into one :class:`CheckResult` (file/judge checks ignore ``measurements``)."""


# --------------------------------------------------------------------------- #
# Per-scope decision - the canonical deterministic grading logic.
#
# These four module-private helpers (``_to_score``, ``_decide``,
# ``_absolute_level``, ``_regressed``) are the single home for the per-scope
# verdict the metric-backed checks share. They read ``higher_is_worse`` from the
# ``Metric``. The boundary rules (inclusive on the higher-is-worse side, strict on
# the higher-is-better side) live only here.
# --------------------------------------------------------------------------- #


def _to_score(
    value: float,
    higher_is_worse: bool,
    absolute: AbsoluteThreshold,
) -> float:
    """Normalize a NUMERIC value to ``0-1`` (higher = better).

    Ramps around the absolute warn/fail bounds: ``1.0`` at/under ``warn`` and
    ``0.0`` at/over ``fail`` (linear between) when ``higher_is_worse``; the ramp
    inverts when larger is better. With no bounds the score is ``1.0``. The
    metric-backed checks only grade NUMERIC metrics, so there is no SCORE/BOOL
    identity branch here (BOOL file checks set their score directly from the
    predicate).
    """
    warn = absolute.warn
    fail = absolute.fail
    if warn is None or fail is None or warn == fail:
        return 1.0

    if higher_is_worse:
        # warn is the good floor, fail the bad ceiling.
        if value <= warn:
            return 1.0
        if value >= fail:
            return 0.0
        return (fail - value) / (fail - warn)
    # higher is better: warn is the good target, fail the bad floor.
    if value >= warn:
        return 1.0
    if value <= fail:
        return 0.0
    return (value - fail) / (warn - fail)


def _absolute_level(
    value: float,
    higher_is_worse: bool,
    absolute: AbsoluteThreshold,
) -> tuple[Level, float | None]:
    """Absolute warn/fail level + the deciding bound - copy of ``_absolute_level``.

    Inclusive at the bound on the higher-is-worse side (``value >= bound``
    breaches: a CC of exactly ``20`` fails) and strict on the higher-is-better
    side (``value < bound`` breaches: coverage of exactly ``80`` is ``ok``).
    """
    if higher_is_worse:
        if absolute.fail is not None and value >= absolute.fail:
            return "fail", absolute.fail
        if absolute.warn is not None and value >= absolute.warn:
            return "warn", absolute.warn
        return "ok", None
    # higher is better: breach when the value drops *strictly below* the bound.
    if absolute.fail is not None and value < absolute.fail:
        return "fail", absolute.fail
    if absolute.warn is not None and value < absolute.warn:
        return "warn", absolute.warn
    return "ok", None


def _regressed(
    value: float,
    base_value: float | None,
    higher_is_worse: bool,
    regression: RegressionPolicy,
) -> bool:
    """Whether ``value`` worsened vs ``base_value`` beyond tolerance - copy of ``_regressed``."""
    if base_value is None:
        return False
    worsening = (value - base_value) if higher_is_worse else (base_value - value)
    return worsening > regression.max_worsening


def _decide(
    value: float,
    base_value: float | None,
    higher_is_worse: bool,
    absolute: AbsoluteThreshold,
    regression: RegressionPolicy,
    mode: Mode,
) -> tuple[Level, Kind, float | None]:
    """Decide ``(level, kind, bound)`` for one scope under ``mode`` - copy of ``_decide``.

    New scopes (no baseline match) always fall back to absolute (``kind="new"``).
    ``"regression"`` mode regression-grades existing scopes; ``"absolute"`` mode
    ignores the baseline; ``"both"`` lets a regression fail first, then absolute.
    """
    is_new = base_value is None

    # New scopes always fall back to absolute (kind="new").
    if is_new:
        level, bound = _absolute_level(value, higher_is_worse, absolute)
        return level, "new", bound

    reg_failed = _regressed(value, base_value, higher_is_worse, regression)
    abs_level, abs_bound = _absolute_level(value, higher_is_worse, absolute)

    if mode == "regression":
        return ("fail", "regression", None) if reg_failed else ("ok", "regression", None)
    if mode == "absolute":
        return abs_level, "absolute", abs_bound
    # both: regression takes precedence as a failure, then absolute.
    if reg_failed:
        return "fail", "regression", None
    return abs_level, "absolute", abs_bound


class _MetricCheck(Check):
    """Shared base for the deterministic, metric-backed checks (T3).

    Holds the :class:`Metric` instance (so it reads ``metric.name`` for the
    measurement lookup and ``metric.higher_is_worse`` for the comparison
    direction) plus the grading-side policy - an :class:`AbsoluteThreshold`, a
    :class:`RegressionPolicy`, and a :attr:`mode`. One parameterized ``grade``
    runs ``_decide`` per scope, aggregating the per-scope :class:`ScopeDetail`
    rows into one :class:`CheckResult` (``passed`` = no scope failed; ``score`` =
    mean of the per-scope ramps; ``None``/``True`` for zero scopes).

    :attr:`cost` is derived from ``metric.needs_project`` (an execution metric is
    EXECUTION-tier, a static one DETERMINISTIC); :attr:`determinism` is
    DETERMINISTIC.
    """

    determinism = Determinism.DETERMINISTIC

    #: Subclasses set this prefix for the stable ``<prefix>:<metric.name>`` id.
    _id_prefix: str

    def __init__(
        self,
        metric: Metric,
        *,
        absolute: AbsoluteThreshold,
        regression: RegressionPolicy,
        mode: Mode,
        weight: float,
        required: bool,
    ) -> None:
        self.metric = metric
        self._absolute = absolute
        self._regression = regression
        self._mode: Mode = mode
        self.weight = weight
        self.required = required
        self.id = f"{self._id_prefix}:{metric.name}"
        # An execution metric (needs a runnable project) is EXECUTION-tier; a
        # static one is DETERMINISTIC. Mirrors ``static_metrics()``'s discriminator.
        self.cost = CostTier.EXECUTION if metric.needs_project else CostTier.DETERMINISTIC

    def available(self, ctx: EvalContext) -> bool:
        """Delegate to the underlying metric (dependency + ctx-slot gating)."""
        return self.metric.available(ctx)

    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
        """Grade every candidate scope of ``self.metric`` into one result."""
        higher_is_worse = self.metric.higher_is_worse
        details: list[ScopeDetail] = []
        scores: list[float] = []
        for scope_key, value, base_value in measurements.pairs(self.metric.name):
            level, kind, bound = _decide(
                value,
                base_value,
                higher_is_worse,
                self._absolute,
                self._regression,
                self._mode,
            )
            score = _to_score(value, higher_is_worse, self._absolute)
            scores.append(score)
            details.append(
                ScopeDetail(
                    evaluator=self.metric.name,
                    scope_key=scope_key,
                    value=value,
                    baseline=base_value,
                    bound=bound,
                    score=score,
                    level=level,
                    kind=kind,
                )
            )

        # passed = no scope failed; warns do NOT fail the check (strict is a
        # Rubric-level concern, applied later from the subresult levels).
        passed = not any(d.level == "fail" for d in details)
        # Mean of the per-scope ramps; zero scopes => no score, vacuously passed.
        composite = sum(scores) / len(scores) if scores else None
        return CheckResult(
            check_id=self.id,
            passed=passed,
            score=composite,
            weight=self.weight,
            required=self.required,
            determinism=self.determinism,
            cost=self.cost,
            status="run",
            subresults=tuple(details),
        )


class ThresholdCheck(_MetricCheck):
    """Grade a metric's scopes against absolute warn/fail bounds (``mode="absolute"``).

    Holds the :class:`Metric` and its own ``warn``/``fail`` bounds (the grading
    policy moved off the metric). ``min_score=`` is sugar for ``fail=min_score``
    (the must-clear floor). ``mode`` defaults to ``"absolute"`` but can be
    ``"both"`` to also fail on regression when a baseline is present.
    """

    _id_prefix = "threshold"

    def __init__(
        self,
        metric: Metric,
        *,
        warn: float | None = None,
        fail: float | None = None,
        min_score: float | None = None,
        weight: float = 0.0,
        required: bool = True,
        mode: Mode = "absolute",
    ) -> None:
        if min_score is not None:
            fail = min_score
        super().__init__(
            metric,
            absolute=AbsoluteThreshold(warn=warn, fail=fail),
            regression=RegressionPolicy(max_worsening=0.0),
            mode=mode,
            weight=weight,
            required=required,
        )


class NonRegressionCheck(_MetricCheck):
    """Grade a metric's scopes for non-regression vs baseline (``mode="regression"``).

    Existing scopes are regression-graded (any worsening beyond ``max_worsening``
    fails); **new** scopes (absent from the baseline) fall back to the absolute
    ``warn``/``fail`` bounds, exactly like ``grade()``'s ``_decide``. The
    deterministic default ``max_worsening=0.0`` means any worsening fails.
    """

    _id_prefix = "nonreg"

    def __init__(
        self,
        metric: Metric,
        *,
        max_worsening: float = 0.0,
        warn: float | None = None,
        fail: float | None = None,
        weight: float = 0.0,
        required: bool = True,
    ) -> None:
        super().__init__(
            metric,
            absolute=AbsoluteThreshold(warn=warn, fail=fail),
            regression=RegressionPolicy(max_worsening=max_worsening),
            mode="regression",
            weight=weight,
            required=required,
        )


__all__ = [
    "Check",
    "MeasurementSet",
    "NonRegressionCheck",
    "ThresholdCheck",
    "slug",
]
