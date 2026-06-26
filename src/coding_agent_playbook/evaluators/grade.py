"""Grade measurements into a report: gate + weighted composite (SPEC prM §C).

:func:`grade` takes a candidate measurement set, an optional baseline, and a
:class:`~coding_agent_playbook.evaluators.types.GradePolicy`. For each candidate
measurement it resolves the *effective* policy (the evaluator's defaults,
overridden by config), matches the baseline by ``(evaluator, scope_key)``, and
decides a ``level``/``kind`` per the active mode. Two aggregates fall out: the
gate (``passed``) and the weighted ``composite`` over evaluators with
``weight > 0`` (static, execution, judged - uniformly).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.registry import get_evaluator
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    EvaluationReport,
    Finding,
    RegressionPolicy,
    ResolvedPolicy,
)

if TYPE_CHECKING:
    from coding_agent_playbook.evaluators.registry import Evaluator
    from coding_agent_playbook.evaluators.types import GradePolicy, Kind, Level, Measurement


def resolve_policy(evaluator: Evaluator, policy: GradePolicy) -> ResolvedPolicy:
    """Effective policy for one evaluator: defaults overridden by config."""
    absolute = policy.thresholds.get(evaluator.name, evaluator.default_absolute)
    regression = policy.regression.get(evaluator.name, evaluator.default_regression)
    weight = policy.weights.get(evaluator.name, evaluator.default_weight)
    return ResolvedPolicy(absolute=absolute, regression=regression, weight=weight)


def grade(
    candidate: list[Measurement],
    baseline: list[Measurement] | None,
    policy: GradePolicy,
) -> EvaluationReport:
    """Grade ``candidate`` against ``baseline`` under ``policy``."""
    baseline_index = _index(baseline or [])
    findings: list[Finding] = []
    weighted_scores: list[tuple[float, float]] = []  # (weight, score)

    for measurement in candidate:
        evaluator = get_evaluator(measurement.evaluator)
        resolved = resolve_policy(evaluator, policy)
        base_value = baseline_index.get((measurement.evaluator, measurement.scope_key))

        level, kind, bound = _decide(
            evaluator, measurement.value, base_value, resolved, policy.mode
        )
        score = evaluator.to_score(measurement.value, resolved)
        findings.append(
            Finding(
                evaluator=measurement.evaluator,
                scope_key=measurement.scope_key,
                value=measurement.value,
                baseline=base_value,
                bound=bound,
                score=score,
                level=level,
                kind=kind,
            )
        )
        if resolved.weight > 0:
            weighted_scores.append((resolved.weight, score))

    warn_count = sum(1 for f in findings if f.level == "warn")
    fail_count = sum(1 for f in findings if f.level == "fail")
    passed = fail_count == 0 and not (policy.strict and warn_count > 0)
    composite = _composite(weighted_scores)

    return EvaluationReport(
        findings=findings,
        warn_count=warn_count,
        fail_count=fail_count,
        composite=composite,
        passed=passed,
    )


def _index(measurements: list[Measurement]) -> dict[tuple[str, str], float]:
    return {(m.evaluator, m.scope_key): m.value for m in measurements}


def _decide(
    evaluator: Evaluator,
    value: float,
    base_value: float | None,
    resolved: ResolvedPolicy,
    mode: str,
) -> tuple[Level, Kind, float | None]:
    """Decide ``(level, kind, bound)`` for one measurement under ``mode``."""
    is_new = base_value is None

    # New scopes always fall back to absolute (kind="new").
    if is_new:
        level, bound = _absolute_level(evaluator, value, resolved.absolute)
        return level, "new", bound

    reg_failed = _regressed(evaluator, value, base_value, resolved.regression)
    abs_level, abs_bound = _absolute_level(evaluator, value, resolved.absolute)

    if mode == "regression":
        return ("fail", "regression", None) if reg_failed else ("ok", "regression", None)
    if mode == "absolute":
        return abs_level, "absolute", abs_bound
    # both: regression takes precedence as a failure, then absolute.
    if reg_failed:
        return "fail", "regression", None
    return abs_level, "absolute", abs_bound


def _regressed(
    evaluator: Evaluator,
    value: float,
    base_value: float | None,
    regression: RegressionPolicy,
) -> bool:
    if base_value is None:
        return False
    worsening = (value - base_value) if evaluator.higher_is_worse else (base_value - value)
    return worsening > regression.max_worsening


def _absolute_level(
    evaluator: Evaluator,
    value: float,
    absolute: AbsoluteThreshold,
) -> tuple[Level, float | None]:
    """Absolute warn/fail level + the bound that decided it."""
    if evaluator.higher_is_worse:
        if absolute.fail is not None and value >= absolute.fail:
            return "fail", absolute.fail
        if absolute.warn is not None and value >= absolute.warn:
            return "warn", absolute.warn
        return "ok", None
    # higher is better: breach when the value drops *below* the bound.
    if absolute.fail is not None and value <= absolute.fail:
        return "fail", absolute.fail
    if absolute.warn is not None and value <= absolute.warn:
        return "warn", absolute.warn
    return "ok", None


def _composite(weighted_scores: list[tuple[float, float]]) -> float | None:
    total_weight = sum(weight for weight, _ in weighted_scores)
    if total_weight <= 0:
        return None
    return sum(weight * score for weight, score in weighted_scores) / total_weight
