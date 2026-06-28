"""Concrete :class:`~coding_agent_playbook.evaluators.check.Check` families (T3).

The ``Check`` layer groups its concrete checks by family. T3 ships the
deterministic file checks (:mod:`coding_agent_playbook.evaluators.checks.files`),
the ``Check``-layer counterpart of the ``[expected]`` predicates; the metric-backed
:class:`~coding_agent_playbook.evaluators.check.ThresholdCheck` /
:class:`~coding_agent_playbook.evaluators.check.NonRegressionCheck` live in the
parent :mod:`coding_agent_playbook.evaluators.check` module. Later tracks add the
judge and execution check families here.

This track is additive: nothing imports these yet outside the new tests.
"""

from __future__ import annotations

from coding_agent_playbook.evaluators.checks.files import (
    FileContainsCheck,
    FileExistsCheck,
    FileForbiddenCheck,
    FileUnchangedCheck,
)

__all__ = [
    "FileContainsCheck",
    "FileExistsCheck",
    "FileForbiddenCheck",
    "FileUnchangedCheck",
]
