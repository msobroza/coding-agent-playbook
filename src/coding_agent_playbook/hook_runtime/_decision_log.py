"""guard-decision-log lines for one dispatch (specs/prK-lifecycle-hooks.md §D.6.2).

One line per decision, ids and flags only (D-10): the record type is
``security.audit.GuardDecisionRecord``, whose writer refuses any other key, so
no command text, path, prompt, reason or environment value can reach the log.
Writing never blocks and never raises: a failure is one stderr note per
session, returned to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.state import StateUnavailable, iso_utc
from coding_agent_playbook.security.audit import GuardDecisionRecord, append_decision

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from coding_agent_playbook.hook_runtime._execute import Ran
    from coding_agent_playbook.hook_runtime.decision import Outcome
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.state import StateStore

__all__ = ["DISPATCHER_ID", "DecisionLog", "LogLine", "lines_for"]

#: The ``hook_id`` of lines the dispatcher itself decides (faults, escapes, overrides).
DISPATCHER_ID: Final = "playbook-dispatcher"
ASK_TO_DENY: Final = "ask→deny"
_LOGGED: Final = frozenset({Decision.DENY, Decision.ASK, Decision.CONTEXT})


@dataclass(frozen=True, slots=True, kw_only=True)
class LogLine:
    """The varying part of one decision line; :class:`DecisionLog` adds the event's fields."""

    hook_id: str
    decision: str
    effective: str
    rule_id: str | None = None
    degraded: bool = False
    escape: str | None = None
    latency_ms: int = 0


def lines_for(ran: Sequence[Ran], outcomes: Sequence[Outcome]) -> list[LogLine]:
    """The lines a fan-out logs: guard decisions, failures, violations and skips.

    A quality hook's own context is not a guard decision, so it is not logged.

    Example::

        >>> lines_for([ran_deny], combined.outcomes)[0].decision  # doctest: +SKIP
        'deny'
    """
    lines: list[LogLine] = []
    for done, outcome in zip(ran, outcomes, strict=False):
        value = _decision_value(done, outcome)
        if value is None:
            continue
        lines.append(
            LogLine(
                hook_id=done.result.hook_id,
                rule_id=done.result.rule_id or None,
                decision=value,
                effective="none" if done.status == "untrusted" else outcome.effective.value,
                degraded=done.result.degraded,
                latency_ms=done.latency_ms,
            )
        )
    return lines


def _decision_value(done: Ran, outcome: Outcome) -> str | None:
    if done.status == "untrusted":
        return "untrusted"
    if done.status == "violation" or outcome.contract_violation:
        return "contract_violation"
    if done.status == "degraded":
        return "degraded"
    if not done.selected.is_guard or outcome.decision not in _LOGGED:
        return None
    if outcome.decision is Decision.ASK and outcome.effective is Decision.DENY:
        return ASK_TO_DENY
    return outcome.decision.value


class DecisionLog:
    """Appends decision lines for one event to ``<state>/decisions-YYYY-MM.jsonl``.

    ``enabled`` is ``guard_config.logging.decisions``; lines the dispatcher
    writes without a loaded config (escapes, faults) pass ``force=True``.

    Example::

        >>> DecisionLog(store, ev, now=clock.time, enabled=True).write([line])  # doctest: +SKIP
        True
    """

    def __init__(
        self,
        store: StateStore,
        ev: CanonicalEvent,
        *,
        now: Callable[[], float],
        enabled: bool,
        canary: bool = False,
    ) -> None:
        self._store = store
        self._ev = ev
        self._now = now
        self._enabled = enabled
        self._canary = canary

    def write(self, lines: Iterable[LogLine], *, force: bool = False) -> bool:
        """Append ``lines``; False when one could not be written (the caller notes it once)."""
        if not (self._enabled or force):
            return True
        records = [self._record(line) for line in lines]
        if not records:
            return True
        try:
            root = self._store.private_dir("")
            for record in records:
                append_decision(root, record)
        except (StateUnavailable, OSError, ValueError):
            return False
        return True

    def _record(self, line: LogLine) -> GuardDecisionRecord:
        ev, tool = self._ev, self._ev.tool
        return {
            "v": 1,
            "ts": iso_utc(self._now()),
            "harness": ev.harness.value,
            "session_id": ev.session_id,
            "event": ev.name.value,
            "hook_id": line.hook_id,
            "rule_id": line.rule_id,
            "decision": "canary" if self._canary else line.decision,
            "effective": line.effective,
            "tool_name": None if tool is None else tool.name,
            "tool_class": None if tool is None else tool.tool_class.value,
            "unattended": ev.unattended,
            "degraded": line.degraded,
            "escape": line.escape,
            "canary": self._canary,
            "latency_ms": line.latency_ms,
        }
