"""The evaluators package re-exports the core public API (SPEC prM §A/§C/§E)."""

from __future__ import annotations

import coding_agent_playbook.evaluators as pkg


def test_public_exports_present() -> None:
    expected = {
        "Scope",
        "ValueKind",
        "Determinism",
        "Evaluator",
        "register_evaluator",
        "all_evaluators",
        "static_evaluators",
        "deterministic_evaluators",
        "get_evaluator",
        "AbsoluteThreshold",
        "RegressionPolicy",
        "Measurement",
        "Finding",
        "EvaluationReport",
        "MetricConfig",
        "EvalContext",
        "ResolvedPolicy",
        "GradePolicy",
        "grade",
        "parse_module",
        "ModuleModel",
    }
    assert expected <= set(pkg.__all__)
    for name in expected:
        assert hasattr(pkg, name), name
