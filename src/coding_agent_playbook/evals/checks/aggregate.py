"""The across-trial aggregate checks: ``pass@k`` / ``pass^k``.

The first three layers of the eval model grade **one** agent run: ``[gate]``
(deterministic), ``[rubric]`` (judged), and the derived ``[verdict]``. The
``[aggregate]`` layer adds a *fourth* dimension - **reliability across ``k``
runner trials**. The runner runs ``N = max(k)`` trials, collects one
:class:`~coding_agent_playbook.grading.types.TrialResult` per trial, and grades
the compiled aggregate layer over a context carrying them
(:attr:`~coding_agent_playbook.grading.types.EvalContext.trials`).

Each handle is an :class:`AggregateCheck` - itself a
:class:`~coding_agent_playbook.grading.check.Check`, so the boolean composers
(``AllOf``/``AnyOf``/``Not``) and the expression interpreter compose aggregate
handles exactly like gate/rubric handles. An aggregate check does **no agent
work**: it reads the already-run trials, so it is ``DETERMINISTIC`` on both axes.

For a check with parameter ``k`` over ``n`` trials of which ``c`` passed the
selected ``over`` axis (``gate`` / ``rubric`` / ``verdict``), the two estimators
are the standard sampling probabilities:

* **pass@k** - the probability a uniformly-random ``k``-subset of the ``n`` trials
  contains **at least one** success::

      1.0                          if (n - c) < k   (cannot avoid a success)
      1 - C(n - c, k) / C(n, k)    otherwise

* **pass^k** - the probability a uniformly-random ``k``-subset is **all**
  successes::

      0.0                          if c < k   (not enough successes)
      C(c, k) / C(n, k)            otherwise

The ``0-1`` estimate is graded against an absolute ``warn``/``fail`` floor with
the *same* higher-is-better strict-below rule the metric checks use
(:func:`~coding_agent_playbook.grading.check._absolute_level`): a score
*strictly below* ``fail`` fails, *strictly below* ``warn`` warns, exactly-on is
ok. ``passed`` is ``score >= fail`` (no ``fail`` floor ⇒ a pure ``warn`` gate
still passes - a warn never fails a check; strict promotion is a ``Rubric``-level
concern).

``max_worsening`` (a regression tolerance vs *baseline* trials) is **not yet
supported** for the aggregate layer - only the absolute ``warn``/``fail`` path
executes. A ``max_worsening`` present on the binding is accepted by the validator
but ignored here (see the ``# NOTE`` in
:func:`~coding_agent_playbook.evals.checks.aggregate._pass_at_k` callers).
"""

from __future__ import annotations

from math import comb
from typing import TYPE_CHECKING

from coding_agent_playbook.grading.check import Check
from coding_agent_playbook.grading.check_registry import register_check
from coding_agent_playbook.grading.scope import CostTier, Determinism
from coding_agent_playbook.grading.types import (
    AbsoluteThreshold,
    CheckResult,
    ScopeDetail,
)

if TYPE_CHECKING:
    from coding_agent_playbook.grading.check import MeasurementSet
    from coding_agent_playbook.grading.types import EvalContext, Level, TrialResult

#: The ``over`` axes an aggregate check may reduce (mirrors the validator set).
_OVER_AXES = frozenset({"gate", "rubric", "verdict"})


def _trial_boolean(over: str, trial: TrialResult) -> bool | None:
    """The per-trial boolean an aggregate reduces, for one ``over`` axis.

    ``over == "verdict"`` reads the trial's already-derived verdict;
    ``over in {"gate", "rubric"}`` reads that layer's ``CheckResult.passed`` from
    the trial's report, or ``None`` when that layer was **skipped** (e.g. the
    rubric layer with no judge) — a skipped layer is neutral, it does not vote.
    This is the structural twin of
    :func:`coding_agent_playbook.evals.compile.compiler.over_boolean`, inlined here so the
    ``grading`` package never imports ``evals`` (which would create a cycle).
    Raises :exc:`ValueError` on an unknown axis, or a layer the report lacks.
    """
    if over == "verdict":
        return trial.verdict
    if over not in _OVER_AXES:
        raise ValueError(
            f"unknown 'over' selector {over!r}; expected 'verdict', 'gate', or 'rubric'"
        )
    for check in trial.report.checks:
        if check.check_id == over:
            return check.passed if check.status == "run" else None
    raise ValueError(f"'over' selector {over!r} has no {over!r} check in the trial report")


