"""The judged ``Check``: one rubric criterion scored by a ``Judge``.

:class:`JudgeCheck` holds a single criterion string (one per ``[rubric]`` line)
and grades it by calling the structural
:class:`~coding_agent_playbook.evaluators.types.JudgeLike` on the context
(``ctx.judge.score_criterion(criterion, ctx.artifact, n=ctx.samples)``), so this
module never imports ``evals`` - avoiding the ``evaluators`` <-> ``evals`` cycle -
and a concrete :class:`~coding_agent_playbook.evals.judge.Judge` satisfies it
structurally.

Dormancy without a judge: :meth:`available` is ``True`` only when ``ctx.judge`` is
set, so a ``Rubric`` evaluated with no judge records the check as *skipped* (it
never fails the gate). The check ignores the
:class:`~coding_agent_playbook.evaluators.check.MeasurementSet` - a judged score
comes from the judge, not a deterministic measurement - and folds the result into
one :class:`~coding_agent_playbook.evaluators.types.CheckResult` carrying a single
``rubric``-keyed :class:`~coding_agent_playbook.evaluators.types.ScopeDetail`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.check import Check, slug
from coding_agent_playbook.evaluators.scope import CostTier, Determinism
from coding_agent_playbook.evaluators.types import CheckResult, ScopeDetail

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.check import MeasurementSet
    from coding_agent_playbook.evaluators.types import EvalContext


class JudgeCheck(Check):
    """Grade one rubric ``criterion`` with the context's judge into a SCORE.

    ``threshold`` is the ``0-1`` floor the judged score must reach to pass;
    ``weight`` is this criterion's share of a :class:`~coding_agent_playbook.evaluators.rubric.Rubric`'s
    weighted composite and ``required`` marks it a gate criterion. The id is
    ``judge:<slug(criterion)>`` (the shared :func:`coding_agent_playbook.evaluators.check.slug`),
    :attr:`determinism` is JUDGED and :attr:`cost` is JUDGED-tier so a scheduler
    runs it last.
    """

    cost = CostTier.JUDGED
    determinism = Determinism.JUDGED

    def __init__(
        self,
        criterion: str,
        *,
        threshold: float = 0.5,
        weight: float = 0.0,
        required: bool = False,
    ) -> None:
        self.criterion = criterion
        self.threshold = threshold
        self.weight = weight
        self.required = required
        self.id = f"judge:{slug(criterion)}"

    def available(self, ctx: EvalContext) -> bool:
        """True only when a judge is configured on ``ctx`` (else the check skips)."""
        return ctx.judge is not None

    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
        """Score the criterion via ``ctx.judge`` (averaged over ``ctx.samples``).

        ``measurements`` is ignored: a judged score is produced by the judge, not
        by a deterministic measurement. ``available`` guarantees a judge is
        present, so the call is unconditional here.
        """
        assert ctx.judge is not None  # guaranteed by available(); narrows for mypy
        score = ctx.judge.score_criterion(self.criterion, ctx.artifact, n=max(1, ctx.samples))
        passed = score >= self.threshold
        detail = ScopeDetail(
            evaluator=self.id,
            scope_key="rubric",
            value=score,
            baseline=None,
            bound=self.threshold,
            score=score,
            level="ok" if passed else "fail",
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


__all__ = ["JudgeCheck"]
