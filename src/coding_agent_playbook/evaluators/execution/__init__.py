"""Execution metrics (SPEC prM §B2, Track M4; prK §F.1.1).

Deterministic metrics that need a **runnable project**: ``test_pass_rate`` and
``coverage`` shell out to the target's ``pytest``/``pytest-cov`` (no playbook
dependency) and parse the standard junit + Cobertura XML with stdlib
``xml.etree``; ``diff_coverage`` scores the changed lines of that same run.
Importing this package fires each module's ``@register_metric`` decorator
(mirroring ``builtins/__init__``), so the registry sees every execution metric
without an explicit list. All are ``needs_project=True`` so ``static_metrics()``
excludes them; they only run under ``--run-tests``.
"""

from __future__ import annotations

from coding_agent_playbook.evaluators.execution import (  # noqa: F401
    coverage,
    diff_coverage,
    test_pass,
)