def _votes(over: str, trials: list[TrialResult]) -> list[bool]:
    """The ``over``-axis booleans of the trials where that axis actually ran."""
    return [vote for vote in (_trial_boolean(over, t) for t in trials) if vote is not None]


class AggregateCheck(Check):
    """Grade a ``pass@k`` / ``pass^k`` estimate over the runner's trials.

    Reads :attr:`~coding_agent_playbook.grading.types.EvalContext.trials` (the
    runner ran ``N = max(k)`` trials), reduces the selected ``over`` axis to the
    success count ``c`` over the ``n`` trials where that axis ran (a skipped axis
    does not vote), computes the ``0-1`` estimate via the subclass
    :meth:`_estimate`, and grades it against the absolute ``warn``/``fail``
    floor. Does no agent work - both axes are ``DETERMINISTIC``;
    :meth:`available` is ``True`` only once ``k`` trials voted on the axis.

    Subclasses set :attr:`_metric` (the registry/id name) and implement
    :meth:`_estimate`.
    """

    cost = CostTier.DETERMINISTIC
    determinism = Determinism.DETERMINISTIC

    #: Subclass id name (``pass_at_k`` / ``pass_pow_k``) for the ``<metric>:<over>@<k>`` id.
    _metric: str

    def __init__(
        self,
        *,
        k: int,
        over: str,
        warn: float | None = None,
        fail: float | None = None,
        weight: float = 0.0,
        required: bool = True,
    ) -> None:
        if k < 1:
            raise ValueError(f"aggregate k must be >= 1, got {k}")
        if over not in _OVER_AXES:
            raise ValueError(
                f"unknown 'over' selector {over!r}; expected 'verdict', 'gate', or 'rubric'"
            )
        self.k = k
        self.over = over
        self._absolute = AbsoluteThreshold(warn=warn, fail=fail)
        self.weight = weight
        self.required = required
        self.id = f"{self._metric}:{over}@{k}"

    def available(self, ctx: EvalContext) -> bool:
        """True once the runner populated ``ctx.trials`` with ``k`` voting trials.

        A trial votes when its ``over`` axis ran. An axis skipped in every trial
        (``over = "rubric"`` with no judge) leaves nothing to aggregate, so the
        check is unavailable — neutral, rather than a ``pass@k`` of ``0``. Fewer
        than ``k`` votes is unavailable too, rather than silently estimating
        ``pass@n`` in place of ``pass@k``.
        """
        return ctx.trials is not None and len(_votes(self.over, ctx.trials)) >= self.k

    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
        """Reduce the trials to ``(n, c)``, estimate the ``0-1`` score, then grade it.

        ``measurements`` is ignored - an aggregate reads ``ctx.trials`` directly.
        ``n`` is the count of trials whose selected ``over`` axis ran (a trial
        that skipped it does not vote) and ``c`` the count of those that passed.
        The subclass :meth:`_estimate` turns ``(n, c, k)`` into a ``0-1``
        reliability score, graded against the absolute ``warn``/``fail`` floor with
        the higher-is-better strict-below rule; ``passed`` is ``score >= fail``
        (a pure ``warn`` gate still passes - a warn never fails a check).
        """
        votes = _votes(self.over, ctx.trials or [])
        n = len(votes)
        c = sum(votes)
        # Guard k > n: available() requires n >= k, so this only fires for a direct
        # grade() call; clamp so the binomial terms stay well-defined.
        k = min(self.k, n) if n else self.k
        score = self._estimate(n=n, c=c, k=k)

        level, bound = _absolute_level(score, self._absolute)
        passed = self._absolute.fail is None or score >= self._absolute.fail
        detail = ScopeDetail(
            evaluator=self.id,
            scope_key=self.over,
            value=score,
            baseline=None,
            bound=bound,
            score=score,
            level=level,
            kind="absolute",
        )
        return CheckResult(
            check_id=self.id,
            passed=passed,
            score=score,
            weight=self.weight,
            required=self.required,
            determinism=self.determinism,
            cost=self.cost,
            status="run",
            subresults=(detail,),
        )

    def _estimate(self, *, n: int, c: int, k: int) -> float:
        """The ``0-1`` reliability estimate for ``c`` successes over ``n`` trials."""
        raise NotImplementedError


