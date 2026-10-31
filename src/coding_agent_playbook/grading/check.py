"""The ``Check`` ABC + the deterministic metric-backed checks.

The ``Check`` layer is the "grade" stage of the
:class:`~coding_agent_playbook.grading.metric.Metric` (measure) ->
:class:`Check` (grade) -> ``Rubric`` (aggregate) stack. A :class:`Metric`
produces raw
:class:`~coding_agent_playbook.grading.types.Measurement` rows; a :class:`Check`
turns those rows (or, for file/judge checks, ``ctx``) into one
:class:`~coding_agent_playbook.grading.types.CheckResult` carrying the per-scope
:class:`~coding_agent_playbook.grading.types.ScopeDetail` rows.

This module holds the **deterministic, metric-backed checks**
(:class:`ThresholdCheck`, :class:`NonRegressionCheck`); the file checks live in
:mod:`coding_agent_playbook.evals.checks.files`. The per-scope decision here
(``to_score``/``_decide``/``_absolute_level``/``_regressed``) is the canonical
deterministic grading logic.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from coding_agent_playbook.grading.scope import CostTier, Determinism
from coding_agent_playbook.grading.types import (
    AbsoluteThreshold,
    CheckResult,
    RegressionPolicy,
    ScopeDetail,
)

if TYPE_CHECKING:
    from coding_agent_playbook.grading.metric import Metric
    from coding_agent_playbook.grading.types import (
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
# These three module-private helpers (``_decide``, ``_absolute_level``,
# ``_regressed``) are the single home for the per-scope verdict the metric-backed
# checks share. Since C3 they operate **entirely on the normalized ``0-1`` score**
# (higher = always better): the metric's :class:`Normalizer` already folded in its
# native direction, so there is no per-direction branch and the warn/fail
# bounds are ``0-1`` cutoffs on the score. A scope breaches a bound when its score
# drops *strictly below* it (so a score landing exactly on a cutoff is still ok).
# --------------------------------------------------------------------------- #


def _absolute_level(
    score: float,
    absolute: AbsoluteThreshold,
) -> tuple[Level, float | None]:
    """Absolute warn/fail level + the deciding ``0-1`` cutoff for a normalized score.

    Higher-is-better on the normalized scale: a scope ``fail``\\ s when its
    ``score`` is *strictly below* ``absolute.fail`` and ``warn``\\ s when it is
    *strictly below* ``absolute.warn`` (a score exactly on the cutoff is ``ok``).
    A ``None`` bound skips that level. The returned cutoff is the ``0-1`` bound
    that decided (``None`` for ``ok``).
    """
    if absolute.fail is not None and score < absolute.fail:
        return "fail", absolute.fail
    if absolute.warn is not None and score < absolute.warn:
        return "warn", absolute.warn
    return "ok", None


def _regressed(
    score: float,
    base_score: float | None,
    regression: RegressionPolicy,
) -> bool:
    """Whether the normalized ``score`` worsened vs ``base_score`` beyond tolerance.

    On the ``0-1`` goodness scale a *drop* is a worsening, so
    ``worsening = base_score - score``; the scope regressed iff that exceeds
    ``regression.max_worsening``.
    """
    if base_score is None:
        return False
    worsening = base_score - score
    return worsening > regression.max_worsening


def _decide(
    score: float,
    base_score: float | None,
    absolute: AbsoluteThreshold,
    regression: RegressionPolicy,
    mode: Mode,
) -> tuple[Level, Kind, float | None]:
    """Decide ``(level, kind, cutoff)`` for one normalized scope under ``mode``.

    New scopes (no baseline match) always fall back to absolute (``kind="new"``).
    ``"regression"`` mode regression-grades existing scopes; ``"absolute"`` mode
    ignores the baseline; ``"both"`` lets a regression fail first, then absolute.
    Everything is decided on the ``0-1`` score; the returned ``cutoff`` is the
    deciding ``0-1`` absolute bound (``None`` when a regression decided it).
    """
    is_new = base_score is None

    # New scopes always fall back to absolute (kind="new").
    if is_new:
        level, cutoff = _absolute_level(score, absolute)
        return level, "new", cutoff

    reg_failed = _regressed(score, base_score, regression)
    abs_level, abs_cutoff = _absolute_level(score, absolute)

    if mode == "regression":
        return ("fail", "regression", None) if reg_failed else ("ok", "regression", None)
    if mode == "absolute":
        return abs_level, "absolute", abs_cutoff
    # both: regression takes precedence as a failure, then absolute.
    if reg_failed:
        return "fail", "regression", None
    return abs_level, "absolute", abs_cutoff


class _MetricCheck(Check):
    """Shared base for the deterministic, metric-backed checks (T3).

    Holds the :class:`Metric` instance (so it reads ``metric.name`` for the
    measurement lookup and ``metric.score`` to normalize each raw value to a
    ``0-1`` goodness) plus the grading-side policy - an :class:`AbsoluteThreshold`
    and a :class:`RegressionPolicy` now expressed as ``0-1`` cutoffs - and a
    :attr:`mode`. One parameterized ``grade`` normalizes each scope's value (and
    its baseline) via ``metric.score`` and runs ``_decide`` on the **normalized
    scores**, aggregating the per-scope :class:`ScopeDetail` rows into one
    :class:`CheckResult` (``passed`` = no scope failed; ``score`` = mean of the
    per-scope normalized scores; ``None``/``True`` for zero scopes). Each
    :class:`ScopeDetail` keeps the **raw** ``value``/``baseline`` and carries the
    normalized ``score`` plus the ``0-1`` ``bound`` that decided.

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
        # Tier the check by its metric's cost: a judge-backed metric is JUDGED, an
        # execution metric (needs a runnable project) is EXECUTION, a static one is
        # DETERMINISTIC. The JUDGED tier lets the cost-tiered scheduler short-circuit
        # a judged rubric check when a cheaper required gate already failed.
        if metric.needs_judge:
            self.cost = CostTier.JUDGED
            self.determinism = Determinism.JUDGED
        elif metric.needs_project:
            self.cost = CostTier.EXECUTION
        else:
            self.cost = CostTier.DETERMINISTIC

    def available(self, ctx: EvalContext) -> bool:
        """A judged metric needs its judge; any other was measured by this run's pass, or not."""
        if self.metric.needs_judge:
            return self.metric.available(ctx)
        return self.metric.name in ctx.measured_metrics

    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
        """Grade every candidate scope of ``self.metric`` into one result.

        For each scope the raw ``value`` (and the baseline) is normalized to a
        ``0-1`` goodness via ``self.metric.score``; the verdict is decided on those
        normalized scores, while the emitted :class:`ScopeDetail` keeps the **raw**
        ``value``/``baseline`` and records the normalized ``score`` and the ``0-1``
        ``bound`` that decided.

        A **judge-backed** metric (``needs_judge``) is measured **lazily here** when
        the :class:`MeasurementSet` carries no pre-computed candidate measurement
        for it: the static/execution metrics are pre-measured up front (so this
        fallback never fires for them), but a judged metric's measurement is the
        judge call itself, which must be deferred until the cost-tiered scheduler
        actually grades this JUDGED-tier check — so a cheaper required gate that
        already failed short-circuits it and the judge is never invoked.

        An **execution** metric fails outright when the suite gave no result, or one
        that does not count (``ctx.suite_failure_detail``, :meth:`_failed_suite`).
        """
        failure = ctx.suite_failure_detail
        if self.metric.needs_project and failure is not None:
            return self._failed_suite(failure)
        measurements = self._lazily_measure(ctx, measurements)
        details: list[ScopeDetail] = []
        scores: list[float] = []
        for scope_key, value, base_value in measurements.pairs(self.metric.name):
            score = self.metric.score(value)
            base_score = self.metric.score(base_value) if base_value is not None else None
            level, kind, bound = _decide(
                score,
                base_score,
                self._absolute,
                self._regression,
                self._mode,
            )
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

        return self._build_result(details, scores)

    def _lazily_measure(self, ctx: EvalContext, measurements: MeasurementSet) -> MeasurementSet:
        """For a judge-backed metric with no pre-computed value, measure it now.

        Returns ``measurements`` unchanged for static/execution metrics (always
        pre-measured) and for a judge-backed metric that already has a candidate
        measurement. Otherwise (a judged metric whose value is the judge call) it
        runs ``self.metric.measure(ctx)`` and returns a fresh
        :class:`MeasurementSet` with those values added to the candidate side — so
        the grade below has a scope to decide. ``available`` guarantees the judge
        is present when this fires.
        """
        if not self.metric.needs_judge:
            return measurements
        if any(m.evaluator == self.metric.name for m in measurements.candidate):
            return measurements
        fresh = list(self.metric.measure(ctx))
        return MeasurementSet([*measurements.candidate, *fresh], measurements.baseline)

    def _failed_suite(self, detail: str) -> CheckResult:
        """The failed result of an execution check over a suite with no result that counts.

        Why fail and not grade: a suite with no result left no rows, and zero scopes
        pass vacuously, so an agent's endless test or crashing ``conftest.py`` scored
        green; a suite whose failing tests were skipped scored green the same way.

        Example::

            >>> check._failed_suite("the test suite gave no result: it timed out").detail  # doctest: +SKIP
            'the test suite gave no result: it timed out'
        """
        return CheckResult(
            check_id=self.id,
            passed=False,
            score=0.0,
            weight=self.weight,
            required=self.required,
            determinism=self.determinism,
            cost=self.cost,
            status="run",
            detail=detail,
        )

    def _build_result(self, details: list[ScopeDetail], scores: list[float]) -> CheckResult:
        """Fold per-scope ``details`` + normalized ``scores`` into one result.

        Split out of :meth:`grade` so the lazy-measure path reads cleanly.
        """
        # passed = no scope failed; warns do NOT fail the check (strict is a
        # Rubric-level concern, applied later from the subresult levels).
        passed = not any(d.level == "fail" for d in details)
        # Mean of the per-scope normalized scores; zero scopes => no score,
        # vacuously passed.
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

    Holds the :class:`Metric` and its own ``warn``/``fail`` bounds - now ``0-1``
    cutoffs on the metric's **normalized score** (the grading policy moved off the
    metric). ``min_score=`` is sugar for ``fail=min_score`` (the must-clear
    normalized floor). ``mode`` defaults to ``"absolute"`` but can be ``"both"`` to
    also fail on regression when a baseline is present.
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

    Existing scopes are regression-graded on the **normalized score** (any drop
    beyond ``max_worsening`` fails); **new** scopes (absent from the baseline)
    fall back to the absolute ``0-1`` ``warn``/``fail`` bounds, exactly like
    ``_decide``. The deterministic default ``max_worsening=0.0`` means any drop in
    normalized score fails.
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
