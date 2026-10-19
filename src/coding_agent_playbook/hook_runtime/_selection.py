"""Which hooks run on an event, and in what order (specs/prK-lifecycle-hooks.md §D.3.2).

A hook in ``guard_config.hooks`` is selected when the event is in its
``events``, the harness is in its ``supports``, ``PLAYBOOK_HOOKS_DISABLE``
does not name it (a ``mandatory`` hook ignores that list) and its
``matcher.<event>`` accepts the event. Sync already applied the on-formula
and ``applies_if``, so the runtime never evaluates them.

``routing`` decides which dispatch runs a handler: a decision sink is never
selected, and an async-routed handler (local-audit-log's ``activity_log`` on
``post_tool_use``) runs only in the async dispatch (OQ-19).

The order is ``(class rank, priority, id)``: guards before quality hooks, so
the first guard deny can short-circuit before a feedback hook spends its
budget, and never dict order.

On ``stop`` / ``subagent_stop`` the Stop coordinator (builtin
``stop_ci_parity_gate``) is the only handler of the Stop-stage hooks (those
whose handler names ``config.stage``, §D.5.1): with it selected they are
never fanned out, because it plans them itself (:func:`select_stage_hooks`)
under one budget and one combined reason. Without it (disabled, or a config
that lacks it) each stage hook's own binding still runs, failing open.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.event import EventName, ToolClass
from coding_agent_playbook.hook_runtime.policy import CLASS_RANK, failure_class
from coding_agent_playbook.hook_runtime.routing import ASYNC_AUDIT_MODE, handler_route

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, HookRecord
    from coding_agent_playbook.hook_runtime.config.hook_records import MatcherSpec
    from coding_agent_playbook.hook_runtime.escape import EscapeHatches
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.policy import FailureClass, OnError

__all__ = [
    "STOP_COORDINATOR_HANDLER",
    "Selected",
    "Selection",
    "matcher_accepts",
    "select_hooks",
    "select_stage_hooks",
    "stage_of",
]

#: The Stop coordinator's builtin: the only handler of the Stop-stage hooks (§D.5.1).
STOP_COORDINATOR_HANDLER: Final = "stop_ci_parity_gate"
_STOP_EVENTS: Final = frozenset({EventName.STOP, EventName.SUBAGENT_STOP})


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


def select_hooks(
    cfg: GuardConfig, ev: CanonicalEvent, hatches: EscapeHatches, *, asynchronous: bool = False
) -> Selection:
    """The hooks of ``cfg`` that run on ``ev``, ordered by ``(class rank, priority, id)``.

    ``asynchronous`` is the async ``post_tool_use`` dispatch: only async-routed
    handlers run there, and the synchronous dispatch skips them once
    ``logging.audit_mode`` says the async route is rendered (``routing``).
    A decision sink is never selected.

    Example::

        >>> [s.record.id for s in select_hooks(cfg, ev, EscapeHatches()).selected]  # doctest: +SKIP
        ['guard-generated-outputs', 'ruff-feedback']
    """
    chosen, disabled = _candidates(cfg, ev, hatches, asynchronous=asynchronous)
    chosen.sort(key=lambda s: (CLASS_RANK[s.failure_class], s.record.priority, s.record.id))
    return Selection(tuple(_route_stop(chosen, ev.name)), tuple(sorted(disabled)))


def select_stage_hooks(
    cfg: GuardConfig, ev: CanonicalEvent, hatches: EscapeHatches
) -> tuple[HookRecord, ...]:
    """The Stop-stage hooks bound to ``ev`` that the coordinator plans (by id; it orders them).

    Example::

        >>> [r.id for r in select_stage_hooks(cfg, stop_ev, EscapeHatches())]  # doctest: +SKIP
        ['stop-drift-and-orphan-gate']
    """
    chosen, _ = _candidates(cfg, ev, hatches)
    staged = (s.record for s in chosen if stage_of(s.record, ev.name) is not None)
    return tuple(sorted(staged, key=lambda record: record.id))


def stage_of(record: HookRecord, event: EventName) -> str | None:
    """The Stop stage ``record`` contributes on ``event`` (its ``config.stage``), else ``None``.

    Example: ``stage_of(cfg.hooks["stop-drift-and-orphan-gate"], EventName.STOP) == "drift"``.
    """
    spec = record.handlers.get(event)
    stage = None if spec is None else spec.config.get("stage")
    return stage if isinstance(stage, str) else None


def _candidates(
    cfg: GuardConfig, ev: CanonicalEvent, hatches: EscapeHatches, *, asynchronous: bool = False
) -> tuple[list[Selected], list[str]]:
    """The hooks bound to ``ev``, and the ids ``PLAYBOOK_HOOKS_DISABLE`` skipped."""
    chosen: list[Selected] = []
    disabled: list[str] = []
    for record in cfg.hooks.values():
        if not _bound(record, ev) or not _routed_here(record, ev.name, cfg, asynchronous):
            continue
        if hatches.skips(record.id, mandatory=record.mandatory):
            disabled.append(record.id)
            continue
        on_error = record.on_error.get(ev.name, "open")
        chosen.append(Selected(record, on_error, failure_class(on_error)))
    return chosen, disabled


def _routed_here(
    record: HookRecord, event: EventName, cfg: GuardConfig, asynchronous: bool
) -> bool:
    """Whether this dispatch (sync or async) runs ``record``'s handler on ``event``."""
    spec = record.handlers[event]
    route = handler_route(
        event.value, kind=spec.kind, name=spec.name, decisions=(d.value for d in record.decisions)
    )
    if route == "sink":
        return False  # the dispatcher's own decision log is the sink's whole job
    if asynchronous:
        return route == "async"
    return route != "async" or cfg.logging.audit_mode != ASYNC_AUDIT_MODE


def _route_stop(chosen: list[Selected], event: EventName) -> list[Selected]:
    """With the coordinator selected, the Stop-stage hooks are its stages, never fanned out."""
    if event not in _STOP_EVENTS or not any(_is_coordinator(s.record, event) for s in chosen):
        return chosen
    return [s for s in chosen if stage_of(s.record, event) is None]


def _is_coordinator(record: HookRecord, event: EventName) -> bool:
    spec = record.handlers.get(event)
    return spec is not None and spec.kind == "builtin" and spec.name == STOP_COORDINATOR_HANDLER


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
    """The tool dimensions, ANDed: the tool (classes OR names), paths, command regexes."""
    if (spec.tools or spec.tool_names) and not _tool_named(spec, tool):
        return False
    if spec.paths.patterns and not any(
        spec.paths.matches(p.key) for p in (*tool.paths, *tool.write_paths)
    ):
        return False
    return not spec.command or _command_matches(spec.command, tool)


def _tool_named(spec: MatcherSpec, tool: ToolCall) -> bool:
    """``tools`` and ``tool_names`` are one OR-ed dimension (§A.2), as both prefilters render it.

    So ``tools: [edit]`` plus ``tool_names: [Skill]`` selects an Edit and a
    ``Skill`` call alike (prompt-write-scope-guard, specs/prK-hook-pack.md §E.3).
    """
    if tool.tool_classes & {_class(name) for name in spec.tools}:
        return True
    return _any_fullmatch(spec.tool_names, (tool.name, tool.native_name))


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
