"""Tests for the judged ``Check`` (T4a) - ``evaluators/checks/judged.py``.

:class:`JudgeCheck` is the ``Check``-layer counterpart of the ``Evaluator``-era
:class:`~coding_agent_playbook.evaluators.judged.JudgedCriterion`: one rubric
criterion, scored by a structural ``JudgeLike`` on ``ctx`` into one
:class:`~coding_agent_playbook.evaluators.types.CheckResult`. These drive it with
a :class:`~coding_agent_playbook.evals.judge.StubJudge` so no LLM/CLI is touched,
asserting the score/pass/status/id shape, the ``available`` gate (a judge must be
present), that ``score_criterion`` is called with ``n = ctx.samples``, and the
``score == threshold`` boundary (a tie passes).
"""

from __future__ import annotations

from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.evaluators.check import MeasurementSet
from coding_agent_playbook.evaluators.checks.judged import JudgeCheck
from coding_agent_playbook.evaluators.scope import CostTier, Determinism
from coding_agent_playbook.evaluators.types import EvalContext, ScopeDetail


def _ctx(judge: StubJudge | None, *, samples: int = 1, artifact: object = "ART") -> EvalContext:
    return EvalContext(
        module=None,
        source="",
        label="judge",
        judge=judge,
        artifact=artifact,
        samples=samples,
    )


def _empty() -> MeasurementSet:
    return MeasurementSet([], None)


def test_id_and_descriptors() -> None:
    check = JudgeCheck("Code is well documented")
    assert check.id == "judge:code-is-well-documented"
    assert check.determinism is Determinism.JUDGED
    assert check.cost is CostTier.JUDGED
    # Defaults: advisory (weight 0, not required).
    assert check.weight == 0.0
    assert check.required is False


def test_available_requires_a_judge() -> None:
    check = JudgeCheck("anything")
    assert check.available(_ctx(None)) is False
    assert check.available(_ctx(StubJudge())) is True


def test_grade_passes_above_threshold() -> None:
    judge = StubJudge({"good": 0.9})
    check = JudgeCheck("good", threshold=0.5, weight=2.0, required=True)
    result = check.grade(_ctx(judge), _empty())

    assert result.check_id == "judge:good"
    assert result.passed is True
    assert result.score == 0.9
    assert result.weight == 2.0
    assert result.required is True
    assert result.status == "run"
    assert result.determinism is Determinism.JUDGED
    assert result.cost is CostTier.JUDGED

    # One ScopeDetail leaf describing the rubric line.
    assert len(result.subresults) == 1
    detail = result.subresults[0]
    assert isinstance(detail, ScopeDetail)
    assert detail.scope_key == "rubric"
    assert detail.value == 0.9
    assert detail.score == 0.9
    assert detail.bound == 0.5
    assert detail.baseline is None
    assert detail.level == "ok"
    assert detail.kind == "absolute"


def test_grade_fails_below_threshold() -> None:
    judge = StubJudge({"weak": 0.2})
    check = JudgeCheck("weak", threshold=0.5)
    result = check.grade(_ctx(judge), _empty())

    assert result.passed is False
    assert result.score == 0.2
    detail = result.subresults[0]
    assert isinstance(detail, ScopeDetail)
    assert detail.level == "fail"


def test_threshold_boundary_is_inclusive() -> None:
    # score == threshold passes (>=).
    judge = StubJudge({"tie": 0.5})
    check = JudgeCheck("tie", threshold=0.5)
    result = check.grade(_ctx(judge), _empty())
    assert result.passed is True
    detail = result.subresults[0]
    assert isinstance(detail, ScopeDetail)
    assert detail.level == "ok"


def test_score_criterion_called_with_ctx_samples() -> None:
    judge = StubJudge({"c": 0.7})
    check = JudgeCheck("c")
    ctx = _ctx(judge, samples=4, artifact="THE-ARTIFACT")
    check.grade(ctx, _empty())

    assert judge.calls == [("c", "THE-ARTIFACT", 4)]


def test_samples_floored_at_one() -> None:
    judge = StubJudge({"c": 0.7})
    check = JudgeCheck("c")
    ctx = _ctx(judge, samples=0)
    check.grade(ctx, _empty())
    # max(1, ctx.samples) ⇒ n is at least 1.
    assert judge.calls == [("c", "ART", 1)]
