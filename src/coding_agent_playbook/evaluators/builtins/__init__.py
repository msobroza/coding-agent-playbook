"""Static builtin metrics (SPEC prM §B).

Importing this package fires each module's ``@register_metric`` decorator, so
the registry sees ``cyclomatic_complexity``, ``wmc``, ``lcom4``, ``dit``, ``cbo``
and ``maintainability_index`` without any explicit list. ``maintainability``
imports cleanly even when its optional ``radon`` dependency is absent (radon is
imported lazily inside ``_measure``), so registering it here never breaks an
air-gapped install.
"""

from __future__ import annotations

from coding_agent_playbook.evaluators.builtins import (  # noqa: F401
    cbo,
    cyclomatic,
    dit,
    lcom4,
    maintainability,
    wmc,
)
