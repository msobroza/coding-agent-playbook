"""The tail every dispatch path shares: combine, deferred notes, render, the one write (§D.1 steps 6-7).

The hooks' fan-out, a ``ConfigFault`` and a ``ContractFault`` all end the same
way, so the caps, the ask degradation and the closed-key renderers apply to
dispatcher-made decisions too.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from coding_agent_playbook.hook_runtime.caps import OutputCaps, clamp_lines
from coding_agent_playbook.hook_runtime.combine import combine
from coding_agent_playbook.hook_runtime.decision import CombinedResult
from coding_agent_playbook.hook_runtime.event import EventName, Harness

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime._execute import Ran
    from coding_agent_playbook.hook_runtime.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.harness.wire import WireOutput
    from coding_agent_playbook.hook_runtime.state.session import SessionState
    from coding_agent_playbook.hook_runtime.watchdog import OutputGate

__all__ = ["DispatchTrace", "Responder"]


@dataclass(frozen=True, slots=True, kw_only=True)
class DispatchTrace:
    """One dispatch as ``simulate`` reports it: the output and how it was reached.

    Example: ``DispatchTrace(wire=WireOutput())`` is an inert event (nothing written).
    """

    wire: WireOutput
    combined: CombinedResult = field(default_factory=CombinedResult)
    ran: tuple[Ran, ...] = ()
    written: bool = False


class Responder:
    """Turns results into the harness output and writes it through the gate.

    Example::

        >>> Responder(Harness.CLAUDE_CODE, gate).respond(ev, [result])  # doctest: +SKIP
        (CombinedResult(...), WireOutput(...))
    """

    def __init__(self, harness: Harness, gate: OutputGate) -> None:
        self.harness = harness
        self.gate = gate

    def render(self, event: EventName, combined: CombinedResult) -> WireOutput:
        """The harness's wire output for ``combined`` (renderers are imported per harness)."""
        if self.harness is Harness.OPENCODE:
            from coding_agent_playbook.hook_runtime.harness.opencode import render_opencode

            return render_opencode(event, combined)
        from coding_agent_playbook.hook_runtime.harness.claude import render_claude

        return render_claude(event, combined)

    def combine(
        self,
        ev: CanonicalEvent,
        results: Sequence[HandlerResult],
        *,
        unattended_ask: Literal["deny", "warn"] = "deny",
        session: SessionState | None = None,
    ) -> CombinedResult:
        """``combine`` with the session's dedupe, plus the deferred notes this event drains."""
        once = session.once if session is not None else _always
        combined = combine(results, ev=ev, unattended_ask=unattended_ask, once=once)
        if session is None or not drains_notes(ev):
            return combined
        deferred = session.drain_notes()
        if not deferred:
            return combined
        notes = list(dict.fromkeys([*deferred, *combined.user_notes]))
        return dataclasses.replace(combined, user_notes=clamp_lines(notes, OutputCaps.USER_NOTES))

    def respond(
        self,
        ev: CanonicalEvent,
        results: Sequence[HandlerResult],
        *,
        unattended_ask: Literal["deny", "warn"] = "deny",
        session: SessionState | None = None,
    ) -> tuple[CombinedResult, WireOutput]:
        """Combine, render and write once; returns what was decided and written."""
        combined = self.combine(ev, results, unattended_ask=unattended_ask, session=session)
        wire = self.render(ev.name, combined)
        self.gate.write(wire)
        return combined, wire


def drains_notes(ev: CanonicalEvent) -> bool:
    """Claude shows deferred notes on the next prompt or session start; OpenCode on every dispatch.

    Example::

        >>> drains_notes(stop_on_claude)  # doctest: +SKIP
        False
    """
    if ev.harness is Harness.OPENCODE:
        return True
    return ev.name in (EventName.USER_PROMPT_SUBMIT, EventName.SESSION_START)


def _always(_key: str) -> bool:
    return True
