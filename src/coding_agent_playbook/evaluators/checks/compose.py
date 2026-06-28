"""The boolean composer checks: ``AllOf`` / ``AnyOf`` / ``Not`` (T4b).

Each composer is itself a :class:`~coding_agent_playbook.evaluators.check.Check`
that folds a set of *child* checks into one
:class:`~coding_agent_playbook.evaluators.types.CheckResult`, running them through
the cost-tiered short-circuit
:func:`~coding_agent_playbook.evaluators.scheduler.schedule`. Because a composer
is a ``Check``, it nests freely - ``AllOf(FileExistsCheck(...), AnyOf(...))`` is a
single check a :class:`~coding_agent_playbook.evaluators.rubric.Rubric` schedules
like any other.

Two derived descriptors let a parent scheduler tier and route a composer
correctly:

* :attr:`~coding_agent_playbook.evaluators.check.Check.cost` is the **max** child
  cost (the composer is only as cheap as its costliest child; ``DETERMINISTIC``
  when it has no children).
* :attr:`~coding_agent_playbook.evaluators.check.Check.determinism` is ``JUDGED``
  iff **any** child is judged (a composer over a judged child is itself judged).

An **unavailable** child is *neutral*, not a failure: ``AllOf`` /``AnyOf`` ignore
a skipped child's verdict (only *run* children vote). ``Not`` over an unavailable
child has nothing to invert, so it is itself ``status="skipped"``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.check import Check
from coding_agent_playbook.evaluators.scheduler import Op, schedule, skipped_result
from coding_agent_playbook.evaluators.scope import CostTier, Determinism
from coding_agent_playbook.evaluators.types import CheckResult

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.check import MeasurementSet
    from coding_agent_playbook.evaluators.types import EvalContext


def _max_cost(children: tuple[Check, ...]) -> CostTier:
    """The costliest child tier (a composer is only as cheap as its priciest child).

    Defaults to :attr:`~coding_agent_playbook.evaluators.scope.CostTier.DETERMINISTIC`
    for a childless composer so it schedules in the cheapest tier.
    """
    return max((c.cost for c in children), default=CostTier.DETERMINISTIC)


def _any_judged(children: tuple[Check, ...]) -> Determinism:
    """``JUDGED`` iff any child is judged, else ``DETERMINISTIC`` (routing axis)."""
    if any(c.determinism is Determinism.JUDGED for c in children):
        return Determinism.JUDGED
    return Determinism.DETERMINISTIC


class _Composer(Check):
    """Shared base for the boolean composers over a tuple of child checks.

    Derives :attr:`cost` (max child cost) and :attr:`determinism` (judged iff any
    child judged) from the children, and owns the descriptor attributes. The
    ``op`` (``"and"`` for :class:`AllOf`, ``"or"`` for :class:`AnyOf`) drives the
    short-circuit; subclasses implement :meth:`_verdict` to fold the *run* child
    results into one ``passed``.
    """

    #: The boolean fold passed to the scheduler (``"and"`` / ``"or"``).
    _op: Op

    def __init__(
        self,
        children: tuple[Check, ...],
        *,
        id: str,
        weight: float,
        required: bool,
    ) -> None:
        self._children = children
        self.id = id
        self.weight = weight
        self.required = required
        self.cost = _max_cost(children)
        self.determinism = _any_judged(children)

    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
        """Schedule the children under ``self._op`` and fold them into one result.

        Short-circuit is on (``op``-decided tiers stop early), single-worker (a
        composer is graded inside the parent's tier - it does not fan out its own
        thread pool). Only *run* children vote in :meth:`_verdict`; the children's
        results ride along as ``subresults``.
        """
        results = schedule(
            list(self._children),
            ctx,
            measurements,
            op=self._op,
            short_circuit=True,
            max_workers=1,
        )
        run = [r for r in results if r.status == "run"]
        passed = self._verdict(run)
        return CheckResult(
            check_id=self.id,
            passed=passed,
            score=1.0 if passed else 0.0,
            weight=self.weight,
            required=self.required,
            determinism=self.determinism,
            cost=self.cost,
            status="run",
            subresults=tuple(results),
        )

    def _verdict(self, run: list[CheckResult]) -> bool:
        """Fold the *run* child results into this composer's ``passed``."""
        raise NotImplementedError


class AllOf(_Composer):
    """Passes iff **all** run children pass (an unavailable child is neutral).

    Short-circuits ``op="and"``: once a required child fails, costlier child tiers
    are never graded. An empty / all-unavailable :class:`AllOf` is vacuously
    ``True`` (no run child failed).
    """

    _op = "and"

    def __init__(
        self,
        *children: Check,
        id: str = "all_of",
        weight: float = 0.0,
        required: bool = True,
    ) -> None:
        super().__init__(children, id=id, weight=weight, required=required)

    def _verdict(self, run: list[CheckResult]) -> bool:
        return all(r.passed for r in run)


class AnyOf(_Composer):
    """Passes iff **any** run child passes (an unavailable child is neutral).

    Short-circuits ``op="or"``: once a child passes, costlier child tiers are
    never graded. An empty / all-unavailable :class:`AnyOf` is ``False`` (no run
    child passed).
    """

    _op = "or"

    def __init__(
        self,
        *children: Check,
        id: str = "any_of",
        weight: float = 0.0,
        required: bool = True,
    ) -> None:
        super().__init__(children, id=id, weight=weight, required=required)

    def _verdict(self, run: list[CheckResult]) -> bool:
        return any(r.passed for r in run)


class Not(Check):
    """Inverts a single child's verdict; ``skipped`` when the child is unavailable.

    Derives :attr:`cost` / :attr:`determinism` from its one child. When the child
    runs, ``passed = not child.passed``; when the child is unavailable there is
    nothing to invert, so ``Not`` is itself ``status="skipped"`` (neutral). The
    child's result rides along as the single ``subresults`` entry.
    """

    def __init__(
        self,
        child: Check,
        *,
        id: str = "not",
        weight: float = 0.0,
        required: bool = True,
    ) -> None:
        self._child = child
        self.id = id
        self.weight = weight
        self.required = required
        self.cost = child.cost
        self.determinism = child.determinism

    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
        """Run the one child via the scheduler and invert its verdict.

        Routing through :func:`~coding_agent_playbook.evaluators.scheduler.schedule`
        (rather than calling the child directly) keeps the availability handling
        in one place: an unavailable child comes back ``status="skipped"``, and
        :class:`Not` propagates that skip instead of inverting a verdict that was
        never produced.
        """
        (child_result,) = schedule([self._child], ctx, measurements, max_workers=1)
        if child_result.status != "run":
            # Nothing to invert: propagate the child's skip, carrying its row.
            skipped = skipped_result(self)
            skipped.subresults = (child_result,)
            return skipped
        passed = not child_result.passed
        return CheckResult(
            check_id=self.id,
            passed=passed,
            score=1.0 if passed else 0.0,
            weight=self.weight,
            required=self.required,
            determinism=self.determinism,
            cost=self.cost,
            status="run",
            subresults=(child_result,),
        )


__all__ = ["AllOf", "AnyOf", "Not"]
