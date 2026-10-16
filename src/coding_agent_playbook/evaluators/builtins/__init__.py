"""Static builtin metrics (SPEC prM §B).

Importing this package fires each module's ``@register_metric`` decorator, so
the registry sees ``cyclomatic_complexity``, ``wmc``, ``lcom4``, ``dit``, ``cbo``
and ``maintainability_index``, plus the opt-in ``ruff_violations``,
``file_sloc`` and ``docstring_example`` (prK §F.2-§F.3), without any explicit
list. ``maintainability`` and ``file_sloc`` import cleanly even when their
optional ``radon`` dependency is absent (radon is imported lazily inside
``_measure``), so registering them here never breaks an air-gapped install.
"""

from __future__ import annotations

from coding_agent_playbook.evaluators.builtins import (  # noqa: F401
    cbo,
    cyclomatic,
    dit,
    docstring_example,
    file_sloc,
    lcom4,
    maintainability,
    ruff_violations,
    wmc,
)
