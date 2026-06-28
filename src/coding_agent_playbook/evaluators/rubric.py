"""The ``Rubric`` aggregator + the ``Rubric``-is-a-``Metric`` composition (T4a/T4b).

:class:`Rubric` is the "aggregate" layer of the clean-slate
:class:`~coding_agent_playbook.evaluators.metric.Metric` (measure) ->
:class:`~coding_agent_playbook.evaluators.check.Check` (grade) -> ``Rubric``
(aggregate) split. It holds an ordered list of checks, runs them through the
cost-tiered :func:`~coding_agent_playbook.evaluators.scheduler.schedule` (T4b -
cheapest tier first, results in **authored order**), and folds their
:class:`~coding_agent_playbook.evaluators.types.CheckResult` rows into one
:class:`~coding_agent_playbook.evaluators.types.EvaluationReport` carrying the
gate / weighted-composite / strict verdict. :meth:`evaluate` defaults to
``fail_fast=False`` so the report stays
complete (every available check runs - behaviour-identical to the pre-scheduler
T4a loop); a caller may opt into ``fail_fast=True`` (gate-lost short-circuit) and
``max_workers > 1`` (per-tier concurrency).

``Rubric`` is **also** a :class:`Metric`: a rubric nested inside a parent rubric
exposes its composite as one MODULE-scope
:class:`~coding_agent_playbook.evaluators.types.Measurement` (keyed on the
rubric's ``name``), which a parent
:class:`~coding_agent_playbook.evaluators.check.ThresholdCheck` then grades. The
``Metric`` half (:meth:`measure`) self-builds a
:class:`~coding_agent_playbook.evaluators.check.MeasurementSet` from the additive
``EvalContext.candidate_measurements`` / ``baseline_measurements`` fields, guards
against a re-entrant self-measure (raising :class:`ValueError`), and memoizes the
result per ``ctx`` so a rubric measured twice in one context is not rebuilt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.check import MeasurementSet
from coding_agent_playbook.evaluators.metric import Metric
from coding_agent_playbook.evaluators.normalizer import Identity
from coding_agent_playbook.evaluators.scheduler import schedule
from coding_agent_playbook.evaluators.scope import CostTier, Scope
from coding_agent_playbook.evaluators.types import (
    EvaluationReport,
    Measurement,
    ScopeDetail,
)

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.check import Check
    from coding_agent_playbook.evaluators.types import CheckResult, EvalContext


class Rubric(Metric):
    """An ordered set of checks aggregated into one report; also a :class:`Metric`.

    The ``Metric`` descriptors are fixed by construction: :attr:`scope` is
    ``MODULE`` (a rubric grades a whole unit), :attr:`normalizer` is
    :class:`~coding_agent_playbook.evaluators.normalizer.Identity` (its composite
    is already a ``0-1`` SCORE where higher is better), :attr:`requires` is
    ``None``, and :attr:`needs_project` is ``True`` iff any child check is
    execution-tier (so a parent rubric / scheduler knows the whole rubric needs a
    runnable project). :attr:`name` (default ``"rubric"``) is the metric name a
    parent :class:`~coding_agent_playbook.evaluators.check.ThresholdCheck` looks up.
    """

    scope = Scope.MODULE
    normalizer = Identity()
    requires = None

    #: The code-defined criteria a subclass declares so :meth:`define` (and the
    #: named-rubric registry) can build it from the class alone. Each pair is
    #: ``(criterion, weight)``; the engine ships no subclasses (named rubrics are
    #: an out-of-tree extension point - see
    #: :mod:`coding_agent_playbook.evaluators.rubrics`).
    CRITERIA: tuple[tuple[str, float], ...] = ()

    def __init__(self, checks: list[Check], *, name: str = "rubric") -> None:
        self.checks = checks
        self.name = name
        # The rubric needs a runnable project exactly when one of its checks is
        # execution-tier; a parent rubric reads this to schedule/gate correctly.
        self.needs_project = any(c.cost == CostTier.EXECUTION for c in checks)
        # Re-entrancy guard for measure() (a self-referential rubric) + a per-ctx
        # memo keyed on id(ctx) so a rubric measured twice in one ctx is reused.
        self._measuring = False
        self._measure_cache: dict[int, list[Measurement]] = {}

    # ------------------------------------------------------------------ #
    # Code-defined constructors: of() builds from explicit pairs, define()
    # builds from the class's CRITERIA. Both produce a JudgeCheck per criterion.
    # ------------------------------------------------------------------ #

    @classmethod
    def of(
        cls,
        *criteria: tuple[str, float],
        name: str = "rubric",
        threshold: float = 0.5,
        normalize: bool = True,
    ) -> Rubric:
        """Build a :class:`Rubric` of :class:`JudgeCheck`\\ s from ``(criterion, weight)`` pairs.

        Each pair becomes a non-gating
        :class:`~coding_agent_playbook.evaluators.checks.judged.JudgeCheck`
        (``required=False`` - judged criteria feed the composite, they do not
        gate) carrying ``threshold`` and its weight. When ``normalize`` (the
        default) and there is at least one pair, the weights are scaled to sum
        ``1.0`` - parity with the TOML ``[rubric].weights`` sum rule; the all-zero
        case is left untouched (no divide-by-zero). The built rubric is a plain
        :class:`Rubric` instance named ``name``.
        """
        from coding_agent_playbook.evaluators.checks.judged import JudgeCheck

        labels = [c for c, _ in criteria]
        weights = [w for _, w in criteria]
        if normalize and weights:
            total = float(sum(weights))
            if total > 0:
                weights = [w / total for w in weights]
        checks: list[Check] = [
            JudgeCheck(label, threshold=threshold, weight=weight, required=False)
            for label, weight in zip(labels, weights, strict=True)
        ]
        return cls(checks, name=name)

    @classmethod
    def define(cls, **kw: object) -> Rubric:
        """Build this subclass from its :attr:`CRITERIA`, named after the class.

        A thin wrapper over :meth:`of` that supplies the class-level
        :attr:`CRITERIA` and defaults the rubric ``name`` to ``cls.__name__``.
        The remaining keyword arguments (``threshold``, ``normalize``) flow
        through to :meth:`of`. This is the entry point the named-rubric registry
        (:func:`coding_agent_playbook.evaluators.rubrics.get_rubric`) calls.
        """
        return cls.of(*cls.CRITERIA, name=cls.__name__, **kw)  # type: ignore[arg-type]

    def available(self, ctx: EvalContext) -> bool:
        """Whether this rubric can run in ``ctx`` (the :class:`Metric` half's gate).

        A rubric does not parse a ``module`` of its own (its checks do their own
        ctx-slot gating), so - unlike the default :meth:`Metric.available` - it is
        **not** gated on ``ctx.module``. The only hard requirement is a runnable
        project when a child check is execution-tier (``needs_project``); otherwise
        a nested rubric is always available and its child checks decide per-check.
        """
        if self.needs_project:
            return ctx.project is not None
        return True

    # ------------------------------------------------------------------ #
    # The aggregate half: run every check, fold into one report.
    # ------------------------------------------------------------------ #

    def evaluate(
        self,
        ctx: EvalContext,
        measurements: MeasurementSet,
        *,
        strict: bool = False,
        fail_fast: bool = False,
        max_workers: int = 1,
    ) -> EvaluationReport:
        """Run the checks via the cost-tiered scheduler and fold them into one report.

        Delegates the run to
        :func:`~coding_agent_playbook.evaluators.scheduler.schedule` (``op="and"``,
        results always in authored order): checks execute cheapest-tier-first, and
        an unavailable check (e.g. a
        :class:`~coding_agent_playbook.evaluators.checks.judged.JudgeCheck` with no
        judge) is recorded as a ``status="skipped"`` placeholder that never sinks
        the gate.

        ``fail_fast`` (default ``False``) toggles the scheduler's short-circuit:
        the default leaves it **off** so the report stays complete - every
        available check runs, identical to the pre-scheduler behaviour. Only a
        caller opting into ``fail_fast=True`` lets a lost gate skip the remaining
        costlier tiers (so a failing deterministic check can spare an LLM call).
        ``max_workers > 1`` runs each tier's checks concurrently; the default
        ``1`` is sequential/reproducible (what CI uses).

        The gate is ``all`` required *run* checks passing, plus - under ``strict``
        - no required run check carrying a ``warn`` leaf. The composite is the
        weight-normalized mean of the run checks' scores (``None`` when no run
        check carries weight). ``findings`` flattens the leaf :class:`ScopeDetail`
        rows (transitional, until the destructive cutover).
        """
        results = schedule(
            self.checks,
            ctx,
            measurements,
            op="and",
            short_circuit=fail_fast,
            max_workers=max_workers,
        )

        passed = self._gate(results, strict=strict)
        composite = self._composite(results)
        warn_count, fail_count = self._level_counts(results)
        findings = self._flatten_findings(results)

        return EvaluationReport(
            findings=findings,
            warn_count=warn_count,
            fail_count=fail_count,
            composite=composite,
            passed=passed,
            checks=results,
        )

    @staticmethod
    def _gate(results: list[CheckResult], *, strict: bool) -> bool:
        """Required *run* checks must pass; under ``strict`` none may carry a warn.

        Skipped checks are ignored by the gate (a dormant judged check does not
        fail it). ``strict`` additionally fails the gate when any required, run
        check has a ``warn``-level :class:`ScopeDetail` subresult.
        """
        run_required = [r for r in results if r.required and r.status == "run"]
        if not all(r.passed for r in run_required):
            return False
        return not (strict and any(_has_warn(r) for r in run_required))

    @staticmethod
    def _composite(results: list[CheckResult]) -> float | None:
        """Weight-normalized mean over run checks with ``weight > 0`` and a score.

        The sum of ``weight * score`` over the total weight, or ``None`` when no
        such check contributes.
        """
        weighted = [
            (r.weight, r.score)
            for r in results
            if r.status == "run" and r.weight > 0 and r.score is not None
        ]
        total_weight = sum(weight for weight, _ in weighted)
        if total_weight <= 0:
            return None
        return sum(weight * score for weight, score in weighted if score is not None) / total_weight

    @staticmethod
    def _level_counts(results: list[CheckResult]) -> tuple[int, int]:
        """Count ``warn``/``fail`` :class:`ScopeDetail` leaves across run checks."""
        warn = 0
        fail = 0
        for result in results:
            if result.status != "run":
                continue
            for sub in result.subresults:
                if isinstance(sub, ScopeDetail):
                    if sub.level == "warn":
                        warn += 1
                    elif sub.level == "fail":
                        fail += 1
        return warn, fail

    @staticmethod
    def _flatten_findings(results: list[CheckResult]) -> list[ScopeDetail]:
        """Flatten the leaf :class:`ScopeDetail` rows from every run check.

        The ``EvaluationReport.findings`` list carries the flat per-scope rows
        renderers read. Only direct ``ScopeDetail`` leaves are collected (nested
        ``CheckResult`` subresults - from a composing check - are not descended
        here).
        """
        findings: list[ScopeDetail] = []
        for result in results:
            if result.status != "run":
                continue
            for sub in result.subresults:
                if isinstance(sub, ScopeDetail):
                    findings.append(sub)
        return findings

    # ------------------------------------------------------------------ #
    # The measure half: a Rubric is a Metric (so rubrics nest).
    # ------------------------------------------------------------------ #

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        """Evaluate self and surface the composite as one MODULE measurement.

        Self-builds a :class:`MeasurementSet` from ``ctx.candidate_measurements``
        (and the optional ``ctx.baseline_measurements``), runs :meth:`evaluate`,
        and returns a single :class:`Measurement` (``evaluator`` /``scope_key`` =
        :attr:`name`) whose value is the report's composite - or ``float(passed)``
        when the composite is ``None`` (no weighted checks). Guards against a
        re-entrant self-measure (a rubric grading itself) with a
        :class:`ValueError`, and memoizes per ``ctx`` (keyed on ``id(ctx)``).
        """
        key = id(ctx)
        cached = self._measure_cache.get(key)
        if cached is not None:
            return cached
        if self._measuring:
            raise ValueError(
                f"re-entrant measure of rubric {self.name!r}: a rubric cannot "
                "grade itself (cycle in the rubric graph)"
            )
        self._measuring = True
        try:
            ms = MeasurementSet(ctx.candidate_measurements or [], ctx.baseline_measurements)
            report = self.evaluate(ctx, ms)
            value = report.composite if report.composite is not None else float(report.passed)
            out = [Measurement(evaluator=self.name, scope_key=self.name, value=value)]
        finally:
            self._measuring = False
        self._measure_cache[key] = out
        return out


def _has_warn(result: CheckResult) -> bool:
    """Whether ``result`` carries any ``warn``-level :class:`ScopeDetail` leaf."""
    return any(isinstance(s, ScopeDetail) and s.level == "warn" for s in result.subresults)


__all__ = ["Rubric"]
