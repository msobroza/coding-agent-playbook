"""Code-quality evaluator subsystem (SPEC prM).

A rubric criterion, a code metric, a coverage number, and a test-pass rate are
all the same thing: a *graded measurement over a scope*. This package provides
the single :class:`~coding_agent_playbook.evaluators.registry.Evaluator`
abstraction, the static builtin metric evaluators, and — in the
:class:`~coding_agent_playbook.evaluators.metric.Metric` /
:class:`~coding_agent_playbook.evaluators.check.Check` /
:class:`~coding_agent_playbook.evaluators.rubric.Rubric` stack — the
:meth:`~coding_agent_playbook.evaluators.rubric.Rubric.evaluate` aggregator (gate
+ weighted composite) that superseded the retired ``grade()``. See
``specs/prM-code-metrics.md`` §A-§E.
"""

from __future__ import annotations

from coding_agent_playbook.evaluators.parse import ModuleModel, parse_module
from coding_agent_playbook.evaluators.registry import (
    Evaluator,
    all_evaluators,
    deterministic_evaluators,
    get_evaluator,
    register_evaluator,
    static_evaluators,
)
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    EvalContext,
    EvaluationReport,
    Finding,
    GradePolicy,
    JudgeLike,
    Measurement,
    MetricConfig,
    RegressionPolicy,
    ResolvedPolicy,
)

__all__ = [
    "AbsoluteThreshold",
    "Determinism",
    "EvalContext",
    "EvaluationReport",
    "Evaluator",
    "Finding",
    "GradePolicy",
    "JudgeLike",
    "Measurement",
    "MetricConfig",
    "ModuleModel",
    "RegressionPolicy",
    "ResolvedPolicy",
    "Scope",
    "ValueKind",
    "all_evaluators",
    "deterministic_evaluators",
    "get_evaluator",
    "parse_module",
    "register_evaluator",
    "static_evaluators",
]
