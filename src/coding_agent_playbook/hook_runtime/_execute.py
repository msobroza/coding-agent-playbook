"""Run the selected handlers under the per-hook failure policy (specs/prK-lifecycle-hooks.md §D.4).

Each selected hook resolves its handler, runs it, and leaves one :class:`Ran`:

- a result whose decision the hook did not declare, or a value that is not a
  ``HandlerResult``, is a ``contract_violation`` and handled as a failure;
- a handler that raises (a ``GitTimeout``, a ``ProcTimeout``, an external
  script breaking its contract) fails by class: a guard asks (``ask`` ->
  ``deny`` unattended), an overlay's strict guard denies, a quality hook adds
  nothing but one note per session;
- an untrusted external or entry-point handler is skipped with one note per
  session, never as a failure;
- a shell guard whose declared argv0s no segment runs is not called at all
  (``_prefilter``, specs/prK-hook-pack.md §E.4): its result is ``NONE``.

The first guard-class deny ends the fan-out: a deny is final. :class:`Progress`
is shared with the watchdog, which reuses :func:`failure_result` for the hooks
still pending when the deadline passes. A builtin declaring a
``failure_reason`` (pii-prompt-guard, specs/prK-hook-pack.md §E.5) has its
reason remembered on :class:`Progress` once resolved, so a raise, a contract
violation and a watchdog timeout all show it instead of the generic one.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_runtime._prefilter import skips_call
from coding_agent_playbook.hook_runtime.dispatch.decision import (
    Decision,
    HandlerResult,
    supported_decision,
)
from coding_agent_playbook.hook_runtime.registry import Untrusted, declaration_of

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from coding_agent_playbook.hook_runtime._selection import Selected
    from coding_agent_playbook.hook_runtime.deps import Clock
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.registry import HandlerContext, HandlerFn

__all__ = [
    "GUARD_FAILURE_REASON",
    "Progress",
    "Ran",
    "RanStatus",
    "failure_result",
    "run_handlers",
]

GUARD_FAILURE_REASON: Final = (
    "Playbook guard {hook_id} failed internally; confirm this action manually."
)
QUALITY_FAILURE_NOTE: Final = "{hook_id} skipped: internal error — run playbook-hook doctor"
UNTRUSTED_NOTE: Final = (
    "Playbook hook {hook_id} skipped: not trusted on this machine ({reason}); "
    "an interactive playbook sync can approve it."
)
INTERNAL_RULE_ID: Final = "internal_error"
UNTRUSTED_RULE_ID: Final = "untrusted"

type RanStatus = Literal["ok", "degraded", "violation", "untrusted"]
#: ``once(key)``: True the first time ``key`` is seen this session (``SessionState.once``).
type Once = Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class Ran:
    """What one selected hook produced on this event, and how."""

    selected: Selected
    result: HandlerResult
    status: RanStatus
    latency_ms: int


@dataclass(slots=True)
class Progress:
    """The fan-out so far; the watchdog reads it from its own thread.

    ``reasons`` holds the declared ``failure_reason`` of each resolved hook
    that has one, keyed by ``id(selected)``.
    """

    selected: tuple[Selected, ...]
    ran: list[Ran] = field(default_factory=list)
    reasons: dict[int, str] = field(default_factory=dict)

    def pending(self) -> list[Selected]:
        """The selected hooks that have not produced a result yet, in order."""
        done = {id(r.selected) for r in list(self.ran)}
        return [s for s in self.selected if id(s) not in done]

    def failure_reason(self, selected: Selected) -> str | None:
        """The reason ``selected``'s handler declared for its failures, if it was resolved."""
        return self.reasons.get(id(selected))


