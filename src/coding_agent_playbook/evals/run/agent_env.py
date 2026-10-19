"""The child env the real eval runners spawn an agent with (specs/prK-lifecycle-hooks.md P-D2).

An eval run has nobody to answer a lifecycle hook's ``ask`` prompt. The runners
therefore mark the agent's env unattended, and the hook runtime degrades ``ask``
to ``deny`` deterministically instead of prompting or hanging until the run's
timeout. Both real runners share this one helper so they cannot drift apart.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Shared name with the hook runtime (§D.3.6). The runtime may not import
#: ``evals``, so it re-declares the name; K2 adds a cross-module equality test.
UNATTENDED_ENV_VAR = "PLAYBOOK_HOOK_UNATTENDED"


def unattended_agent_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """A copy of ``base`` (default: ``os.environ``) with the unattended flag forced to ``"1"``.

    The parent env is kept whole (``PATH``, credentials, proxies) because the
    agent CLI needs it; only the flag is added or overridden.

    Example::

        >>> unattended_agent_env({"PATH": "/usr/bin"})
        {'PATH': '/usr/bin', 'PLAYBOOK_HOOK_UNATTENDED': '1'}
    """
    source = os.environ if base is None else base
    return {**source, UNATTENDED_ENV_VAR: "1"}
