"""Tests for the weighted-composite verdict (C10).

The weighted form of ``[verdict]`` derives a single ``0-1`` composite over the
gate/rubric layers' per-layer scores: rubric layer falls through to its own
``CheckResult.score`` (the per-trial rubric's composite), gate layer falls
through to the mean-of-leaf-scores (Goodness-of-Boolean). Skipped layers are
dropped and the remaining weights renormalize. ``passed = composite >= fail``.

These tests drive :func:`_layer_score` over synthetic :class:`CheckResult` trees
and :func:`weighted_verdict` over synthetic :class:`EvaluationReport` shapes.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.evals.compile._expr import parse
from coding_agent_playbook.evals.compile.compiler import (
    VerdictSpec,
    _layer_score,
    _mean_leaf_scores,
    weighted_verdict,
)
from coding_agent_playbook.evaluators.scope import CostTier, Determinism
from coding_agent_playbook.evaluators.types import (
    CheckResult,
    EvaluationReport,
    ScopeDetail,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _leaf(
    check_id: str,
    *,
    score: float | None,
    passed: bool = True,
    status: str = "run",
) -> CheckResult:
    """A leaf :class:`CheckResult` (subresults are scope-details — none here)."""
    return CheckResult(
        check_id=check_id,
        passed=passed,
        score=score,
        weight=0.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        status=status,  # type: ignore[arg-type]
        subresults=(),
    )


def _composer(
    check_id: str,
    *children: CheckResult,
    passed: bool = True,
) -> CheckResult:
    """A composer-shaped :class:`CheckResult` (subresults are nested CheckResults)."""
    return CheckResult(
        check_id=check_id,
        passed=passed,
        score=1.0 if passed else 0.0,  # boolean composer collapse.
        weight=0.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        status="run",
        subresults=tuple(children),
    )


def _layer(check_id: str, inner: CheckResult, *, passed: bool | None = None) -> CheckResult:
    """The compiler wraps each layer in a single-child ``AllOf`` named after the layer."""
    if passed is None:
        passed = inner.passed
    return _composer(check_id, inner, passed=passed)


def _skipped_layer(check_id: str) -> CheckResult:
    """A layer recorded skipped (dormant judged path)."""
    return CheckResult(
        check_id=check_id,
        passed=True,
        score=None,
        weight=0.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        status="skipped",
        subresults=(),
    )


def _report(*layers: CheckResult) -> EvaluationReport:
    return EvaluationReport(
        findings=[],
        warn_count=0,
        fail_count=0,
        composite=None,
        passed=True,
        checks=list(layers),
    )


def _detail(scope: str, *, score: float) -> ScopeDetail:
    return ScopeDetail(
        evaluator="x",
        scope_key=scope,
        value=score,
        baseline=None,
        bound=None,
        score=score,
        level="ok",
        kind="absolute",
    )


# --------------------------------------------------------------------------- #
# _layer_score: G-B over gate-shaped trees, score-passthrough on rubric
# --------------------------------------------------------------------------- #


def test_layer_score_gate_mean_of_leaf_scores() -> None:
    """Four leaves under a composer-wrapped layer => mean-of-leaves."""
    gate = _layer(
        "gate",
        _composer(
            "all_of",
            _leaf("a", score=1.0),
            _leaf("b", score=1.0),
            _leaf("c", score=1.0),
            _leaf("d", score=0.5),
        ),
    )
    assert _layer_score(gate) == pytest.approx(0.875)


def test_layer_score_descends_through_nested_composites() -> None:
    """Composers nested under composers are flattened to their leaves."""
    gate = _layer(
        "gate",
        _composer(
            "all_of",
            _composer("any_of", _leaf("a", score=1.0), _leaf("b", score=0.0)),
            _leaf("c", score=0.5),
        ),
    )
    # Three leaves: 1.0, 0.0, 0.5 -> mean = 0.5
    assert _layer_score(gate) == pytest.approx(0.5)


def test_layer_score_skipped_leaves_excluded() -> None:
    """A skipped leaf contributes nothing to the mean."""
    gate = _layer(
        "gate",
        _composer(
            "all_of",
            _leaf("a", score=1.0),
            _leaf("b", score=None, status="skipped"),
            _leaf("c", score=0.0),
        ),
    )
    # Two run leaves (1.0, 0.0); skipped 'b' excluded -> mean = 0.5.
    assert _layer_score(gate) == pytest.approx(0.5)


def test_layer_score_no_leaves_with_score_returns_none() -> None:
    """If no leaf contributed a score, the layer-score is ``None`` (effectively-skipped)."""
    gate = _layer(
        "gate",
        _composer("all_of", _leaf("a", score=None, status="skipped")),
    )
    assert _layer_score(gate) is None


def test_layer_score_rubric_uses_layer_threshold_score() -> None:
    """The rubric layer's wrapping AllOf is G-B, but its inner ThresholdCheck has the composite."""
    # The wrapping AllOf has score=1.0/0.0; the inner ThresholdCheck has score
    # = the rubric's actual composite. _layer_score should descend past the
    # G-B wrapper and report the rubric composite (a partial-credit leaf).
    inner = CheckResult(
        check_id="threshold:quality",
        passed=True,
        score=0.8,  # the actual rubric composite (mean of judged criteria).
        weight=0.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        status="run",
        subresults=(_detail("quality", score=0.8),),
    )
    rubric = _layer("rubric", inner)
    assert _layer_score(rubric) == pytest.approx(0.8)


