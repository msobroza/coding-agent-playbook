"""Which hooks run on an event, and in what order (specs/prK-lifecycle-hooks.md §D.3.2).

A hook in ``guard_config.hooks`` is selected when the event is in its
``events``, the harness is in its ``supports``, ``PLAYBOOK_HOOKS_DISABLE``
does not name it (a ``mandatory`` hook ignores that list) and its
``matcher.<event>`` accepts the event. Sync already applied the on-formula
and ``applies_if``, so the runtime never evaluates them.

The order is ``(class rank, priority, id)``: guards before quality hooks, so
the first guard deny can short-circuit before a feedback hook spends its
budget, and never dict order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coding_agent_playbook.hook_runtime.event import EventName, ToolClass
from coding_agent_playbook.hook_runtime.policy import CLASS_RANK, failure_class

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.hook_runtime._hook_records import MatcherSpec
    from coding_agent_playbook.hook_runtime.config import GuardConfig, HookRecord
    from coding_agent_playbook.hook_runtime.escape import EscapeHatches
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.policy import FailureClass, OnError

__all__ = ["Selected", "Selection", "matcher_accepts", "select_hooks"]


@dataclass(frozen=True, slots=True)
class Selected:
    """One hook that runs on this event, with its per-event failure class."""

    record: HookRecord
    on_error: OnError
    failure_class: FailureClass

    @property
    def is_guard(self) -> bool:
        """Guard-class hooks ask (or deny) on failure; their first deny ends the fan-out."""
        return self.failure_class != "quality"


@dataclass(frozen=True, slots=True)
class Selection:
    """The hooks to run, in order, and those ``PLAYBOOK_HOOKS_DISABLE`` skipped."""

    selected: tuple[Selected, ...]
    disabled: tuple[str, ...] = ()


def select_hooks(cfg: GuardConfig, ev: CanonicalEvent, hatches: EscapeHatches) -> Selection:
    """The hooks of ``cfg`` that run on ``ev``, ordered by ``(class rank, priority, id)``.

    Example::

        >>> [s.record.id for s in select_hooks(cfg, ev, EscapeHatches()).selected]  # doctest: +SKIP
        ['guard-generated-outputs', 'ruff-feedback']
    """
    chosen: list[Selected] = []
    disabled: list[str] = []
    for record in cfg.hooks.values():
        if not _bound(record, ev):
            continue
        if hatches.skips(record.id, mandatory=record.mandatory):
            disabled.append(record.id)
            continue
        on_error = record.on_error.get(ev.name, "open")
        chosen.append(Selected(record, on_error, failure_class(on_error)))
    chosen.sort(key=lambda s: (CLASS_RANK[s.failure_class], s.record.priority, s.record.id))
    return Selection(tuple(chosen), tuple(sorted(disabled)))


def _bound(record: HookRecord, ev: CanonicalEvent) -> bool:
    return (
        ev.name in record.events
        and ev.name in record.handlers
        and ev.harness.value in record.supports
        and matcher_accepts(record.matcher.get(ev.name), ev)
    )


def matcher_accepts(spec: MatcherSpec | None, ev: CanonicalEvent) -> bool:
    """Whether every dimension ``spec`` sets accepts ``ev`` (an absent matcher accepts all).

    Example::

        >>> matcher_accepts(None, ev)  # doctest: +SKIP
        True
    """
    if spec is None:
        return True
    if ev.name is EventName.SESSION_START and spec.sources:
        return ev.source in spec.sources
    if ev.name is EventName.PRE_COMPACT and spec.triggers:
        return ev.source in spec.triggers
    if ev.name is EventName.SUBAGENT_STOP and spec.agent_types:
        return ev.agent_type in spec.agent_types
    if ev.tool is None:
        return True
    return _tool_accepts(spec, ev.tool)


def _tool_accepts(spec: MatcherSpec, tool: ToolCall) -> bool:
    """The tool dimensions, ANDed: classes, names, paths, command regexes."""
    if spec.tools and not tool.tool_classes & {_class(name) for name in spec.tools}:
        return False
    if spec.tool_names and not _any_fullmatch(spec.tool_names, (tool.name, tool.native_name)):
        return False
    if spec.paths.patterns and not any(
        spec.paths.matches(p.key) for p in (*tool.paths, *tool.write_paths)
    ):
        return False
    return not spec.command or _command_matches(spec.command, tool)


def _class(name: str) -> ToolClass | None:
    try:
        return ToolClass(name)
    except ValueError:
        return None  # validate rejects it; it can never match


def _any_fullmatch(patterns: Iterable[str], values: tuple[str, ...]) -> bool:
    return any(_fullmatch(p, v) for p in patterns for v in values)


def _fullmatch(pattern: str, value: str) -> bool:
    try:
        return re.fullmatch(pattern, value) is not None
    except re.error:
        return False  # validate rejects it (H4); a bad pattern never matches


def _command_matches(patterns: tuple[str, ...], tool: ToolCall) -> bool:
    """A command regex searches the shell text: a non-shell call never matches one."""
    if tool.shell is None:
        return False
    for pattern in patterns:
        try:
            if re.search(pattern, tool.shell.text):
                return True
        except re.error:
            continue
    return False
