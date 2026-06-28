"""Concrete :class:`~coding_agent_playbook.evaluators.check.Check` families.

The ``Check`` layer groups its concrete checks by family. T3 ships the
deterministic file checks (:mod:`coding_agent_playbook.evaluators.checks.files`),
the ``Check``-layer counterpart of the ``[expected]`` predicates; the metric-backed
:class:`~coding_agent_playbook.evaluators.check.ThresholdCheck` /
:class:`~coding_agent_playbook.evaluators.check.NonRegressionCheck` live in the
parent :mod:`coding_agent_playbook.evaluators.check` module. T4a adds the judged
check (:mod:`coding_agent_playbook.evaluators.checks.judged`) and the convenience
execution-check factories (:mod:`coding_agent_playbook.evaluators.checks.execution`).

This track is additive: nothing imports these yet outside the new tests.
"""

from __future__ import annotations

from coding_agent_playbook.evaluators.checks.execution import CoverageCheck, TestsPassCheck
from coding_agent_playbook.evaluators.checks.files import (
    FileContainsCheck,
    FileExistsCheck,
    FileForbiddenCheck,
    FileUnchangedCheck,
)
from coding_agent_playbook.evaluators.checks.judged import JudgeCheck

__all__ = [
    "CoverageCheck",
    "FileContainsCheck",
    "FileExistsCheck",
    "FileForbiddenCheck",
    "FileUnchangedCheck",
    "JudgeCheck",
    "TestsPassCheck",
]
