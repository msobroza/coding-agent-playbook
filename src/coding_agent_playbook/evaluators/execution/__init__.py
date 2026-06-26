"""Execution evaluators (SPEC prM §B2, Track M4).

Deterministic metrics that need a **runnable project**: ``test_pass_rate`` and
``coverage`` shell out to the target's ``pytest``/``pytest-cov`` (no playbook
dependency) and parse the standard junit + Cobertura XML with stdlib
``xml.etree``. Importing this package fires each module's ``@register_evaluator``
decorator (mirroring ``builtins/__init__``), so the registry sees both execution
evaluators without an explicit list. Both are ``needs_project=True`` so
``static_evaluators()`` excludes them; they only run under ``--run-tests``.
"""

from __future__ import annotations

from coding_agent_playbook.evaluators.execution import (  # noqa: F401
    coverage,
    test_pass,
)
