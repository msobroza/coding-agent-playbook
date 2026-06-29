"""Tests for the task compiler (Track C6).

The task compiler turns the parsed ``[gate]``/``[rubric]``/``[verdict]`` blocks
into a per-trial evaluation structure: a
:class:`~coding_agent_playbook.evaluators.rubric.Rubric` carrying the two named
layer checks (``id="gate"`` / ``id="rubric"``) plus a *derived* verdict AST. The
verdict is computed as a boolean function over the two layers' ``passed`` results
- gate and rubric each run **once** (as the rubric's two checks); the verdict
does **not** re-run them, so the judge / test suite is never double-invoked.

These tests drive :func:`compile_task` (layer composition, the single-handle
default-expr rule, the at-least-one-layer + verdict-name-subset validation),
:func:`verdict_passed` (derive the trial verdict over a report), and
:func:`over_boolean` (the aggregate ``over`` selector), plus an end-to-end run of
the compiled per-trial rubric over a real file fixture + a ``StubJudge``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals._compile import (
    CompiledTask,
    VerdictSpec,
    compile_task,
    over_boolean,
    verdict_passed,
)
from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.evaluators.check import MeasurementSet
from coding_agent_playbook.evaluators.rubric import Rubric
from coding_agent_playbook.evaluators.scope import CostTier, Determinism
from coding_agent_playbook.evaluators.types import (
    CheckResult,
    EvalContext,
    EvaluationReport,
)

if TYPE_CHECKING:
    from pathlib import Path

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

_GATE_BIND = {"build": {"check": "file_exists", "path": "x.py"}}
_RUBRIC_BIND = {"quality": {"rubric": [{"judge": "a", "weight": 1.0}], "fail": 0.5}}


def _result(check_id: str, *, passed: bool) -> CheckResult:
    """A minimal :class:`CheckResult` row for a synthetic report."""
    return CheckResult(
        check_id=check_id,
        passed=passed,
        score=1.0 if passed else 0.0,
        weight=0.0,
        required=True,
        determinism=Determinism.DETERMINISTIC,
        cost=CostTier.DETERMINISTIC,
        status="run",
    )


def _report(*results: CheckResult) -> EvaluationReport:
    return EvaluationReport(
        findings=[],
        warn_count=0,
        fail_count=0,
        composite=None,
        passed=all(r.passed for r in results),
        checks=list(results),
    )


# --------------------------------------------------------------------------- #
# compile_task: gate + rubric layers, default verdict
# --------------------------------------------------------------------------- #


def test_compile_task_builds_two_named_layer_checks() -> None:
    compiled = compile_task(
        gate_bind=_GATE_BIND,
        gate_expr="build",
        rubric_bind=_RUBRIC_BIND,
        rubric_expr="quality",
        name="t1",
    )
    assert isinstance(compiled, CompiledTask)
    assert isinstance(compiled.per_trial, Rubric)
    assert compiled.per_trial.name == "t1"
    ids = [c.id for c in compiled.per_trial.checks]
    assert ids == ["gate", "rubric"]
    assert compiled.layers == frozenset({"gate", "rubric"})


def test_compile_task_default_verdict_is_gate_and_rubric() -> None:
    compiled = compile_task(
        gate_bind=_GATE_BIND,
        gate_expr="build",
        rubric_bind=_RUBRIC_BIND,
        rubric_expr="quality",
    )
    # default verdict "gate and rubric" => both layers required for the trial.
    assert compiled.verdict_spec.mode == "boolean"
    assert (
        verdict_passed(
            _report(_result("gate", passed=True), _result("rubric", passed=True)),
            compiled.verdict_ast,
        )
        is True
    )
    assert (
        verdict_passed(
            _report(_result("gate", passed=True), _result("rubric", passed=False)),
            compiled.verdict_ast,
        )
        is False
    )


# --------------------------------------------------------------------------- #
# compile_task: weighted-verdict spec (C10)
# --------------------------------------------------------------------------- #


def test_compile_task_with_weighted_verdict_builds_a_weighted_spec() -> None:
    compiled = compile_task(
        gate_bind=_GATE_BIND,
        gate_expr="build",
        rubric_bind=_RUBRIC_BIND,
        rubric_expr="quality",
        verdict_weights={"gate": 0.4, "rubric": 0.6},
        verdict_fail=0.7,
        verdict_warn=0.85,
    )
    assert isinstance(compiled.verdict_spec, VerdictSpec)
    assert compiled.verdict_spec.mode == "weighted"
    assert compiled.verdict_spec.weights == {"gate": 0.4, "rubric": 0.6}
    assert compiled.verdict_spec.fail == 0.7
    assert compiled.verdict_spec.warn == 0.85


def test_compile_task_boolean_verdict_spec_keeps_today_shape() -> None:
    compiled = compile_task(
        gate_bind=_GATE_BIND,
        gate_expr="build",
        verdict_trial="gate",
    )
    assert compiled.verdict_spec.mode == "boolean"
    assert compiled.verdict_spec.weights is None
    assert compiled.verdict_spec.fail is None


def test_compile_task_rejects_both_trial_and_weights() -> None:
    with pytest.raises(ValueError, match="cannot set both"):
        compile_task(
            gate_bind=_GATE_BIND,
            gate_expr="build",
            rubric_bind=_RUBRIC_BIND,
            rubric_expr="quality",
            verdict_trial="gate and rubric",
            verdict_weights={"gate": 0.4, "rubric": 0.6},
            verdict_fail=0.5,
        )


def test_compile_task_rejects_unknown_layer_in_weights() -> None:
    """Weighted weights must be a subset of the present layers."""
    with pytest.raises(ValueError, match="unknown layer"):
        compile_task(
            gate_bind=_GATE_BIND,
            gate_expr="build",
            # No [rubric], yet weights mention it.
            verdict_weights={"gate": 0.4, "rubric": 0.6},
            verdict_fail=0.5,
        )


def test_compile_task_rejects_weights_not_summing_to_one() -> None:
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        compile_task(
            gate_bind=_GATE_BIND,
            gate_expr="build",
            rubric_bind=_RUBRIC_BIND,
            rubric_expr="quality",
            verdict_weights={"gate": 0.3, "rubric": 0.5},
            verdict_fail=0.5,
        )


def test_compile_task_rejects_weighted_without_fail() -> None:
    with pytest.raises(ValueError, match="requires 'fail'"):
        compile_task(
            gate_bind=_GATE_BIND,
            gate_expr="build",
            rubric_bind=_RUBRIC_BIND,
            rubric_expr="quality",
            verdict_weights={"gate": 0.4, "rubric": 0.6},
        )


# --------------------------------------------------------------------------- #
# default-expr rule: single handle defaults; multi-handle no-expr raises
# --------------------------------------------------------------------------- #


def test_single_handle_layer_defaults_to_that_handle() -> None:
    # gate has exactly one handle and no expr => the expr defaults to "build".
    compiled = compile_task(gate_bind=_GATE_BIND, gate_expr=None, verdict_trial="gate")
    (gate_check,) = compiled.per_trial.checks
    assert gate_check.id == "gate"
    assert compiled.layers == frozenset({"gate"})


def test_multi_handle_layer_with_no_expr_raises() -> None:
    bind = {
        "build": {"check": "file_exists", "path": "x.py"},
        "lint": {"check": "file_exists", "path": "y.py"},
    }
    with pytest.raises(ValueError, match="compose"):
        compile_task(gate_bind=bind, gate_expr=None, verdict_trial="gate")


# --------------------------------------------------------------------------- #
# layer presence: gate-only works; missing-layer verdict name raises
# --------------------------------------------------------------------------- #


def test_gate_only_task_with_gate_verdict() -> None:
    compiled = compile_task(gate_bind=_GATE_BIND, gate_expr="build", verdict_trial="gate")
    ids = [c.id for c in compiled.per_trial.checks]
    assert ids == ["gate"]
    assert compiled.layers == frozenset({"gate"})


def test_gate_only_task_with_default_verdict_mentioning_rubric_raises() -> None:
    # default verdict "gate and rubric" mentions "rubric" but there is no [rubric].
    with pytest.raises(ValueError, match="rubric"):
        compile_task(gate_bind=_GATE_BIND, gate_expr="build")


def test_no_layer_at_all_raises() -> None:
    with pytest.raises(ValueError, match="at least one"):
        compile_task()


# --------------------------------------------------------------------------- #
# verdict_passed: derive the trial verdict over a report's check results
# --------------------------------------------------------------------------- #


def test_verdict_passed_and_is_false_when_rubric_fails() -> None:
    report = _report(_result("gate", passed=True), _result("rubric", passed=False))
    compiled = compile_task(
        gate_bind=_GATE_BIND,
        gate_expr="build",
        rubric_bind=_RUBRIC_BIND,
        rubric_expr="quality",
        verdict_trial="gate and rubric",
    )
    assert verdict_passed(report, compiled.verdict_ast) is False


def test_verdict_passed_or_is_true_when_one_layer_passes() -> None:
    report = _report(_result("gate", passed=True), _result("rubric", passed=False))
    compiled = compile_task(
        gate_bind=_GATE_BIND,
        gate_expr="build",
        rubric_bind=_RUBRIC_BIND,
        rubric_expr="quality",
        verdict_trial="gate or rubric",
    )
    assert verdict_passed(report, compiled.verdict_ast) is True


# --------------------------------------------------------------------------- #
# over_boolean: the aggregate "over" selector
# --------------------------------------------------------------------------- #


def test_over_boolean_reads_named_layer() -> None:
    report = _report(_result("gate", passed=True), _result("rubric", passed=False))
    assert over_boolean("gate", report, verdict=False) is True
    assert over_boolean("rubric", report, verdict=False) is False


def test_over_boolean_verdict_reads_passed_in_bool() -> None:
    report = _report(_result("gate", passed=False))
    assert over_boolean("verdict", report, verdict=True) is True
    assert over_boolean("verdict", report, verdict=False) is False


def test_over_boolean_unknown_raises() -> None:
    report = _report(_result("gate", passed=True))
    with pytest.raises(ValueError, match="over"):
        over_boolean("bogus", report, verdict=True)


def test_over_boolean_missing_layer_raises() -> None:
    # "rubric" requested but the report has no rubric check.
    report = _report(_result("gate", passed=True))
    with pytest.raises(ValueError, match="rubric"):
        over_boolean("rubric", report, verdict=True)


# --------------------------------------------------------------------------- #
# End-to-end: build the compiled per-trial Rubric and evaluate it for real.
# --------------------------------------------------------------------------- #

# The rubric-group handle is a ThresholdCheck over a nested Rubric (a Metric); the
# ThresholdCheck grades a *pre-built* MeasurementSet, so the rubric's composite
# must be measured into ``candidate_measurements`` up front (the C8 aggregate layer
# / runner does this). These helpers mirror that wiring inside the test.
_E2E_RUBRIC_BIND = {"quality": {"rubric": [{"judge": "a", "weight": 1.0}], "fail": 0.5}}


def _measured_ctx(tmp_path: Path, judge: StubJudge) -> tuple[EvalContext, MeasurementSet]:
    """A candidate tree + a ctx/MeasurementSet with the rubric composite pre-measured."""
    from coding_agent_playbook.evals._handles import build_handles

    (tmp_path / "x.py").write_text("print('hi')\n", encoding="utf-8")

    # Pre-measure the nested rubric metric (keys its composite on name "quality").
    rubric_metric = build_handles(_E2E_RUBRIC_BIND, layer="rubric")["quality"].metric  # type: ignore[attr-defined]
    measure_ctx = EvalContext(
        module=None, source="", label="e2e", judge=judge, artifact="ART", tree=tmp_path
    )
    candidate_measurements = list(rubric_metric.measure(measure_ctx))

    ctx = EvalContext(
        module=None,
        source="",
        label="e2e",
        judge=judge,
        artifact="ART",
        tree=tmp_path,
        candidate_measurements=candidate_measurements,
    )
    return ctx, MeasurementSet(candidate_measurements, None)


def test_compiled_per_trial_evaluates_end_to_end(tmp_path: Path) -> None:
    # file_exists runs over the real tree; the StubJudge scores the rubric high.
    compiled = compile_task(
        gate_bind=_GATE_BIND,
        gate_expr="build",
        rubric_bind=_E2E_RUBRIC_BIND,
        rubric_expr="quality",
        name="e2e",
    )
    ctx, ms = _measured_ctx(tmp_path, StubJudge({"a": 0.9}))
    report = compiled.per_trial.evaluate(ctx, ms)

    by_id = {c.check_id: c for c in report.checks}
    assert set(by_id) == {"gate", "rubric"}
    assert by_id["gate"].passed is True  # x.py exists
    assert by_id["rubric"].passed is True  # composite 0.9 >= 0.5 floor
    assert verdict_passed(report, compiled.verdict_ast) is True


def test_compiled_per_trial_verdict_false_when_rubric_fails(tmp_path: Path) -> None:
    compiled = compile_task(
        gate_bind=_GATE_BIND,
        gate_expr="build",
        rubric_bind=_E2E_RUBRIC_BIND,
        rubric_expr="quality",
        name="e2e",
    )
    ctx, ms = _measured_ctx(tmp_path, StubJudge({"a": 0.1}))  # composite below 0.5
    report = compiled.per_trial.evaluate(ctx, ms)

    by_id = {c.check_id: c for c in report.checks}
    assert by_id["gate"].passed is True
    assert by_id["rubric"].passed is False
    assert verdict_passed(report, compiled.verdict_ast) is False
