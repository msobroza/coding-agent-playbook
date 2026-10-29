"""Re-score one stored run from its judge-free checks and new criterion scores (spec D9).

When only the judge changed, a record re-grades a release's stored answers with
the new judge instead of rerunning the agent. :func:`rescore_run` turns one
stored run (``evals.answers_store.StoredRun.checks``) and the new judge's mean
score per rubric criterion into the run's verdict and scores, exactly as
``evals.run.scoring.score`` would have produced them:

- It grades the sample's own compiled per-trial rubric, so the layer
  expressions, weights and thresholds (``fail = 0.5``) are the engine's.
- A deterministic layer (every ``[gate]`` today) is not regraded: its stored
  result stands. In a judged layer, each deterministic leaf is read from the
  stored checks and each judge call returns the given criterion score.
- The ``[verdict]`` is derived by ``scoring.apply_verdict``, shared with ``score``.

A run whose judge fail-fast skipped is never re-graded (D9), so every criterion
needs a score. Samples whose stored checks cannot reproduce them are refused
with :class:`RejudgeError`: an ``[aggregate]`` block (it folds several trials),
a weighted ``[verdict]`` (it scores the gate from its leaves, not its stored
verdict), and a judged layer whose deterministic leaf stored a partial score
(its verdict needs the measurement, not the score).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.evals.release_metrics import report_check_scores
from coding_agent_playbook.evals.run.scoring import apply_verdict
from coding_agent_playbook.evals.sample import compile_eval_sample
from coding_agent_playbook.exit_two import ExitTwoError
from coding_agent_playbook.grading.check import Check, MeasurementSet
from coding_agent_playbook.grading.compose import AllOf, AnyOf, Not
from coding_agent_playbook.grading.judged import JudgeCheck
from coding_agent_playbook.grading.measuring import referenced_metrics
from coding_agent_playbook.grading.rubric import Rubric
from coding_agent_playbook.grading.scope import Determinism
from coding_agent_playbook.grading.types import CheckResult, EvalContext

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.evals.compile.compiler import CompiledSample
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.grading.types import EvaluationReport


class RejudgeError(ExitTwoError):
    """A stored run that cannot be re-scored; the message names the sample or criterion."""


@dataclass(frozen=True)
class RunScore:
    """One re-scored run: its layer verdicts, weighted rubric score, verdict and check scores.

    ``rubric_passed`` is ``None`` without a rubric layer, ``rubric_score`` without
    a rubric criterion. ``checks`` is what ``release_metrics.run_check_scores``
    gives for a fresh run.
    """

    gate_passed: bool
    rubric_passed: bool | None
    rubric_score: float | None
    passed: bool
    aggregate_score: float
    checks: Mapping[str, float]


def rescore_run(
    sample: EvalSample, stored_checks: Mapping[str, float], criterion_scores: Mapping[str, float]
) -> RunScore:
    """Re-score one stored run of ``sample`` with new ``criterion_scores`` (text to 0-1 mean).

    Example::

        >>> rescore_run(sample, stored.checks, {"The review names the bug": 0.9}).passed
        ... # doctest: +SKIP
        True
    """
    compiled = _compiled(sample)
    layers = [_replay_layer(layer, stored_checks) for layer in compiled.per_trial.checks]
    ctx = EvalContext(
        module=None, source="", label="rubric", judge=_GivenScores(sample.id, criterion_scores)
    )
    report = Rubric(layers, name=sample.id).evaluate(ctx, MeasurementSet([], None))
    apply_verdict(report, compiled.verdict_spec)
    return RunScore(
        gate_passed=_layer_passed(report, "gate") is not False,
        rubric_passed=_layer_passed(report, "rubric"),
        rubric_score=_weighted_score(rubric_criteria(sample), criterion_scores),
        passed=report.passed,
        # As the runner's single-trial ``_assemble``: the composite, else the verdict.
        aggregate_score=report.composite if report.composite is not None else float(report.passed),
        checks={**stored_checks, **report_check_scores(report.checks)},
    )


def rubric_criteria(sample: EvalSample) -> tuple[tuple[str, float], ...]:
    """Each judged rubric criterion of ``sample`` with its weight, in rubric order.

    Read off the compiled check tree, as grading sees it (named rubrics included).

    Example::

        >>> rubric_criteria(sample)[0]  # doctest: +SKIP
        ('The extracted helper has a name ...', 0.3)
    """
    checks = compile_eval_sample(sample).per_trial.checks
    rubrics = [m for m in referenced_metrics(checks, nested=True) if isinstance(m, Rubric)]
    return tuple(
        (check.criterion, check.weight)
        for rubric in rubrics
        for check in rubric.checks
        if isinstance(check, JudgeCheck)
    )


def _compiled(sample: EvalSample) -> CompiledSample:
    """``sample`` compiled, refused when its stored checks cannot reproduce its scores."""
    compiled = compile_eval_sample(sample)
    if compiled.aggregate is not None:
        raise RejudgeError(f"cannot re-judge {sample.id}: its [aggregate] block folds trials")
    if compiled.verdict_spec.mode != "boolean":
        raise RejudgeError(f"cannot re-judge {sample.id}: its [verdict] is weighted")
    return compiled


def _replay_layer(layer: Check, stored: Mapping[str, float]) -> Check:
    """A deterministic layer keeps its stored result; a judged one is regraded."""
    if layer.determinism is Determinism.DETERMINISTIC:
        return _StoredCheck(layer, stored)
    return _replay(layer, stored)


def _replay(check: Check, stored: Mapping[str, float]) -> Check:
    """``check`` with each deterministic leaf read from ``stored``; judged leaves stay."""
    if isinstance(check, (AllOf, AnyOf)):
        children = (_replay(child, stored) for child in check.children)
        return type(check)(*children, id=check.id, weight=check.weight, required=check.required)
    if isinstance(check, Not):
        child = _replay(check.children[0], stored)
        return Not(child, id=check.id, weight=check.weight, required=check.required)
    if check.determinism is Determinism.DETERMINISTIC:
        return _StoredCheck(check, stored)
    return check


class _StoredCheck(Check):
    """A deterministic check whose result is its stored score; skipped when none was stored.

    Its verdict is the stored score read as a boolean: a layer or a file or
    answer check stores ``1.0`` or ``0.0``, and any other score is refused.
    """

    determinism = Determinism.DETERMINISTIC

    def __init__(self, check: Check, stored: Mapping[str, float]) -> None:
        self.id = check.id
        self.weight = check.weight
        self.required = check.required
        self.cost = check.cost
        self._stored = stored

    def available(self, ctx: EvalContext) -> bool:
        return self.id in self._stored

    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
        score = self._stored[self.id]
        if score not in (0.0, 1.0):
            raise RejudgeError(
                f"cannot re-judge check {self.id!r}: its stored score {score} is not a verdict"
            )
        return CheckResult(
            check_id=self.id,
            passed=score == 1.0,
            score=score,
            weight=self.weight,
            required=self.required,
            determinism=self.determinism,
            cost=self.cost,
            status="run",
        )


class _GivenScores:
    """A judge that returns each criterion's given score and makes no call."""

    def __init__(self, sample_id: str, scores: Mapping[str, float]) -> None:
        self._sample_id = sample_id
        self._scores = scores

    def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
        if criterion not in self._scores:
            raise RejudgeError(f"no criterion score for {self._sample_id}: {criterion!r}")
        return self._scores[criterion]


def _layer_passed(report: EvaluationReport, layer: str) -> bool | None:
    """``layer``'s verdict in ``report``; ``None`` when it is absent or skipped."""
    for check in report.checks:
        if check.check_id == layer and check.status == "run":
            return check.passed
    return None


def _weighted_score(
    criteria: tuple[tuple[str, float], ...], scores: Mapping[str, float]
) -> float | None:
    """The weight-normalized mean of the criterion ``scores``; ``None`` without a criterion."""
    total = sum(weight for _text, weight in criteria)
    if not criteria or total <= 0:
        return None
    return sum(weight * scores[text] for text, weight in criteria) / total


__all__ = ["RejudgeError", "RunScore", "rescore_run", "rubric_criteria"]
