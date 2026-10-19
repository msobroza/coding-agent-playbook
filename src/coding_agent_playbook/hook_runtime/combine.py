"""The one combination rule: an event's handler results to one decision (specs/prK-lifecycle-hooks.md §D.3.3).

``combine`` applies, in order: the event-support map-down (§D.3.5), ask
degradation (§D.3.6), ``DENY > ASK > CONTEXT > NONE``, and the §D.3.4 caps on
reasons, context items and user notes. It is pure: the per-session context
dedupe arrives as an injected ``once`` callable and the ``[hooks]
unattended_ask`` policy as a value, so it needs no state or config type. The
declared-decision check (§D.3.3 step 6) runs in the dispatcher before this,
because only the dispatcher holds the hook records.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, Protocol

from coding_agent_playbook.hook_runtime.dispatch.caps import (
    OutputCaps,
    clamp_lines,
    clean_text,
    clip,
)
from coding_agent_playbook.hook_runtime.dispatch.decision import (
    CombinedResult,
    Decision,
    HandlerResult,
    Outcome,
    supported_decision,
)
from coding_agent_playbook.hook_runtime.dispatch.event import EventName, Harness

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

__all__ = [
    "ASK_DENIED_PREFIX",
    "ASK_WARNED_PREFIX",
    "OPENCODE_ASK_PREFIX",
    "EventFacts",
    "UnattendedAsk",
    "combine",
]

#: ``[hooks] unattended_ask`` (§B.1): what an ask becomes when no human can answer.
type UnattendedAsk = Literal["deny", "warn"]

ASK_DENIED_PREFIX: Final = "Needs user confirmation; unattended run, so denied: "
#: OpenCode has an attending user but no ask primitive (§C.3.4), so it says why.
OPENCODE_ASK_PREFIX: Final = "Needs user approval (OpenCode cannot ask): "
ASK_WARNED_PREFIX: Final = "Needs user confirmation; unattended run, so allowed with a warning: "
_MORE_FINDINGS = "(+{n} more playbook findings)"
_STOP_EVENTS: Final = frozenset({EventName.STOP, EventName.SUBAGENT_STOP})
_WARNED_NOTE = (
    "Playbook hook {hook_id} would have asked for confirmation; "
    "unattended run, so it was allowed with a warning."
)


class EventFacts(Protocol):
    """What ``combine`` reads of the event; ``CanonicalEvent`` satisfies it."""

    @property
    def name(self) -> EventName: ...

    @property
    def harness(self) -> Harness: ...

    @property
    def unattended(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class _Effective:
    """A result with its effective decision and the texts that decision carries."""

    result: HandlerResult
    decision: Decision
    reason: str
    context: tuple[str, ...]
    note: str
    violation: bool


def _first_time(_key: str) -> bool:
    return True


def combine(
    results: Sequence[HandlerResult],
    *,
    ev: EventFacts,
    unattended_ask: UnattendedAsk = "deny",
    once: Callable[[str], bool] = _first_time,
) -> CombinedResult:
    """Fold ``results`` (in handler order) into the event's one decision (§D.3.3).

    ``once(key)`` is ``SessionState.once``: true the first time a context
    item's key is seen this session. It is called only for items actually
    shown, so a cap or a deny never burns a key. The default shows every item
    (stateless mode).

    Example::

        >>> combine([HandlerResult(decision=Decision.ASK, hook_id="g", reason="sure?")],
        ...         ev=unattended_event).reason  # doctest: +SKIP
        'Needs user confirmation; unattended run, so denied: sure?'
    """
    effective = [_effective(r, ev, unattended_ask) for r in results]
    final = max((e.decision for e in effective), key=lambda d: d.rank, default=Decision.NONE)
    context = _context(effective, once) if final is Decision.CONTEXT else ()
    if final is Decision.CONTEXT and not context:
        final = Decision.NONE
    return CombinedResult(
        decision=final,
        reason=_reason(effective, final, ev.name),
        context=context,
        user_notes=clamp_lines(_notes(effective), OutputCaps.USER_NOTES),
        outcomes=tuple(_outcome(e) for e in effective),
    )


def _effective(r: HandlerResult, ev: EventFacts, unattended_ask: UnattendedAsk) -> _Effective:
    """Map ``r`` to what the event can express, then degrade an unanswerable ask."""
    mapped = _map_to_event(r, ev.name)
    if mapped.decision is not Decision.ASK or not ev.unattended:
        return mapped
    if unattended_ask == "warn":
        note = _join(r.user_note, _WARNED_NOTE.format(hook_id=r.hook_id))
        warned = (f"{ASK_WARNED_PREFIX}{mapped.reason}",)
        return _Effective(r, Decision.CONTEXT, mapped.reason, warned, note, mapped.violation)
    prefix = OPENCODE_ASK_PREFIX if ev.harness is Harness.OPENCODE else ASK_DENIED_PREFIX
    denied = f"{prefix}{mapped.reason}"
    return _Effective(r, Decision.DENY, denied, mapped.context, r.user_note, mapped.violation)


def _map_to_event(r: HandlerResult, event: EventName) -> _Effective:
    """``r`` with its decision mapped down to ``event``'s matrix row (§D.3.3 step 7).

    A deny or ask that falls to context keeps its reason as a context item, so
    the model still learns what the hook found.
    """
    decision = supported_decision(event, r.decision)
    reason, context = _reason_text(r), r.context
    if decision is Decision.CONTEXT and r.decision.rank > Decision.CONTEXT.rank:
        context = (*context, reason)
    return _Effective(r, decision, reason, context, r.user_note, decision is not r.decision)


def _reason_text(r: HandlerResult) -> str:
    """The result's reason, or a line naming the hook when it gave none."""
    if r.reason.strip():
        return r.reason
    verb = "asks for confirmation" if r.decision is Decision.ASK else "blocked this action"
    return f"Playbook hook {r.hook_id} {verb}."


