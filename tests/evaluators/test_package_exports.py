"""The evaluators package re-exports the core public API (SPEC prM §A/§C/§E)."""

from __future__ import annotations

import coding_agent_playbook.evaluators as pkg


def test_public_exports_present() -> None:
    expected = {
        "Scope",
        "Determinism",
        "Metric",
        "register_metric",
        "all_metrics",
        "static_metrics",
        "execution_metrics",
        "get_metric",
        "AbsoluteThreshold",
        "RegressionPolicy",
        "Measurement",
        "EvaluationReport",
        "EvalContext",
        "ResolvedPolicy",
        "GradePolicy",
        "parse_module",
        "ModuleModel",
    }
    assert expected <= set(pkg.__all__)
    for name in expected:
        assert hasattr(pkg, name), name


def test_dead_evaluator_symbols_are_gone() -> None:
    """The retired ``Evaluator`` world is no longer importable from the package."""
    for name in (
        "Evaluator",
        "register_evaluator",
        "all_evaluators",
        "static_evaluators",
        "deterministic_evaluators",
        "get_evaluator",
        "ValueKind",
        "Finding",
    ):
        assert name not in set(pkg.__all__), name
        assert not hasattr(pkg, name), name
