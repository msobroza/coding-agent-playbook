"""What the dispatcher decides itself when it cannot run the hooks (specs/prK-lifecycle-hooks.md §D.4).

- A ``ContractFault`` (an unusable payload, a bad dispatch argv) asks on
  ``pre_tool_use`` (``deny`` unattended) and is silent elsewhere: a usage
  error must never look like a deny, and must not let a tool call through
  unseen either.
- A ``ConfigFault`` (``guard_config.json`` missing, changed since sync, or
  newer than this engine) asks **once per session** on ``pre_tool_use``, then
  adds one degraded note; every other event only gets the note. Asking on
  every call would brick the session.

Both are logged as ``degraded`` (:func:`degraded_lines`), ids only.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._decision_log import DISPATCHER_ID, LogLine
from coding_agent_playbook.hook_runtime.config import CONFIG_FAULT_REASON
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.event import CanonicalEvent, EventName
from coding_agent_playbook.hook_runtime.policy import is_unattended

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.config import ConfigFault
    from coding_agent_playbook.hook_runtime.decision import Outcome
    from coding_agent_playbook.hook_runtime.event import Harness

__all__ = [
    "CONFIG_FAULT_NOTE",
    "CONTRACT_FAULT_REASON",
    "config_fault_results",
    "contract_fault_results",
    "degraded_lines",
    "fault_event",
]

CONTRACT_FAULT_REASON: Final = (
    "Playbook could not read this tool call ({problem}); confirm this action manually."
)
CONFIG_FAULT_NOTE: Final = (
    "Playbook guards are degraded this session: the guard configuration is missing or "
    "changed since sync ({kind}); ask the user to run playbook sync."
)
CONTRACT_FAULT_RULE: Final = "contract_fault"
CONFIG_FAULT_RULE: Final = "config_fault"


def fault_event(
    event: EventName,
    harness: Harness,
    *,
    session_id: str,
    project_dir: str,
    env: Mapping[str, str],
) -> CanonicalEvent:
    """A minimal event for a payload that never parsed: enough to combine, render and log.

    Example::

        >>> fault_event(EventName.STOP, Harness.OPENCODE, session_id="", project_dir="/r", env={}).unattended
        True
    """
    ev = CanonicalEvent(
        name=event, harness=harness, session_id=session_id, cwd=project_dir, project_dir=project_dir
    )
    return dataclasses.replace(ev, unattended=is_unattended(ev, env))


def contract_fault_results(event: EventName, problem: str) -> list[HandlerResult]:
    """An ask on ``pre_tool_use``, nothing elsewhere (§D.4's ``ContractFault`` row).

    Example::

        >>> contract_fault_results(EventName.STOP, "tool_name missing")
        []
    """
    if event is not EventName.PRE_TOOL_USE:
        return []
    return [
        HandlerResult(
            decision=Decision.ASK,
            hook_id=DISPATCHER_ID,
            rule_id=CONTRACT_FAULT_RULE,
            reason=CONTRACT_FAULT_REASON.format(problem=problem),
            degraded=True,
        )
    ]


def config_fault_results(
    event: EventName, fault: ConfigFault, once: Callable[[str], bool]
) -> list[HandlerResult]:
    """The results of a ``ConfigFault`` on ``event``: one ask per session, then one note.

    Example::

        >>> config_fault_results(EventName.PRE_TOOL_USE, fault, session.once)[0].decision
        ... # doctest: +SKIP
        <Decision.ASK: 'ask'>
    """
    rule_id = f"{CONFIG_FAULT_RULE}:{fault.kind}"
    if event is EventName.PRE_TOOL_USE and once("config_fault:ask"):
        return [
            HandlerResult(
                decision=Decision.ASK,
                hook_id=DISPATCHER_ID,
                rule_id=rule_id,
                reason=CONFIG_FAULT_REASON,
                degraded=True,
            )
        ]
    if not once("config_fault:note"):
        return []
    return [
        HandlerResult(
            decision=Decision.NONE,
            hook_id=DISPATCHER_ID,
            rule_id=rule_id,
            user_note=CONFIG_FAULT_NOTE.format(kind=fault.kind),
            degraded=True,
        )
    ]


def degraded_lines(outcomes: Sequence[Outcome]) -> list[LogLine]:
    """One ``degraded`` decision-log line per dispatcher-made result.

    Example::

        >>> degraded_lines(combined.outcomes)[0].decision  # doctest: +SKIP
        'degraded'
    """
    return [
        LogLine(
            hook_id=o.hook_id,
            rule_id=o.rule_id or None,
            decision="degraded",
            effective=o.effective.value,
            degraded=True,
        )
        for o in outcomes
    ]
