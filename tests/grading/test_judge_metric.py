"""Tests for the ``JudgeMetric`` adapter — ``grading/judge_metric.py``.

``JudgeMetric`` is the Adapter (Track C2) that lets a judged criterion be wrapped
in an ordinary metric-backed :class:`ThresholdCheck`/:class:`NonRegressionCheck`:
it presents the structural :class:`JudgeLike` on the context as a
:class:`~coding_agent_playbook.grading.metric.Metric` whose single
:class:`~coding_agent_playbook.grading.types.Measurement` value is the judge's
``score_criterion`` over the configured criterion. The weighted rubric-criterion
path (``JudgeCheck`` via ``Rubric.of``) is untouched and unrelated to this.

These tests are hermetic: ``StubJudge`` (unregistered) supplies deterministic
scores and records its calls so the ``n=ctx.samples`` wiring is asserted.
"""

from __future__ import annotations

from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.grading.judge_metric import JudgeMetric
from coding_agent_playbook.grading.normalizer import Identity
from coding_agent_playbook.grading.scope import Scope
from coding_agent_playbook.grading.types import EvalContext


def _ctx(
    *, judge: StubJudge | None, artifact: object = "ARTIFACT", samples: int = 1
) -> EvalContext:
    """A minimal :class:`EvalContext` carrying just the judged fields."""
    return EvalContext(
        module=None,
        source="",
        label="",
        judge=judge,
        artifact=artifact,
        samples=samples,
    )


def test_judge_metric_name_scope_and_flags() -> None:
    metric = JudgeMetric("clear naming")
    assert metric.name == "judge:clear-naming"
    assert metric.scope is Scope.FILE
    assert metric.needs_project is False
    assert metric.requires is None
    assert isinstance(metric.normalizer, Identity)


def test_available_false_without_judge() -> None:
    metric = JudgeMetric("clear naming")
    assert metric.available(_ctx(judge=None)) is False


def test_available_true_with_judge() -> None:
    metric = JudgeMetric("clear naming")
    assert metric.available(_ctx(judge=StubJudge())) is True


def test_measure_returns_one_measurement_with_stub_score() -> None:
    judge = StubJudge({"clear naming": 0.75})
    metric = JudgeMetric("clear naming")
    measurements = metric.measure(_ctx(judge=judge))
    assert len(measurements) == 1
    (m,) = measurements
    assert m.evaluator == "judge:clear-naming"
    assert m.scope_key == "judge"
    assert m.value == 0.75


def test_measure_passes_samples_as_n() -> None:
    judge = StubJudge({"clear naming": 1.0})
    metric = JudgeMetric("clear naming")
    metric.measure(_ctx(judge=judge, artifact="THE-DIFF", samples=3))
    assert judge.calls == [("clear naming", "THE-DIFF", 3)]


def test_measure_floors_samples_at_one() -> None:
    judge = StubJudge({"clear naming": 1.0})
    metric = JudgeMetric("clear naming")
    metric.measure(_ctx(judge=judge, samples=0))
    assert judge.calls[0][2] == 1
