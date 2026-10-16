"""Attendance and failure-policy tables for the dispatcher (specs/prK-lifecycle-hooks.md §D.3.6, §D.4).

``is_unattended`` is the one definition of "no human can answer an ask"
(D-4); the parsers call it once per event. The failure-policy tables say what
a hook's declared ``on_error`` means on the event that fired: its effective
value (clamped per event, §A.2), its failure class (guard before quality in
the fan-out order), and the decision a failure becomes. ``ENGINE_DEADLINE_CAP_MS``
bounds each event's watchdog deadline (§D.4).

The runtime may not import ``hook_policy`` or ``evals`` (§D.1), so the tables
shared with them are re-declared here and pinned to their twins by parity tests.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal, Protocol

from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName, Harness

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "CLASS_RANK",
    "ENGINE_DEADLINE_CAP_MS",
    "ON_ERROR_ALLOWED",
    "UNATTENDED_ENV_VAR",
    "AttendanceFacts",
    "FailureClass",
    "OnError",
    "effective_on_error",
    "failure_class",
    "failure_decision",
    "is_unattended",
]

#: Set to ``1`` by the eval runners on the agent's env (P-D2); the twin of
#: ``evals.agent_env.UNATTENDED_ENV_VAR``.
UNATTENDED_ENV_VAR: Final = "PLAYBOOK_HOOK_UNATTENDED"

type OnError = Literal["ask", "deny", "open"]
#: ``guard`` asks on failure, ``guard_strict`` (overlay ``on_error: deny``)
#: denies, ``quality`` fails open with one note per session (§D.4).
type FailureClass = Literal["guard", "guard_strict", "quality"]

_OPEN_ONLY: Final[frozenset[OnError]] = frozenset({"open"})

#: The ``on_error`` values each event honours (§A.2); any other clamps to ``open``.
ON_ERROR_ALLOWED: Final[Mapping[EventName, frozenset[OnError]]] = MappingProxyType(
    {
        EventName.SESSION_START: _OPEN_ONLY,
        EventName.USER_PROMPT_SUBMIT: frozenset({"deny", "open"}),
        EventName.PRE_TOOL_USE: frozenset({"ask", "deny", "open"}),
        EventName.POST_TOOL_USE: _OPEN_ONLY,
        EventName.POST_TOOL_USE_FAILURE: _OPEN_ONLY,
        EventName.STOP: _OPEN_ONLY,
        EventName.SUBAGENT_STOP: _OPEN_ONLY,
        EventName.PRE_COMPACT: _OPEN_ONLY,
        EventName.SESSION_END: _OPEN_ONLY,
    }
)

_FAILURE_CLASS: Final[Mapping[OnError, FailureClass]] = MappingProxyType(
    {"ask": "guard", "deny": "guard_strict", "open": "quality"}
)

#: Fan-out order key (§D.3.2): guards run before quality hooks, so a guard deny
#: short-circuits before any feedback hook spends its budget.
CLASS_RANK: Final[Mapping[FailureClass, int]] = MappingProxyType(
    {"guard": 0, "guard_strict": 0, "quality": 1}
)

_FAILURE_DECISION: Final[Mapping[FailureClass, Decision]] = MappingProxyType(
    {"guard": Decision.ASK, "guard_strict": Decision.DENY, "quality": Decision.NONE}
)

#: The most a whole event may take (§D.4): ``deadline_ms = min(cap, Σ timeout_ms)``.
#: The stop caps are the upper bound of the stop budget formula.
ENGINE_DEADLINE_CAP_MS: Final[Mapping[EventName, int]] = MappingProxyType(
    {
        EventName.SESSION_START: 15_000,
        EventName.USER_PROMPT_SUBMIT: 30_000,
        EventName.PRE_TOOL_USE: 30_000,
        EventName.POST_TOOL_USE: 60_000,
        EventName.POST_TOOL_USE_FAILURE: 30_000,
        EventName.STOP: 595_000,
        EventName.SUBAGENT_STOP: 595_000,
        EventName.PRE_COMPACT: 30_000,
        # Above Claude's shared 1.5 s SessionEnd budget: the registration raises it.
        EventName.SESSION_END: 8_000,
    }
)

_CI_VALUES: Final = frozenset({"true", "1"})


class AttendanceFacts(Protocol):
    """What ``is_unattended`` reads of an event; ``CanonicalEvent`` satisfies it."""

    @property
    def harness(self) -> Harness: ...

    @property
    def permission_mode(self) -> str | None: ...


def is_unattended(ev: AttendanceFacts, env: Mapping[str, str]) -> bool:
    """Whether no human can answer an ask for ``ev`` (§D.3.6), from exact values only.

    True for ``PLAYBOOK_HOOK_UNATTENDED=1``, ``CI`` of ``true`` or ``1``,
    ``GITHUB_ACTIONS=true``, any OpenCode event (no ask primitive) and Claude's
    ``dontAsk`` mode. ``bypassPermissions`` and ``auto`` count as attended
    (OQ-21). ``env`` is the hook process environment, never a segment prefix.

    Example::

        >>> is_unattended(event_on_claude, {"CI": "true"})  # doctest: +SKIP
        True
    """
    return (
        env.get(UNATTENDED_ENV_VAR) == "1"
        or env.get("CI") in _CI_VALUES
        or env.get("GITHUB_ACTIONS") == "true"
        or ev.harness is Harness.OPENCODE
        or ev.permission_mode == "dontAsk"
    )


def effective_on_error(declared: str, event: EventName) -> OnError:
    """``declared`` where ``event`` honours it, else ``open`` (the §A.2 per-event clamp).

    Example::

        >>> effective_on_error("ask", EventName.STOP)
        'open'
    """
    for value in ON_ERROR_ALLOWED[event]:
        if value == declared:
            return value
    return "open"


def failure_class(on_error: OnError) -> FailureClass:
    """The failure class an effective ``on_error`` puts a hook in (§D.4).

    Example::

        >>> failure_class("deny")
        'guard_strict'
    """
    return _FAILURE_CLASS[on_error]


def failure_decision(cls: FailureClass) -> Decision:
    """The decision a failed hook of class ``cls`` yields, before ask degradation.

    Example::

        >>> failure_decision("guard")
        <Decision.ASK: 'ask'>
    """
    return _FAILURE_DECISION[cls]
