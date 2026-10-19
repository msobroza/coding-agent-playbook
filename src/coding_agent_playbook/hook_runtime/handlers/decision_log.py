"""guard-decision-log: the decision sink (specs/prK-hook-pack.md §E.5, specs/prK-lifecycle-hooks.md §D.6.2).

The log itself is written by the dispatcher, in pipeline step 8, through
``hook_runtime._decision_log`` (one line per non-``none`` decision, escape and
degraded event, ids and flags only). This builtin is the switch: its hook's
presence renders ``guard_config.logging.decisions = true``. It is a **sink**
(``routing.DECISION_SINK_HANDLERS``): no registration of its own, no share of
any §D.4 deadline, never selected into a fan-out, so it receives decisions and
can never return one. It is registered so validate (H6) reads its declaration
like any builtin's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hook_runtime.registry import register_hook_handler

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.dispatch.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.registry import HandlerContext

__all__ = ["decision_log"]


@register_hook_handler(
    "decision_log", events=[event.value for event in EventName], decisions=["none"]
)
def decision_log(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Never called by the dispatcher (a sink); a direct call decides nothing.

    Example: ``decision_log(ev, ctx) is None``.
    """
    del ev, ctx
    return None
