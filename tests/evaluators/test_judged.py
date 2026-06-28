"""Tests for the judged evaluator (rubric, generalized) — SPEC prM §B3.

``JudgedCriterion`` is a parameterized evaluator the block-compiler instantiates
once per rubric line; it is *not* a registered singleton. It is JUDGED, dormant
in v1 (``available()`` False without a ``Judge``), and only ever exercised here
via a stub judge — never the v2 placeholder, which raises ``NotImplementedError``.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.evaluators.judged import JudgedCriterion, slug
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import EvalContext, JudgeLike


class _StubJudge:
    """A minimal stand-in implementing the :class:`JudgeLike` protocol.

    Exposes the canonical ``score_criterion(criterion, artifact, n)`` shape that
    ``JudgedCriterion.evaluate`` calls (R2 rename from ``.score``). Records how
    many samples it was asked for so tests can assert averaging behaviour, and
    returns a deterministic mean over the scripted per-sample scores.
    """

    def __init__(self, per_sample: list[float]) -> None:
        self.per_sample = per_sample
        self.calls: list[tuple[str, object, int]] = []

    def score_criterion(self, criterion: str, artifact: object, n: int = 1) -> float:
        self.calls.append((criterion, artifact, n))
        # Average the first ``n`` scripted per-sample scores (cycle if short).
        sampled = [self.per_sample[i % len(self.per_sample)] for i in range(n)]
        return sum(sampled) / len(sampled)


def _ctx(*, judge: JudgeLike | None = None, samples: int = 1) -> EvalContext:
    return EvalContext(
        module=None,
        source="",
        label="output",
        judge=judge,
        artifact="the agent's output text",
        samples=samples,
    )


def test_judged_criterion_descriptor_attrs() -> None:
    ev = JudgedCriterion("Findings prioritized correctly", weight=0.5)
    assert ev.determinism is Determinism.JUDGED
    assert ev.value_kind is ValueKind.SCORE
    assert ev.higher_is_worse is False
    assert ev.scope is Scope.FILE
    assert ev.needs_project is False
    assert ev.requires is None
    assert ev.default_weight == 0.5
    assert ev.weight == 0.5
    assert ev.criterion == "Findings prioritized correctly"


def test_judged_criterion_name_is_slugged() -> None:
    ev = JudgedCriterion("Each finding proposes a concrete fix!", weight=0.5)
    assert ev.name == "judged:each-finding-proposes-a-concrete-fix"


def test_judged_criterion_default_regression_is_tolerant() -> None:
    """Judged regression uses a tolerance band (stochastic), unlike the exact
    deterministic ``0.0``."""
    ev = JudgedCriterion("c", weight=0.5)
    assert ev.default_regression.max_worsening == pytest.approx(0.1)


def test_judged_criterion_default_absolute_optional_min_score() -> None:
    ev = JudgedCriterion("c", weight=0.5, min_score=0.6)
    assert ev.default_absolute.fail == pytest.approx(0.6)


def test_judged_criterion_default_absolute_unset_by_default() -> None:
    ev = JudgedCriterion("c", weight=0.5)
    assert ev.default_absolute.fail is None
    assert ev.default_absolute.warn is None


def test_available_false_without_judge() -> None:
    ev = JudgedCriterion("c", weight=0.5)
    assert ev.available(_ctx(judge=None)) is False


def test_available_true_with_judge() -> None:
    ev = JudgedCriterion("c", weight=0.5)
    assert ev.available(_ctx(judge=_StubJudge([1.0]))) is True


def test_evaluate_returns_one_score_measurement() -> None:
    judge = _StubJudge([0.8])
    ev = JudgedCriterion("Findings prioritized correctly", weight=0.5)
    measurements = ev.evaluate(_ctx(judge=judge, samples=1))
    assert len(measurements) == 1
    m = measurements[0]
    assert m.evaluator == ev.name
    assert m.value == pytest.approx(0.8)
    assert m.scope_key == "output"


def test_evaluate_passes_criterion_artifact_and_samples_to_judge() -> None:
    judge = _StubJudge([0.5])
    ev = JudgedCriterion("crit", weight=0.5)
    ev.evaluate(_ctx(judge=judge, samples=3))
    assert judge.calls == [("crit", "the agent's output text", 3)]


def test_evaluate_averages_over_samples() -> None:
    # Per-sample scores 1.0, 0.0, 1.0, 0.0 -> mean over 4 = 0.5.
    judge = _StubJudge([1.0, 0.0])
    ev = JudgedCriterion("crit", weight=0.5)
    measurements = ev.evaluate(_ctx(judge=judge, samples=4))
    assert measurements[0].value == pytest.approx(0.5)


def test_evaluate_without_judge_returns_empty() -> None:
    ev = JudgedCriterion("crit", weight=0.5)
    assert ev.evaluate(_ctx(judge=None)) == []


def test_evaluate_clamps_samples_to_at_least_one() -> None:
    """``ctx.samples`` is documented as ``>= 1``; a degenerate ``0`` must not
    crash with a divide-by-zero — it is clamped to a single sample."""
    judge = _StubJudge([0.7])
    ev = JudgedCriterion("crit", weight=0.5)
    measurements = ev.evaluate(_ctx(judge=judge, samples=0))
    assert measurements[0].value == pytest.approx(0.7)
    # The judge is asked for at least one sample.
    assert judge.calls[0][2] == 1


def test_judged_criterion_is_not_registered() -> None:
    """It is parameterized per rubric line, so it must NOT be a registered
    singleton discoverable by name."""
    from coding_agent_playbook.evaluators.registry import all_evaluators

    names = {ev.name for ev in all_evaluators()}
    assert not any(n.startswith("judged:") for n in names)


def test_slug_helper() -> None:
    assert slug("Hello, World!") == "hello-world"
    assert slug("  multiple   spaces ") == "multiple-spaces"
    assert slug("Tests use pytest.parametrize") == "tests-use-pytest-parametrize"
    assert slug("") == "criterion"
    assert slug("???") == "criterion"
