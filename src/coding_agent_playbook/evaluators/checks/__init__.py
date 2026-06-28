"""Concrete :class:`~coding_agent_playbook.evaluators.check.Check` families.

The ``Check`` layer groups its concrete checks by family. T3 ships the
deterministic file checks (:mod:`coding_agent_playbook.evaluators.checks.files`),
the ``Check``-layer counterpart of the ``[expected]`` predicates; the metric-backed
:class:`~coding_agent_playbook.evaluators.check.ThresholdCheck` /
:class:`~coding_agent_playbook.evaluators.check.NonRegressionCheck` live in the
parent :mod:`coding_agent_playbook.evaluators.check` module. T4a adds the judged
check (:mod:`coding_agent_playbook.evaluators.checks.judged`) and the convenience
execution-check factories (:mod:`coding_agent_playbook.evaluators.checks.execution`).
T4b adds the boolean composers (:mod:`coding_agent_playbook.evaluators.checks.compose`:
``AllOf`` / ``AnyOf`` / ``Not``).

Track C2 adds the :class:`~coding_agent_playbook.evaluators.checks.judge_metric.JudgeMetric`
adapter and the Check **registry** (:mod:`coding_agent_playbook.evaluators.checks.registry`:
``register_check`` / ``get_check`` / ``all_check_ids``). Importing this package
fires each module's ``@register_check`` decorator (the file + execution checks) and
the ``threshold`` / ``non_regression`` factories defined in ``registry``.

This track is additive: nothing in the eval/task pipeline imports these yet.
"""

from __future__ import annotations

from coding_agent_playbook.evaluators.checks.compose import AllOf, AnyOf, Not
from coding_agent_playbook.evaluators.checks.execution import CoverageCheck, TestsPassCheck
from coding_agent_playbook.evaluators.checks.files import (
    FileContainsCheck,
    FileExistsCheck,
    FileForbiddenCheck,
    FileUnchangedCheck,
)

# Import order matters: the leaf check families (which carry the
# ``@register_check`` decorators) come first, then ``registry`` last so its own
# ``threshold`` / ``non_regression`` factories register without re-entering a
# half-initialized package.
from coding_agent_playbook.evaluators.checks.judge_metric import JudgeMetric
from coding_agent_playbook.evaluators.checks.judged import JudgeCheck
from coding_agent_playbook.evaluators.checks.registry import (
    all_check_ids,
    get_check,
    register_check,
)

__all__ = [
    "AllOf",
    "AnyOf",
    "CoverageCheck",
    "FileContainsCheck",
    "FileExistsCheck",
    "FileForbiddenCheck",
    "FileUnchangedCheck",
    "JudgeCheck",
    "JudgeMetric",
    "Not",
    "TestsPassCheck",
    "all_check_ids",
    "get_check",
    "register_check",
]
