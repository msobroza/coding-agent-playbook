"""The deterministic ``answer_matches`` check — gate on what the agent *said*.

The file checks in :mod:`coding_agent_playbook.evals.checks.files` gate on
what the agent *did* (the candidate tree). This one gates on the graded
**artifact** (:attr:`EvalContext.artifact`), which for a review-only sample is the
agent's answer: such a sample forbids edits (a ``file_unchanged`` gate), so it
produces no diff and the file predicates alone can only prove the agent stayed
its hand — never that it reached the right conclusion.

Its purpose is a cheap, token-free *class* gate in front of the LLM judge: a sample
whose answer must land in a known category (a CWE class, a required verdict word)
declares one regex, and the cost-tiered scheduler's short-circuit
(:mod:`coding_agent_playbook.grading.scheduler`, ``fail_fast=True`` — the
runner default) skips the JUDGED tier entirely when it fails. A plainly wrong
answer therefore costs zero judge tokens.

Two deliberate design points:

* **Fail-closed.** :meth:`available` is unconditionally ``True`` (the check needs
  no judge, project, or tree). A missing or empty artifact grades ``False``
  rather than reporting unavailable — an unavailable check is *skipped*, and a
  skipped check is neutral in the layer expression, which would let a silent
  agent through the gate it was meant to lose.
* **The regex compiles at construction.** A malformed pattern is an authoring
  error in ``sample.toml``, so it raises while the sample is being compiled (and
  hence during ``playbook validate``) instead of midway through a scored run.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from coding_agent_playbook.grading.check import Check
from coding_agent_playbook.grading.check_registry import register_check
from coding_agent_playbook.grading.scope import CostTier, Determinism
from coding_agent_playbook.grading.types import CheckResult, ScopeDetail

if TYPE_CHECKING:
    from coding_agent_playbook.grading.check import MeasurementSet
    from coding_agent_playbook.grading.types import EvalContext

#: The single scope key the check reports under (it grades one artifact, not a tree).
_SCOPE_KEY = "answer"


@register_check("answer_matches")
class AnswerMatchesCheck(Check):
    """The graded artifact matches ``pattern`` (a Python :mod:`re` regex).

    Authored as a ``[gate.bind]`` handle::

        [gate.bind]
        names_class = { check = "answer_matches", pattern = "(?i)command injection|cwe[-\\s]?78" }

    Case-insensitivity is **the pattern's** business (``(?i)``), not a separate
    flag — one knob, and the authored regex reads exactly as it behaves.

    A pure gate like the file checks: ``weight=0.0``, ``required=True``,
    DETERMINISTIC determinism and cost, with ``passed`` straight from the
    predicate and ``score`` its ``1.0``/``0.0`` shadow.
    """

    cost = CostTier.DETERMINISTIC
    determinism = Determinism.DETERMINISTIC

    def __init__(self, pattern: str, *, weight: float = 0.0, required: bool = True) -> None:
        try:
            self._regex = re.compile(pattern)
        except re.error as exc:
            raise ValueError(
                f"answer_matches pattern {pattern!r} is not a valid Python regular "
                f"expression ({exc}); expected e.g. '(?i)command injection|cwe[-\\s]?78'"
            ) from exc
        self.pattern = pattern
        self.weight = weight
        self.required = required
        self.id = f"answer_matches:/{pattern}/"

    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
        """Search ``ctx.artifact`` for the pattern into one BOOL result.

        ``measurements`` is ignored — like the file checks this one reads the
        context directly. ``ctx.artifact`` is typed ``Any`` (the scoring bridge
        sets the candidate's diff or, for a review sample, its transcript), so it is
        stringified; ``None`` becomes ``""`` and therefore cannot match.
        """
        ok = self._regex.search(_as_text(ctx.artifact)) is not None
        score = 1.0 if ok else 0.0
        detail = ScopeDetail(
            evaluator=self.id,
            scope_key=_SCOPE_KEY,
            value=score,
            baseline=None,
            bound=None,
            score=score,
            level="ok" if ok else "fail",
            kind="absolute",
        )
        return CheckResult(
            check_id=self.id,
            passed=ok,
            score=score,
            weight=self.weight,
            required=self.required,
            determinism=self.determinism,
            cost=self.cost,
            status="run",
            subresults=(detail,),
        )


def _as_text(artifact: object | None) -> str:
    """The artifact as searchable text — ``""`` when absent (so it cannot match)."""
    if artifact is None:
        return ""
    return artifact if isinstance(artifact, str) else str(artifact)


__all__ = ["AnswerMatchesCheck"]
