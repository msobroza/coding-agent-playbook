"""The shared half of both parsers: decode, read typed fields, build the event (§D.2.2).

Both harnesses deliver one Claude-shaped JSON object (the OpenCode shim
translates to it, §C.3.3), so decoding, the common fields and the per-event
fields are parsed here once. A field of the wrong type counts as absent:
unknown and malformed optional fields never fail an event (forward
compatibility); only the required tool fields do (``_tools``).
"""

from __future__ import annotations

import dataclasses
import json
import os
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hook_runtime.event import (
    CanonicalEvent,
    EventName,
    Harness,
    StopInfo,
    ToolCall,
    sanitize_session_id,
)
from coding_agent_playbook.hook_runtime.harness import STDIN_CAP_BYTES, ContractFault
from coding_agent_playbook.hook_runtime.paths import normalize_path
from coding_agent_playbook.hook_runtime.policy import is_unattended

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.hook_runtime.harness import ParseContext

#: A decoded payload: one JSON object with string keys.
type Payload = dict[str, Any]
#: Builds the event's ``ToolCall`` (paths resolve against ``ev.cwd`` and
#: ``ev.repo``), or returns the problem that makes it a ``ContractFault``.
type ToolBuilder = Callable[[Payload, CanonicalEvent, ParseContext], ToolCall | str]

_UTF8_BOM = b"\xef\xbb\xbf"
_TOOL_EVENTS = frozenset(
    {EventName.PRE_TOOL_USE, EventName.POST_TOOL_USE, EventName.POST_TOOL_USE_FAILURE}
)


def decode_object(raw: bytes, *, truncated: bool) -> Payload | str:
    """The payload's one JSON object, or the problem with it.

    A leading UTF-8 BOM is dropped first: Cursor on Windows prepends one
    (§C.5.2). Example: ``decode_object(b'{"a": 1}', truncated=False) == {"a": 1}``.
    """
    try:
        value = json.loads(raw.removeprefix(_UTF8_BOM).decode("utf-8"))
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError alike
        cut = f"; stdin exceeded the {STDIN_CAP_BYTES >> 20} MiB cap" if truncated else ""
        return f"payload is not valid JSON (UTF-8){cut}: {type(exc).__name__}"
    if not isinstance(value, dict):
        return f"payload is not a JSON object (got {type(value).__name__})"
    return value


def opt_str(obj: Mapping[str, Any], key: str) -> str | None:
    """``obj[key]`` when it is a string, else ``None``."""
    value = obj.get(key)
    return value if isinstance(value, str) else None


def fault(ctx: ParseContext, problem: str, payload: Payload | None = None) -> ContractFault:
    """A ``ContractFault`` for ``ctx``'s event, carrying the session id when there is one."""
    session = opt_str(payload, "session_id") if payload is not None else None
    return ContractFault(
        event=ctx.argv_event, problem=problem, session_id=sanitize_session_id(session)
    )


def host_path(raw: str, *, base: str, ctx: ParseContext) -> str:
    """``raw`` (absolute, or relative to ``base``) normalized and symlink-resolved."""
    return normalize_path(raw, base=base, repo=None, home=ctx.home, platform=ctx.platform).realpath


def build_event(
    payload: Payload,
    ctx: ParseContext,
    *,
    harness: Harness,
    project_dir: str,
    tool_builder: ToolBuilder,
) -> CanonicalEvent | ContractFault:
    """The ``CanonicalEvent`` of a payload that passed its harness's foreign check.

    ``project_dir`` is the raw project root (``--project-dir``, else the
    harness's own source); the repository is discovered from it, ``cwd``
    resolves against it, and ``unattended`` is computed once, here.

    Example::

        build_event({"session_id": "s", "cwd": "/r"}, ctx, harness=Harness.CLAUDE_CODE,
                    project_dir="/r", tool_builder=build_tool_call)
    """
    root = host_path(project_dir, base=os.getcwd(), ctx=ctx)
    cwd = host_path(opt_str(payload, "cwd") or root, base=root, ctx=ctx)
    ev = CanonicalEvent(
        name=ctx.argv_event,
        harness=harness,
        session_id=opt_str(payload, "session_id") or "",
        turn_id=opt_str(payload, "prompt_id"),
        cwd=cwd,
        project_dir=root,
        repo=ctx.find_repo(root),
        permission_mode=opt_str(payload, "permission_mode"),
        agent_id=opt_str(payload, "agent_id"),
        agent_type=opt_str(payload, "agent_type"),
        transcript_path=opt_str(payload, "transcript_path"),
        truncated=ctx.truncated,
        raw_event_name=opt_str(payload, "hook_event_name") or "",
        **_event_fields(payload, ctx.argv_event),
    )
    if ev.name in _TOOL_EVENTS:
        tool = tool_builder(payload, ev, ctx)
        if isinstance(tool, str):
            return fault(ctx, tool, payload)
        ev = dataclasses.replace(ev, tool=tool)
    return dataclasses.replace(ev, unattended=is_unattended(ev, ctx.env))


def _event_fields(payload: Payload, event: EventName) -> dict[str, Any]:
    """The fields only some events carry: prompt, source/trigger, stop info."""
    if event is EventName.USER_PROMPT_SUBMIT:
        return {"prompt": opt_str(payload, "prompt")}
    if event is EventName.SESSION_START:
        return {"source": opt_str(payload, "source")}
    if event is EventName.PRE_COMPACT:
        return {"source": opt_str(payload, "trigger")}
    if event in (EventName.STOP, EventName.SUBAGENT_STOP):
        return {"stop": _stop_info(payload, event)}
    return {}


def _stop_info(payload: Payload, event: EventName) -> StopInfo:
    transcript = opt_str(payload, "agent_transcript_path")
    return StopInfo(
        stop_hook_active=payload.get("stop_hook_active") is True,
        last_assistant_message=opt_str(payload, "last_assistant_message") or "",
        agent_transcript_path=transcript if event is EventName.SUBAGENT_STOP else None,
    )
