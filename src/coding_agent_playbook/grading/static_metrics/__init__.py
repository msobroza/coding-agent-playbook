"""Static builtin metrics (SPEC prM §B): measured over a parsed module, no project run.

Deliberately empty: import the defining module. ``cyclomatic``, ``wmc``,
``lcom4``, ``dit``, ``cbo`` and ``maintainability`` (``maintainability_index``),
plus the opt-in ``ruff_violations``, ``file_sloc`` and ``docstring_example``
(prK §F.2-§F.3), each register their metric with ``@register_metric`` when
``grading.metric`` imports them. ``maintainability`` and ``file_sloc`` import
cleanly even when their optional ``radon`` dependency is absent (radon is
imported lazily inside ``_measure``), so registering them never breaks an
air-gapped install.
"""
