"""Harness-neutral registration planning (specs/prK-lifecycle-hooks.md §C.2.1, §D.4).

:func:`plan_registrations` turns enabled hooks into one :class:`HookRegistration`
per reachable event (L3: one registration, in-process fan-out), plus
``session_start`` whenever any registration exists: the dispatcher's bootstrap
and the launcher's one visible-failure channel (§C.2.7). :func:`deadlines_ms`
and :func:`registration_timeout_s` are the one §D.4 timeout formula, rendered
into ``guard_config.json`` (the watchdog) and into every registration (the
harness backstop), with a checked one-second margin between them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Protocol

from coding_agent_playbook._hook_schema import HookMatcher
from coding_agent_playbook.hook_policy import (
    ENGINE_DEADLINE_CAP_MS,
    HOOK_CAPABLE_ADAPTERS,
    HOOK_EVENTS,
    HOOK_SUPPORT,
)
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.policy import effective_on_error
from coding_agent_playbook.hook_runtime.stop.stages import DEFAULT_BUDGET_S

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.types import HookFrontmatter

__all__ = [
    "BOOTSTRAP_DEADLINE_MS",
    "STOP_COORDINATOR_ID",
    "STOP_EVENTS",
    "WATCHDOG_MARGIN_MS",
    "DeclaredMember",
    "HookRegistration",
    "RegistrationMember",
    "RegistrationTimeoutError",
    "checked_registration_timeout_s",
    "coordinator_budget_s",
    "deadlines_ms",
    "declared_stop_budget_s",
    "plan_registrations",
    "registration_timeout_s",
]

#: The Stop coordinator hook, whose merged ``budget_s`` sets the stop deadline (§D.4).
STOP_COORDINATOR_ID: Final = "stop-ci-parity-gate"
#: The deadline of a ``session_start`` registered with no member hook: the
#: dispatcher's bootstrap only (state sweep, launcher-log report). The §D.4 sum
#: would be 0, which the runtime's ``guard_config`` loader rejects (minimum 1).
BOOTSTRAP_DEADLINE_MS: Final = 2_000
#: The harness must never kill the dispatcher before its watchdog has written a
#: decided result: registration seconds * 1000 >= deadline + this margin.
WATCHDOG_MARGIN_MS: Final = 1_000

#: The events whose deadline is the Stop coordinator's budget, not a sum (§D.4).
STOP_EVENTS: Final = frozenset({"stop", "subagent_stop"})


class RegistrationMember(Protocol):
    """What planning reads of a hook; :class:`~coding_agent_playbook.hook_policy.ResolvedHook` fits.

    ``on_error`` is already clamped per event; ``supports`` lists the adapters
    that render the hook.
    """

    @property
    def id(self) -> str: ...
    @property
    def events(self) -> Sequence[str]: ...
    @property
    def matcher(self) -> Mapping[str, HookMatcher]: ...
    @property
    def timeout(self) -> float: ...
    @property
    def on_error(self) -> Mapping[str, str]: ...
    @property
    def supports(self) -> Sequence[str]: ...


@dataclass(frozen=True)
class DeclaredMember:
    """A hook as its frontmatter declares it, for the debug projection (no gating, no config).

    Example: ``DeclaredMember.from_frontmatter(hook.frontmatter)``.
    """

    id: str
    events: tuple[str, ...]
    matcher: Mapping[str, HookMatcher]
    timeout: float
    on_error: Mapping[str, str]
    supports: tuple[str, ...]

    @classmethod
    def from_frontmatter(cls, fm: HookFrontmatter) -> DeclaredMember:
        """Canonical events only, ``on_error`` clamped per event, hook-capable ``supports`` only."""
        events = tuple(event for event in dict.fromkeys(fm.events) if event in HOOK_EVENTS)
        return cls(
            id=fm.id,
            events=events,
            matcher={event: fm.matcher.get(event, HookMatcher()) for event in events},
            timeout=fm.timeout,
            on_error={event: effective_on_error(fm.on_error, EventName(event)) for event in events},
            supports=tuple(a for a in dict.fromkeys(fm.supports) if a in HOOK_CAPABLE_ADAPTERS),
        )


class RegistrationTimeoutError(ValueError):
    """A registration timeout that would let the harness kill the dispatcher first (§D.4)."""


@dataclass(frozen=True)
class HookRegistration:
    """One harness registration: an event, its member hooks, its deadline and timeout.

    ``matchers`` are the members' entries for ``event`` (their union is the
    harness matcher); ``strict`` is overlay strict mode (``onFailure: block`` +
    ``--strict-launch`` on Claude). Harness-neutral: :func:`to_claude_group`
    renders it for Claude Code; K4 renders the OpenCode shim's ``REG``.

    Example::

        >>> reg = plan_registrations(hooks, "claude_code")[0]  # doctest: +SKIP
        >>> reg.artifact_id
        'registration:session_start'
    """

    event: str
    members: tuple[str, ...]
    deadline_ms: int
    timeout_s: int
    strict: bool = False
    matchers: tuple[HookMatcher, ...] = field(default=())

    @property
    def artifact_id(self) -> str:
        """The lockfile ``artifact_id`` of the managed group (§B.6)."""
        return f"registration:{self.event}"

    @property
    def claude_event(self) -> str:
        """The Claude Code event name (``PreToolUse``)."""
        return HOOK_EVENTS[self.event].claude_name


# --- the §D.4 timeout formula -----------------------------------------------------------


def deadlines_ms(
    members: Iterable[RegistrationMember],
    *,
    stop_budget_s: float = DEFAULT_BUDGET_S,
    execution_timeouts_s: Sequence[float] = (),
) -> dict[str, int]:
    """Per-event watchdog deadlines, in canonical order, for every event a member declares.

    ``min(cap, Σ member timeouts)``; ``stop``/``subagent_stop`` instead take
    ``min(cap, budget + Σ execution-stage timeouts)``. ``session_start`` is
    always present once any member exists (:data:`BOOTSTRAP_DEADLINE_MS` when
    no member declares it). Pass **every** resolved hook, not one adapter's:
    ``guard_config.json`` holds one deadline per event for all harnesses.

    Example::

        >>> deadlines_ms([hook])  # a 2 s pre_tool_use hook  # doctest: +SKIP
        {'session_start': 2000, 'pre_tool_use': 2000}
    """
    listed = list(members)
    if not listed:
        return {}
    stop_ms = round(1000 * (stop_budget_s + sum(execution_timeouts_s)))
    deadlines: dict[str, int] = {}
    for event in HOOK_EVENTS:
        on_event = [m for m in listed if event in m.events]
        if event == "session_start" and not on_event:
            deadlines[event] = BOOTSTRAP_DEADLINE_MS
        elif on_event:
            total = stop_ms if event in STOP_EVENTS else _sum_ms(on_event)
            deadlines[event] = min(ENGINE_DEADLINE_CAP_MS[event], total)
    return deadlines


def coordinator_budget_s(hooks: Iterable[ResolvedHook]) -> float:
    """The Stop coordinator's merged ``budget_s``, else :data:`DEFAULT_BUDGET_S`.

    K6 adds the enabled execution stages' timeouts through ``deadlines_ms``.

    Example: ``deadlines_ms(hooks, stop_budget_s=coordinator_budget_s(hooks))``.
    """
    for hook in hooks:
        handler = hook.handlers.get("stop")
        if hook.id == STOP_COORDINATOR_ID and handler is not None:
            return _budget(handler.config)
    return DEFAULT_BUDGET_S


def declared_stop_budget_s(fm: HookFrontmatter) -> float:
    """:func:`coordinator_budget_s` for an unresolved definition (the debug projection)."""
    handler = fm.handlers.get("stop", fm.handler)
    if fm.id != STOP_COORDINATOR_ID or handler is None:
        return DEFAULT_BUDGET_S
    return _budget(handler.config)


def registration_timeout_s(deadline_ms: int) -> int:
    """The harness timeout in seconds: ``ceil(deadline_ms / 1000) + 2`` (§D.4).

    Example: ``registration_timeout_s(30_000) == 32``.
    """
    return math.ceil(deadline_ms / 1000) + 2


def checked_registration_timeout_s(
    event: str, deadline_ms: int, *, formula: Callable[[int], int] = registration_timeout_s
) -> int:
    """``formula(deadline_ms)``, asserting the harness outlives the watchdog by a second.

    Raises :class:`RegistrationTimeoutError` naming the event, the timeout and
    the deadline when ``timeout_s * 1000 < deadline_ms + 1000``.

    Example: ``checked_registration_timeout_s("stop", 3000) == 5``.
    """
    timeout_s = formula(deadline_ms)
    if timeout_s * 1000 < deadline_ms + WATCHDOG_MARGIN_MS:
        raise RegistrationTimeoutError(
            f"{event}: registration timeout {timeout_s}s would cut the {deadline_ms} ms "
            f"watchdog deadline; expected at least {deadline_ms + WATCHDOG_MARGIN_MS} ms"
        )
    return timeout_s


# --- the plan ----------------------------------------------------------------------------


def plan_registrations(
    members: Sequence[RegistrationMember],
    adapter_name: str,
    support: Mapping[str, Mapping[str, frozenset[str]]] = HOOK_SUPPORT,
    *,
    deadlines: Mapping[str, int] | None = None,
    strict_pre_tool_use: bool = False,
) -> list[HookRegistration]:
    """One registration per event reachable on ``adapter_name`` with a member, in canonical order.

    A member is a hook that lists ``adapter_name`` in ``supports`` and declares
    the event. ``deadlines`` defaults to :func:`deadlines_ms` over every member
    passed. Strict mode needs a member whose (clamped) ``on_error`` is ``deny``,
    and on ``pre_tool_use`` an explicit ``strict_pre_tool_use`` opt-in (OQ-18).

    Example::

        >>> [r.event for r in plan_registrations(hooks, "claude_code")]  # doctest: +SKIP
        ['session_start', 'pre_tool_use']
    """
    reachable = support.get(adapter_name, {})
    on_adapter = [m for m in members if adapter_name in m.supports]
    by_event = {
        event: [m for m in on_adapter if event in m.events]
        for event in HOOK_EVENTS
        if event in reachable
    }
    wanted = [event for event, found in by_event.items() if found]
    if wanted and "session_start" in reachable and "session_start" not in wanted:
        wanted.insert(0, "session_start")
    limits = deadlines_ms(members) if deadlines is None else deadlines
    return [_registration(event, by_event[event], limits, strict_pre_tool_use) for event in wanted]


def _registration(
    event: str,
    found: Sequence[RegistrationMember],
    limits: Mapping[str, int],
    strict_pre_tool_use: bool,
) -> HookRegistration:
    deadline = limits.get(event, ENGINE_DEADLINE_CAP_MS[event] if found else BOOTSTRAP_DEADLINE_MS)
    strict = any(m.on_error.get(event) == "deny" for m in found) and (
        event != "pre_tool_use" or strict_pre_tool_use
    )
    return HookRegistration(
        event=event,
        members=tuple(sorted(m.id for m in found)),
        deadline_ms=deadline,
        timeout_s=checked_registration_timeout_s(event, deadline),
        strict=strict,
        matchers=tuple(m.matcher.get(event, HookMatcher()) for m in found),
    )


def _sum_ms(members: Iterable[RegistrationMember]) -> int:
    return sum(round(member.timeout * 1000) for member in members)


def _budget(config: Mapping[str, Any]) -> float:
    """A positive number ``budget_s``, else the default (validate reports a bad one)."""
    value = config.get("budget_s")
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return DEFAULT_BUDGET_S
    return float(value)
