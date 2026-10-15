"""How each adapter carries an on hook: the one label set (specs/prK-lifecycle-hooks.md §A.8, §C.5.1).

``playbook check`` prints it per hook and per enabled adapter, and the sync
summary counts it, so a reader always sees where a guard is a boundary and
where it is only advice (QC-10):

- ``enforced``: every declared event is native on the adapter;
- ``degraded``: registered there, but weaker (an evidence-only or unreachable
  event, or a tool class the harness has no tool for);
- ``advisory``: only the advisory text reaches it;
- ``—``: nothing is rendered for it (no native event, no advisory text).

Stdlib-only, like the rest of ``hook_policy``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_policy.tables import DEGRADED_EVENTS, TOOL_CLASS_NAMES

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_policy.resolved import ResolvedHook

__all__ = ["HOOK_LABELS", "HookLabel", "adapter_label"]

HookLabel = Literal["enforced", "degraded", "advisory", "—"]
#: Every label, in the order a summary lists them.
HOOK_LABELS: Final[tuple[HookLabel, ...]] = ("enforced", "degraded", "advisory", "—")

_TOOL_EVENTS: Final = frozenset({"pre_tool_use", "post_tool_use", "post_tool_use_failure"})


def adapter_label(
    hook: ResolvedHook,
    adapter: str,
    hook_support: Mapping[str, frozenset[str]],
    *,
    degraded: Mapping[str, frozenset[str]] = DEGRADED_EVENTS,
) -> HookLabel:
    """The label of ``hook`` on ``adapter``, whose class declares ``hook_support``.

    ``hook.supports`` is already narrowed to the adapters that receive hooks
    (``[hooks] adapters``), so a hook-capable adapter left out of it only gets
    the advisory text.

    Example::

        >>> adapter_label(hook, "claude_code", ClaudeCodeAdapter.hook_support)  # doctest: +SKIP
        'enforced'
    """
    reachable = [event for event in hook.events if event in hook_support]
    if adapter in hook.supports and reachable:
        weak = (
            len(reachable) < len(hook.events)
            or any(event in degraded.get(adapter, frozenset()) for event in reachable)
            or _lacks_a_tool(hook, adapter, reachable)
        )
        return "degraded" if weak else "enforced"
    return "—" if hook.advisory is None else "advisory"


def _lacks_a_tool(hook: ResolvedHook, adapter: str, events: list[str]) -> bool:
    """Whether a tool event matches a tool class the harness has no tool for (§A.2)."""
    tool_classes = {
        tool_class
        for event in events
        if event in _TOOL_EVENTS and event in hook.matcher
        for tool_class in hook.matcher[event].tools
    }
    return any(not TOOL_CLASS_NAMES.get(name, {}).get(adapter, ()) for name in tool_classes)
