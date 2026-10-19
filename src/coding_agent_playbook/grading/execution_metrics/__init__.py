"""Execution metrics (SPEC prM §B2, Track M4; prK §F.1.1).

Deterministic metrics that need a **runnable project**: ``test_pass_rate`` and
``coverage`` shell out to the target's ``pytest``/``pytest-cov`` (no playbook
dependency) and parse the standard junit + Cobertura XML with stdlib
``xml.etree``; ``diff_coverage`` scores the changed lines of that same run.
Deliberately empty: import the defining module. ``test_pass``, ``coverage`` and
``diff_coverage`` each register their metric with ``@register_metric`` when
``grading.metric`` imports them; ``project`` runs the suite once and ``junit``,
``coverage_xml`` and ``git_diff`` parse what it leaves. All are
``needs_project=True`` so ``static_metrics()`` excludes them; they only run under
``--run-tests``.
"""