def failure_result(
    selected: Selected, *, once: Once | None, reason: str | None = None
) -> HandlerResult:
    """The result a failed hook yields under its class (§D.4); ``degraded`` is set.

    A quality hook adds its note only when ``once`` says it is the first
    failure this session (``None``, as in the watchdog: no note). A guard's
    reason is ``reason`` (its handler's declared ``failure_reason``) when
    given, else the generic one naming the hook.

    Example::

        >>> failure_result(guard, once=None).decision  # doctest: +SKIP
        <Decision.ASK: 'ask'>
    """
    hook_id = selected.record.id
    if selected.failure_class == "quality":
        first = once is not None and once(f"failed:{hook_id}")
        note = QUALITY_FAILURE_NOTE.format(hook_id=hook_id) if first else ""
        return HandlerResult(
            decision=Decision.NONE,
            hook_id=hook_id,
            rule_id=INTERNAL_RULE_ID,
            user_note=note,
            degraded=True,
        )
    decision = Decision.DENY if selected.failure_class == "guard_strict" else Decision.ASK
    return HandlerResult(
        decision=decision,
        hook_id=hook_id,
        rule_id=INTERNAL_RULE_ID,
        reason=reason or GUARD_FAILURE_REASON.format(hook_id=hook_id),
        degraded=True,
    )


def run_handlers(
    ev: CanonicalEvent,
    progress: Progress,
    *,
    resolve: Callable[[Selected], HandlerFn | Untrusted],
    context: Callable[[Selected], HandlerContext],
    once: Once,
    clock: Clock,
) -> list[Ran]:
    """Run every selected hook in order until the first guard deny; returns what ran.

    Example::

        >>> run_handlers(ev, Progress(selection.selected), resolve=..., context=..., once=..., clock=...)
        ... # doctest: +SKIP
    """
    for selected in progress.selected:
        started = clock.monotonic()
        result, status = _run_one(
            ev, selected, progress, resolve=resolve, context=context, once=once
        )
        latency = max(0, round((clock.monotonic() - started) * 1000))
        progress.ran.append(Ran(selected, result, status, latency))
        if selected.is_guard and supported_decision(ev.name, result.decision) is Decision.DENY:
            break
    return list(progress.ran)


def _run_one(
    ev: CanonicalEvent,
    selected: Selected,
    progress: Progress,
    *,
    resolve: Callable[[Selected], HandlerFn | Untrusted],
    context: Callable[[Selected], HandlerContext],
    once: Once,
) -> tuple[HandlerResult, RanStatus]:
    try:
        handler = resolve(selected)
        if isinstance(handler, Untrusted):
            return _untrusted(selected, handler, once), "untrusted"
        declaration = declaration_of(handler)
        if declaration is not None and declaration.failure_reason:
            progress.reasons[id(selected)] = declaration.failure_reason
        spec = selected.record.handlers.get(ev.name)
        if skips_call(declaration, ev, {} if spec is None else spec.config):
            return HandlerResult(decision=Decision.NONE, hook_id=selected.record.id), "ok"
        raw = handler(ev, context(selected))
    except Exception:
        return _failed(selected, progress, once), "degraded"
    return _checked(raw, selected, progress, once)


def _failed(selected: Selected, progress: Progress, once: Once) -> HandlerResult:
    return failure_result(selected, once=once, reason=progress.failure_reason(selected))


def _checked(
    raw: object, selected: Selected, progress: Progress, once: Once
) -> tuple[HandlerResult, RanStatus]:
    """``raw`` when it is a declared ``HandlerResult``, else a contract violation.

    The result is attributed to the hook that ran, whatever ``hook_id`` the
    handler set: a shared builtin cannot log under another hook's name.
    """
    record = selected.record
    if raw is None:
        return HandlerResult(decision=Decision.NONE, hook_id=record.id), "ok"
    if not isinstance(raw, HandlerResult):
        return _failed(selected, progress, once), "violation"
    if raw.decision is not Decision.NONE and raw.decision not in record.decisions:
        return _failed(selected, progress, once), "violation"
    if raw.hook_id != record.id:
        raw = dataclasses.replace(raw, hook_id=record.id)
    return raw, "ok"


def _untrusted(selected: Selected, untrusted: Untrusted, once: Once) -> HandlerResult:
    hook_id = selected.record.id
    first = once(f"untrusted:{hook_id}")
    note = UNTRUSTED_NOTE.format(hook_id=hook_id, reason=untrusted.reason) if first else ""
    return HandlerResult(
        decision=Decision.NONE, hook_id=hook_id, rule_id=UNTRUSTED_RULE_ID, user_note=note
    )


def results_of(ran: Sequence[Ran]) -> list[HandlerResult]:
    """The results to combine, in handler order."""
    return [r.result for r in ran]
