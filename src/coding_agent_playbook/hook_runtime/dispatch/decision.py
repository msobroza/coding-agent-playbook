"""The decision model (specs/prK-lifecycle-hooks.md §D.3.1, §D.3.5).

Handlers return a ``HandlerResult``; ``combine.combine`` folds an event's
results into one ``CombinedResult``, which the harness renderers turn into wire
output. ``EVENT_DECISIONS`` is the decision-support matrix both of them obey:
``supported_decision`` maps any decision down to what an event can express, so
neither a buggy handler nor a hand-built result can render an impossible output.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.event import EventName

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "EVENT_DECISIONS",
    "CombinedResult",
    "Decision",
    "HandlerResult",
    "Outcome",
    "supported_decision",
]


class Decision(StrEnum):
    """What a hook decides; precedence ``DENY > ASK > CONTEXT > NONE`` (L6: never allow).

    Example: ``max(Decision.ASK, Decision.DENY, key=lambda d: d.rank) is Decision.DENY``.
    """

    DENY = "deny"
    ASK = "ask"
    CONTEXT = "context"
    NONE = "none"

    @property
    def rank(self) -> int:
        """The precedence: higher wins."""
        return _RANK[self]


_RANK: Final[Mapping[Decision, int]] = MappingProxyType(
    {Decision.NONE: 0, Decision.CONTEXT: 1, Decision.ASK: 2, Decision.DENY: 3}
)


def _allowed(*decisions: Decision) -> frozenset[Decision]:
    return frozenset((*decisions, Decision.NONE))


#: The §D.3.5 decision-support matrix: what each event can express. The runtime
#: twin of ``hooks.resolution.tables.HOOK_EVENTS[...].decisions`` (a parity test pins them).
EVENT_DECISIONS: Final[Mapping[EventName, frozenset[Decision]]] = MappingProxyType(
    {
        EventName.SESSION_START: _allowed(Decision.CONTEXT),
        EventName.USER_PROMPT_SUBMIT: _allowed(Decision.DENY, Decision.CONTEXT),
        EventName.PRE_TOOL_USE: _allowed(Decision.DENY, Decision.ASK, Decision.CONTEXT),
        EventName.POST_TOOL_USE: _allowed(Decision.CONTEXT),
        EventName.POST_TOOL_USE_FAILURE: _allowed(Decision.CONTEXT),
        EventName.STOP: _allowed(Decision.DENY, Decision.CONTEXT),
        EventName.SUBAGENT_STOP: _allowed(Decision.DENY, Decision.CONTEXT),
        EventName.PRE_COMPACT: _allowed(),
        EventName.SESSION_END: _allowed(),
    }
)

# §D.3.3 step 7: an ask the event cannot express is tried as a deny first, then
# everything falls to context, then to none.
_FALLBACKS: Final[Mapping[Decision, tuple[Decision, ...]]] = MappingProxyType(
    {
        Decision.DENY: (Decision.DENY, Decision.CONTEXT, Decision.NONE),
        Decision.ASK: (Decision.ASK, Decision.DENY, Decision.CONTEXT, Decision.NONE),
        Decision.CONTEXT: (Decision.CONTEXT, Decision.NONE),
        Decision.NONE: (Decision.NONE,),
    }
)


def supported_decision(event: EventName, decision: Decision) -> Decision:
    """``decision`` mapped down to the strongest one ``event`` can express.

    Example::

        >>> supported_decision(EventName.POST_TOOL_USE, Decision.DENY)
        <Decision.CONTEXT: 'context'>
    """
    allowed = EVENT_DECISIONS[event]
    return next(d for d in _FALLBACKS[decision] if d in allowed)


@dataclass(frozen=True, slots=True, kw_only=True)
class HandlerResult:
    """One hook's verdict on one event; a handler returning ``None`` means ``NONE``.

    ``reason`` is the deny/ask text, ``context`` the advisory items for the
    model, ``user_note`` a line for the user. ``dedupe_key`` scopes the
    per-session dedupe of the context items (typically the path); an empty key
    shows them every time. ``degraded`` marks a result the failure policy made.
    ``escape`` names an escape hatch the hook honoured (a static identifier such
    as ``override_token``, never the text that triggered it): the decision log
    records it as an ``escape`` line, ids only (§D.6.2).

    Example: ``HandlerResult(decision=Decision.DENY, hook_id="guard-x", reason="no")``.
    """

    decision: Decision
    hook_id: str
    rule_id: str = ""
    reason: str = ""
    context: tuple[str, ...] = ()
    user_note: str = ""
    dedupe_key: str = ""
    degraded: bool = False
    escape: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class Outcome:
    """What became of one result: the decision-log view (§D.6.2), ids only.

    ``effective`` is the decision after the event-support map-down and ask
    degradation; ``contract_violation`` marks a decision the event cannot
    express. Example: an unattended ask has ``decision=ASK, effective=DENY``.
    """

    hook_id: str
    rule_id: str
    decision: Decision
    effective: Decision
    degraded: bool = False
    contract_violation: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class CombinedResult:
    """An event's single combined decision, capped and ready to render.

    ``context`` is non-empty only for ``CONTEXT``; ``user_notes`` come from
    every result. Example: ``CombinedResult()`` renders as no output at all.
    """

    decision: Decision = Decision.NONE
    reason: str = ""
    context: tuple[str, ...] = ()
    user_notes: tuple[str, ...] = ()
    outcomes: tuple[Outcome, ...] = ()
