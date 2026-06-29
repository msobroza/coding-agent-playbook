"""The ``JudgeMetric`` adapter: a judged criterion presented as a ``Metric``.

The weighted rubric-criterion path is a
:class:`~coding_agent_playbook.evaluators.checks.judged.JudgeCheck` built via
``Rubric.of`` and is untouched here. This Adapter (Track C2) serves the *other*
shape: a judged criterion graded by an ordinary metric-backed
:class:`~coding_agent_playbook.evaluators.check.ThresholdCheck` /
:class:`~coding_agent_playbook.evaluators.check.NonRegressionCheck`. It wraps the
structural :class:`~coding_agent_playbook.evaluators.types.JudgeLike` on the
context as a :class:`~coding_agent_playbook.evaluators.metric.Metric` whose single
:class:`~coding_agent_playbook.evaluators.types.Measurement` value is the judge's
``score_criterion`` over the configured criterion (already a ``0-1`` goodness, so
the normalizer is :class:`~coding_agent_playbook.evaluators.normalizer.Identity`).

Like :class:`~coding_agent_playbook.evaluators.checks.judged.JudgeCheck`, it is
dormant without a judge (:meth:`available` is ``False`` when ``ctx.judge is
None``) and never imports ``evals`` — it consumes the judge only through the
``JudgeLike`` protocol, so the ``evaluators`` <-> ``evals`` cycle stays broken.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.check import slug
from coding_agent_playbook.evaluators.metric import Metric
from coding_agent_playbook.evaluators.normalizer import Identity, Normalizer
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import Measurement

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.types import EvalContext


class JudgeMetric(Metric):
    """Adapt a judged ``criterion`` to the :class:`Metric` measure interface.

    The metric ``name`` is ``judge:<slug(criterion)>`` (mirroring
    :class:`~coding_agent_playbook.evaluators.checks.judged.JudgeCheck`'s id), the
    scope is :attr:`~coding_agent_playbook.evaluators.scope.Scope.FILE`, and the
    value is the judge's per-criterion score (a ``0-1`` goodness, hence the
    :class:`~coding_agent_playbook.evaluators.normalizer.Identity` normalizer the
    ``Metric`` base now reads via :meth:`Metric.score`).
    """

    needs_project = False
    #: A judged criterion needs ``ctx.judge`` to measure (so a metric-backed check
    #: schedules it JUDGED-tier and measures it lazily — short-circuitable).
    needs_judge = True
    requires: str | None = None
    #: A judged score is already a ``0-1`` goodness, so the adapter passes it
    #: through unchanged (the ``Metric`` base owns ``normalizer`` since C3).
    normalizer: Normalizer = Identity()

    def __init__(self, criterion: str) -> None:
        self.criterion = criterion
        self.name = f"judge:{slug(criterion)}"
        self.scope = Scope.FILE

    def available(self, ctx: EvalContext) -> bool:
        """True only when a judge is configured on ``ctx`` (else the metric skips)."""
        return ctx.judge is not None

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        """One :class:`Measurement` = the judge's score for ``self.criterion``.

        ``available`` guarantees a judge is present, so the call is unconditional;
        the artifact graded is ``ctx.artifact`` and the sample count is
        ``max(1, ctx.samples)`` (mirroring
        :class:`~coding_agent_playbook.evaluators.checks.judged.JudgeCheck`).
        """
        assert ctx.judge is not None  # guaranteed by available(); narrows for mypy
        value = ctx.judge.score_criterion(self.criterion, ctx.artifact, n=max(1, ctx.samples))
        return [Measurement(evaluator=self.name, scope_key="judge", value=value)]


__all__ = ["JudgeMetric"]