class PassAtK(AggregateCheck):
    """``pass@k`` - probability a random ``k``-subset contains ≥1 success.

    ``1.0`` when fewer than ``k`` trials failed (a ``k``-subset cannot avoid a
    success), else ``1 - C(n - c, k) / C(n, k)``.
    """

    _metric = "pass_at_k"

    def _estimate(self, *, n: int, c: int, k: int) -> float:
        if n == 0:
            return 0.0
        # If fewer than k trials failed, every k-subset must contain a success.
        if (n - c) < k:
            return 1.0
        return 1.0 - comb(n - c, k) / comb(n, k)


class PassPowK(AggregateCheck):
    """``pass^k`` - probability a random ``k``-subset is all successes.

    ``0.0`` when fewer than ``k`` trials succeeded (no all-success ``k``-subset
    exists), else ``C(c, k) / C(n, k)``.
    """

    _metric = "pass_pow_k"

    def _estimate(self, *, n: int, c: int, k: int) -> float:
        if n == 0 or c < k:
            return 0.0
        return comb(c, k) / comb(n, k)


def _absolute_level(
    score: float,
    absolute: AbsoluteThreshold,
) -> tuple[Level, float | None]:
    """Absolute warn/fail level + the deciding ``0-1`` cutoff for an estimate.

    The same higher-is-better strict-below rule the metric checks use
    (:func:`coding_agent_playbook.grading.check._absolute_level`): a score
    *strictly below* ``fail`` is ``fail``, *strictly below* ``warn`` is ``warn``,
    exactly-on the cutoff is ``ok``. A ``None`` bound skips that level. Returned
    cutoff is the ``0-1`` bound that decided (``None`` for ``ok``).
    """
    if absolute.fail is not None and score < absolute.fail:
        return "fail", absolute.fail
    if absolute.warn is not None and score < absolute.warn:
        return "warn", absolute.warn
    return "ok", None


@register_check("pass_at_k")
def _pass_at_k(
    *,
    k: int,
    over: str,
    warn: float | None = None,
    fail: float | None = None,
    weight: float = 0.0,
    required: bool = True,
    # NOTE: max_worsening (regression vs baseline trials) is accepted by the
    # validator but NOT YET SUPPORTED here - the absolute warn/fail path executes.
    # Swallow it here so an authored binding carrying it still builds.
    max_worsening: float | None = None,
) -> Check:
    """Build a :class:`PassAtK` over the runner's trials (the aggregate factory)."""
    return PassAtK(k=k, over=over, warn=warn, fail=fail, weight=weight, required=required)


@register_check("pass_pow_k")
def _pass_pow_k(
    *,
    k: int,
    over: str,
    warn: float | None = None,
    fail: float | None = None,
    weight: float = 0.0,
    required: bool = True,
    # NOTE: max_worsening is NOT YET SUPPORTED here (see _pass_at_k). Swallowed.
    max_worsening: float | None = None,
) -> Check:
    """Build a :class:`PassPowK` over the runner's trials (the aggregate factory)."""
    return PassPowK(k=k, over=over, warn=warn, fail=fail, weight=weight, required=required)


__all__ = ["AggregateCheck", "PassAtK", "PassPowK"]
