"""Claude Code: parse the hook payload, render the hook output (specs/prK-lifecycle-hooks.md §D.2.2, §D.3.5).

**Parsing.** The §C.5.2 foreign-payload heuristic runs before anything else:
other harnesses (Cursor, Copilot CLI, VS Code) read ``.claude/settings.json``
and reach this dispatcher with payloads that only look similar, and inert
beats a mis-normalized guard that false-denies. A payload that passes it but
is still unusable is a ``ContractFault``. Unknown keys are ignored.

**Rendering.** Output comes only from a closed key allowlist:
``hookSpecificOutput.{hookEventName, permissionDecision (deny|ask),
permissionDecisionReason, additionalContext}``, top-level ``decision:
"block"``, ``reason`` and ``systemMessage``. A ``pre_tool_use`` deny also puts
its reason on stderr and exits ``DENY_EXIT``, which the launcher maps to
Claude's exit 2: that channel survives a shell profile corrupting stdout. A
Stop context-only result is a ``systemMessage``, never ``additionalContext``,
which on Stop would force the agent to continue (D-3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.decision import Decision, supported_decision
from coding_agent_playbook.hook_runtime.event import (
    CanonicalEvent,
    EventName,
    Harness,
    sanitize_session_id,
)
from coding_agent_playbook.hook_runtime.harness import (
    CLAUDE_EVENT_NAMES,
    DENY_EXIT,
    ForeignPayload,
    WireOutput,
)
from coding_agent_playbook.hook_runtime.harness._payload import (
    build_event,
    decode_object,
    fault,
    opt_str,
)
from coding_agent_playbook.hook_runtime.harness._render import (
    context_items,
    dump,
    field_text,
    reason_text,
)
from coding_agent_playbook.hook_runtime.harness._tools import build_tool_call

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.decision import CombinedResult
    from coding_agent_playbook.hook_runtime.event import ToolCall
    from coding_agent_playbook.hook_runtime.harness import ParseContext, ParseOutcome
    from coding_agent_playbook.hook_runtime.harness._payload import Payload

__all__ = ["PROJECT_DIR_ENV", "parse_claude", "render_claude"]

#: Claude sets it for every hook; Copilot CLI sets nothing, so its absence is foreign.
PROJECT_DIR_ENV: Final = "CLAUDE_PROJECT_DIR"
#: Keys that only foreign harnesses send (Cursor; §C.5.2).
_FOREIGN_KEYS: Final = ("cursor_version", "conversation_id")
_STOP_EVENTS = frozenset({EventName.STOP, EventName.SUBAGENT_STOP})

type _Body = dict[str, object]


def parse_claude(payload: bytes, ctx: ParseContext) -> ParseOutcome:
    """Normalize a Claude Code hook payload, or say why it is foreign or faulty.

    ``ctx.project_dir`` (``--project-dir``) wins over ``CLAUDE_PROJECT_DIR``,
    which stays at the session root while ``cwd`` follows the agent.

    Example::

        parse_claude(b'{"hook_event_name": "Stop", "session_id": "s", "cwd": "/r"}',
                     ParseContext(argv_event=EventName.STOP, env={"CLAUDE_PROJECT_DIR": "/r"}))
    """
    decoded = decode_object(payload, truncated=ctx.truncated)
    if isinstance(decoded, str):
        if not ctx.env.get(PROJECT_DIR_ENV):
            return ForeignPayload(event=ctx.argv_event, marker="claude_project_dir_unset")
        return fault(ctx, decoded)
    marker = _foreign_marker(decoded, ctx)
    if marker is not None:
        session = sanitize_session_id(opt_str(decoded, "session_id"))
        return ForeignPayload(event=ctx.argv_event, marker=marker, session_id=session)
    project_dir = ctx.project_dir or ctx.env[PROJECT_DIR_ENV]
    return build_event(
        decoded, ctx, harness=Harness.CLAUDE_CODE, project_dir=project_dir, tool_builder=_tool
    )


def _foreign_marker(payload: Payload, ctx: ParseContext) -> str | None:
    """The first §C.5.2 heuristic the payload trips, most specific first, or ``None``."""
    for key in _FOREIGN_KEYS:
        if key in payload:
            return f"foreign_marker:{key}"
    if "timestamp" in payload:
        return "timestamp"
    if payload.get("hook_event_name") != CLAUDE_EVENT_NAMES[ctx.argv_event]:
        return "event_mismatch"
    if not opt_str(payload, "session_id"):
        return "missing_session_id"
    if not ctx.env.get(PROJECT_DIR_ENV):
        return "claude_project_dir_unset"
    return None


def _tool(payload: Payload, ev: CanonicalEvent, ctx: ParseContext) -> ToolCall | str:
    return build_tool_call(payload, ev, ctx)


def render_claude(event: EventName, combined: CombinedResult) -> WireOutput:
    """Claude's stdout JSON, stderr and exit code for ``combined`` on ``event``.

    The decision is first mapped down to what ``event`` can express, so no
    result can produce an output the event does not allow.

    Example::

        >>> render_claude(EventName.STOP, CombinedResult(decision=Decision.DENY, reason="RED")).stdout
        '{"decision":"block","reason":"RED"}\\n'
    """
    decision = supported_decision(event, combined.decision)
    body, stderr, exit_code = _decision_body(event, decision, combined)
    notes = list(combined.user_notes)
    if event in _STOP_EVENTS and decision is Decision.CONTEXT:
        notes[:0] = context_items(combined)
    if notes:
        body["systemMessage"] = field_text("\n".join(notes))
    return WireOutput(dump(body) if body else "", stderr, exit_code)


def _decision_body(
    event: EventName, decision: Decision, combined: CombinedResult
) -> tuple[_Body, str, int]:
    """``(body, stderr, exit_code)`` for the decision itself, before any user notes."""
    if decision in (Decision.DENY, Decision.ASK):
        reason = reason_text(combined, decision)
        if event is not EventName.PRE_TOOL_USE:
            return {"decision": "block", "reason": reason}, "", 0
        body = _specific(event, permissionDecision=decision.value, permissionDecisionReason=reason)
        return (body, f"{reason}\n", DENY_EXIT) if decision is Decision.DENY else (body, "", 0)
    items = context_items(combined) if decision is Decision.CONTEXT else ()
    if items and event not in _STOP_EVENTS:
        return _specific(event, additionalContext="\n".join(items)), "", 0
    return {}, "", 0


def _specific(event: EventName, **fields: str) -> _Body:
    return {"hookSpecificOutput": {"hookEventName": CLAUDE_EVENT_NAMES[event], **fields}}
