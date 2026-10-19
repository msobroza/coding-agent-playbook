"""Code-quality evaluator subsystem (SPEC prM).

A rubric criterion, a code metric, a coverage number, and a test-pass rate are
all the same thing: a *graded measurement over a scope*. This package provides
the :class:`~coding_agent_playbook.evaluators.metric.Metric` (measure) /
:class:`~coding_agent_playbook.evaluators.check.Check` (grade) /
:class:`~coding_agent_playbook.evaluators.rubric.Rubric` (aggregate) stack — the
static builtin metrics plus the
:meth:`~coding_agent_playbook.evaluators.rubric.Rubric.evaluate` aggregator (gate
+ weighted composite). See ``specs/prM-code-metrics.md`` §A-§E.
"""

from __future__ import annotations

from coding_agent_playbook.evaluators.metric import (
    Metric,
    all_metrics,
    execution_metrics,
    get_metric,
    register_metric,
    static_metrics,
)
from coding_agent_playbook.evaluators.parse import ModuleModel, parse_module
from coding_agent_playbook.evaluators.rubric import Rubric
from coding_agent_playbook.evaluators.rubrics import (
    all_rubric_names,
    get_rubric,
    register_rubric,
)
from coding_agent_playbook.evaluators.scope import Determinism, Scope
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    EvalContext,
    EvaluationReport,
    GradePolicy,
    JudgeLike,
    Measurement,
    RegressionPolicy,
    ResolvedPolicy,
    TrialResult,
)

__all__ = [
    "AbsoluteThreshold",
    "Determinism",
    "EvalContext",
    "EvaluationReport",
    "GradePolicy",
    "JudgeLike",
    "Measurement",
    "Metric",
    "ModuleModel",
    "RegressionPolicy",
    "ResolvedPolicy",
    "Rubric",
    "Scope",
    "TrialResult",
    "all_metrics",
    "all_rubric_names",
    "execution_metrics",
    "get_metric",
    "get_rubric",
    "parse_module",
    "register_metric",
    "register_rubric",
    "static_metrics",
]