def _reason(effective: list[_Effective], final: Decision, event: EventName) -> str:
    """The reasons of the results that decided, clamped to the §D.3.4 reason budget.

    A Stop block is the coordinator's one combined reason, whose own budget is
    40 lines (§D.5.4), not a tool-call deny's four.
    """
    if final not in (Decision.DENY, Decision.ASK):
        return ""
    deciding = [e.reason for e in effective if e.decision is final]
    summary = (lambda n: _MORE_FINDINGS.format(n=n)) if len(deciding) > 1 else None
    cap = OutputCaps.STOP_REASON if event in _STOP_EVENTS else OutputCaps.REASON
    return "\n".join(clamp_lines(deciding, cap, summary=summary))


def _context(effective: list[_Effective], once: Callable[[str], bool]) -> tuple[str, ...]:
    """The CONTEXT items to show: in-event unique, capped, then deduped per session."""
    shown: dict[str, None] = {}
    for e in effective:
        if e.decision is not Decision.CONTEXT:
            continue
        taken = 0
        for item, key in _items(e):
            if len(shown) == OutputCaps.CONTEXT_ITEMS_PER_EVENT:
                return tuple(shown)
            if taken == OutputCaps.CONTEXT_ITEMS_PER_HOOK:
                break
            if item in shown or (key and not once(key)):
                continue
            shown[item] = None
            taken += 1
    return tuple(shown)


def _items(e: _Effective) -> Iterator[tuple[str, str]]:
    """``(item, once key)`` per non-blank context item; the key is empty without a dedupe key."""
    for raw in e.context:
        item = clip(clean_text(raw).strip(), OutputCaps.FIELD_CHARS)
        if not item:
            continue
        key = e.result.dedupe_key
        yield item, f"ctx:{key}:{_digest8(item)}" if key else ""


def _digest8(text: str) -> str:
    """The §D.3.4 dedupe digest, ``sha1(text)[:8]``: an identity, not a security hash."""
    digest = hashlib.sha1(text.encode("utf-8", "surrogatepass"), usedforsecurity=False)
    return digest.hexdigest()[:8]


def _notes(effective: list[_Effective]) -> list[str]:
    """Every result's note lines, in order, each line once."""
    lines = (line.strip() for e in effective for line in clean_text(e.note).splitlines())
    return list(dict.fromkeys(line for line in lines if line))


def _outcome(e: _Effective) -> Outcome:
    r = e.result
    return Outcome(
        hook_id=r.hook_id,
        rule_id=r.rule_id,
        decision=r.decision,
        effective=e.decision,
        degraded=r.degraded,
        contract_violation=e.violation,
    )


def _join(first: str, second: str) -> str:
    return f"{first}\n{second}" if first else second