# --------------------------------------------------------------------------- #
# weighted_verdict: composite + threshold + skipped renormalization
# --------------------------------------------------------------------------- #


def _spec(weights: dict[str, float], *, fail: float, warn: float | None = None) -> VerdictSpec:
    return VerdictSpec(
        mode="weighted",
        ast=parse("gate and rubric"),
        weights=weights,
        fail=fail,
        warn=warn,
    )


def test_weighted_verdict_combines_layer_scores() -> None:
    # gate score 1.0 (one perfect leaf), rubric score 0.5 (one half-credit leaf).
    gate = _layer("gate", _composer("all_of", _leaf("a", score=1.0)))
    rubric_inner = CheckResult(
        check_id="threshold:q",
        passed=True,
        score=0.5,
        weight=0.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        status="run",
        subresults=(_detail("q", score=0.5),),
    )
    rubric = _layer("rubric", rubric_inner)
    report = _report(gate, rubric)
    spec = _spec({"gate": 0.4, "rubric": 0.6}, fail=0.6)
    # 0.4 * 1.0 + 0.6 * 0.5 = 0.4 + 0.3 = 0.7
    score, passed = weighted_verdict(report, spec)
    assert score == pytest.approx(0.7)
    assert passed is True


def test_weighted_verdict_threshold_exact_equality_passes() -> None:
    """``passed = composite >= fail`` — an exact-on-cutoff score passes."""
    gate = _layer("gate", _composer("all_of", _leaf("a", score=0.5)))
    rubric_inner = CheckResult(
        check_id="threshold:q",
        passed=True,
        score=0.5,
        weight=0.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        status="run",
        subresults=(_detail("q", score=0.5),),
    )
    rubric = _layer("rubric", rubric_inner)
    report = _report(gate, rubric)
    spec = _spec({"gate": 0.5, "rubric": 0.5}, fail=0.5)
    score, passed = weighted_verdict(report, spec)
    assert score == pytest.approx(0.5)
    assert passed is True


def test_weighted_verdict_just_below_threshold_fails() -> None:
    gate = _layer("gate", _composer("all_of", _leaf("a", score=0.5)))
    rubric_inner = CheckResult(
        check_id="threshold:q",
        passed=True,
        score=0.4,
        weight=0.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        status="run",
        subresults=(_detail("q", score=0.4),),
    )
    rubric = _layer("rubric", rubric_inner)
    report = _report(gate, rubric)
    spec = _spec({"gate": 0.5, "rubric": 0.5}, fail=0.5)
    score, passed = weighted_verdict(report, spec)
    # 0.5*0.5 + 0.5*0.4 = 0.45 < 0.5
    assert score == pytest.approx(0.45)
    assert passed is False


def test_weighted_verdict_renormalizes_skipped_layer() -> None:
    """When the rubric layer is skipped, gate's weight renormalizes to 1.0."""
    gate = _layer("gate", _composer("all_of", _leaf("a", score=0.8)))
    rubric = _skipped_layer("rubric")
    report = _report(gate, rubric)
    spec = _spec({"gate": 0.4, "rubric": 0.6}, fail=0.7)
    score, passed = weighted_verdict(report, spec)
    # Only gate contributes; renormalized weight = 1.0. Composite = 0.8.
    assert score == pytest.approx(0.8)
    assert passed is True


def test_weighted_verdict_all_skipped_is_vacuous_pass() -> None:
    """Every referenced layer skipped => (None, True) (vacuous pass)."""
    report = _report(_skipped_layer("gate"), _skipped_layer("rubric"))
    spec = _spec({"gate": 0.4, "rubric": 0.6}, fail=0.7)
    score, passed = weighted_verdict(report, spec)
    assert score is None
    assert passed is True


def test_mean_leaf_scores_skipped_layer_returns_none() -> None:
    """A skipped layer has no run leaves -> ``None`` from the mean helper."""
    skipped = _skipped_layer("rubric")
    assert _mean_leaf_scores(skipped) is None


def test_weighted_verdict_rejects_boolean_spec() -> None:
    spec = VerdictSpec(mode="boolean", ast=parse("gate"))
    with pytest.raises(ValueError, match="boolean"):
        weighted_verdict(_report(_layer("gate", _leaf("a", score=1.0))), spec)
