"""Static builtin evaluators (SPEC prM §B).

Importing this package fires each module's ``@register_evaluator`` decorator, so
the registry sees ``cyclomatic_complexity``, ``wmc``, ``lcom4``, ``dit`` and
``cbo`` without any explicit list.
"""

from __future__ import annotations

from coding_agent_playbook.evaluators.builtins import (  # noqa: F401
    cbo,
    cyclomatic,
    dit,
    lcom4,
    wmc,
)
