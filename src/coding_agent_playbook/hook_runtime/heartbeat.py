"""The guard heartbeat line the model sees at session start (specs/prK-hook-pack.md §E.1).

``PLAYBOOK-GUARDS: OK <n>`` says the dispatcher ran and ``n`` guards passed
their in-process canary; ``GUARDRAILS DEGRADED: <which>`` names what did not.
The ``.claude/CLAUDE.md`` carrier line tells the model to warn the user when
neither appears, so a dead runtime is caught by the line's absence.

A leaf module (``caps`` only): the session-start briefing builds the line, and
the dispatcher's config-fault path (``_faults``), which runs before any hook
can, reports ``DEGRADED: config`` with the same wording.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import clip

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["DEGRADED_PREFIX", "HEARTBEAT_MAX_CHARS", "OK_PREFIX", "degraded_line", "ok_line"]

#: The heartbeat line is always at most this long (§E.0.5 session-start caps).
HEARTBEAT_MAX_CHARS: Final = 40
OK_PREFIX: Final = "PLAYBOOK-GUARDS: OK"
DEGRADED_PREFIX: Final = "GUARDRAILS DEGRADED:"


def ok_line(proven: int) -> str:
    """The healthy heartbeat: ``proven`` guards answered their canary as expected.

    Example::

        >>> ok_line(2)
        'PLAYBOOK-GUARDS: OK 2'
    """
    return f"{OK_PREFIX} {proven}"


def degraded_line(which: Iterable[str]) -> str:
    """The degraded heartbeat naming ``which`` parts failed, clipped to 40 characters.

    Example::

        >>> degraded_line(["config"])
        'GUARDRAILS DEGRADED: config'
    """
    return clip(f"{DEGRADED_PREFIX} {', '.join(which)}", HEARTBEAT_MAX_CHARS)
