"""Private forward-reference shims for the public ABCs.

PR 1 declared the Adapter / ArtifactSource / StateSource ABCs before the
canonical types existed. As each type lands, this module re-exports it so the
ABC modules never have to change:

- ``Rule`` / ``Prompt`` / ``Skill`` -> ``coding_agent_playbook.types`` (PR 2)
- ``Config`` / ``Lockfile``         -> placeholders until PR 5
- ``EvalTask``                      -> ``coding_agent_playbook.evals.task`` (PR 11)

Everything lives under ``TYPE_CHECKING``: this module has no runtime symbols,
and nothing imports from it at runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    from coding_agent_playbook.evals.task import EvalTask as EvalTask
    from coding_agent_playbook.types import Prompt as Prompt
    from coding_agent_playbook.types import Rule as Rule
    from coding_agent_playbook.types import Skill as Skill

    Config = Any
    Lockfile = Any
