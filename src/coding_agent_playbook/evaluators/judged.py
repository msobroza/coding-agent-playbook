"""Judged evaluator — the rubric, generalized (SPEC prM §B3).

A rubric criterion is just another :class:`Evaluator`: a graded SCORE over a
scope whose value is produced by a *judge* (LLM or human) rather than by static
analysis. :class:`JudgedCriterion` is a **parameterized** evaluator the eval
block-compiler instantiates once per rubric line — it is deliberately **not** a
registered singleton (no ``@register_evaluator``), since each instance carries
its own criterion text and weight.

Dormancy without a judge: :meth:`available` is ``True`` only when a judge is
supplied on the context, so with no judge configured the runner never runs it.
The judge is the structural :class:`~coding_agent_playbook.evaluators.types.JudgeLike`
protocol (``ctx.judge.score_criterion(criterion, artifact, n)``), so this module
never imports ``evals`` — avoiding the ``evaluators`` ↔ ``evals`` cycle — and the
concrete :class:`~coding_agent_playbook.evals.judge.Judge` satisfies it
structurally.

Non-regression is stochastic for judged criteria, so the default tolerance band
is a small ``max_worsening`` (``0.1``) rather than the deterministic exact ``0.0``,
and :meth:`evaluate` averages over ``ctx.samples`` (``>= 1``) to damp LLM noise.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.parse import scope_key
from coding_agent_playbook.evaluators.registry import Evaluator
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    Measurement,
    RegressionPolicy,
)

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext

#: Tolerance band for judged non-regression (stochastic; SPEC prM §H/§I).
_JUDGED_TOLERANCE = 0.1

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    """Lowercase ``text`` to a hyphen-separated slug for the evaluator name.

    Collapses every run of non-alphanumeric characters to a single ``-`` and
    strips leading/trailing hyphens. Returns the literal ``"criterion"`` when the
    input slugs to the empty string (e.g. ``""`` or ``"???"``) so the resulting
    ``judged:<slug>`` name is always well-formed.
    """
    cleaned = _SLUG_NON_ALNUM.sub("-", text.lower()).strip("-")
    return cleaned or "criterion"


class JudgedCriterion(Evaluator):
    """One rubric criterion, scored by a judge into a ``0-1`` SCORE.

    Instantiated per rubric line by the block-compiler; ``criterion`` is the
    human-readable text shown to the judge and ``weight`` is its share of the
    weighted composite. Scope is :attr:`Scope.FILE`: a judged criterion grades
    one artifact (the agent's produced output, ``ctx.artifact``) keyed on
    ``ctx.label``, mirroring how the FILE-scope static metrics key the file.
    """

    scope = Scope.FILE
    value_kind = ValueKind.SCORE
    determinism = Determinism.JUDGED
    higher_is_worse = False
    #: The judge is supplied via ``ctx.judge`` at run time, not an importable
    #: dependency, so there is nothing for ``available()`` to ``find_spec``.
    requires = None
    needs_project = False

    def __init__(self, criterion: str, *, weight: float, min_score: float | None = None) -> None:
        self.criterion = criterion
        self.weight = weight
        self.name = f"judged:{slug(criterion)}"
        self.default_weight = weight
        # Optional hard floor on the judged score; unset by default.
        self.default_absolute = AbsoluteThreshold(fail=min_score)
        # Tolerance band — judged scores are stochastic (vs deterministic 0.0).
        self.default_regression = RegressionPolicy(max_worsening=_JUDGED_TOLERANCE)

    def available(self, ctx: EvalContext) -> bool:
        """True only when a ``Judge`` is configured, so v1 never runs it."""
        return ctx.judge is not None

    def evaluate(self, ctx: EvalContext) -> list[Measurement]:
        """Score the criterion via the judge, averaged over ``ctx.samples``.

        Calls ``ctx.judge.score_criterion(self.criterion, ctx.artifact, n=samples)``
        once with ``n = max(1, ctx.samples)`` (the judge owns the per-sample
        averaging) and surfaces the result as one SCORE measurement keyed on
        ``ctx.label``. Returns ``[]`` when no judge is present so a stray call in
        a judge-less context is a no-op rather than a crash.
        """
        if ctx.judge is None:
            return []
        samples = max(1, ctx.samples)
        value = ctx.judge.score_criterion(self.criterion, ctx.artifact, n=samples)
        return [
            Measurement(
                evaluator=self.name,
                scope_key=scope_key(ctx.label, None),
                value=float(value),
            )
        ]
