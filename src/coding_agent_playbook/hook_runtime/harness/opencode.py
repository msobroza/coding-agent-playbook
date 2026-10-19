"""OpenCode V1: parse the shim's payload, render ``playbook.hook.wire/1`` (specs/prK-lifecycle-hooks.md §D.2.2, §D.3.5).

**Parsing.** The shim (§C.3.2) sends a Claude-shaped payload: Claude tool
names (``apply_patch`` and unmapped tools pass through), OpenCode's native
arguments plus the §C.3.3 snake_case aliases, ``cwd`` = the shim's ``ROOT``.
The project root comes from ``--project-dir``, never from the payload's
worktree, which is ``/`` outside git. Every OpenCode event is unattended: the
plugin can only throw or pass, so an ask always degrades (§D.3.6).

**Rendering.** stdout is always exactly ``{"v": 1, "decision": "deny" |
"context" | "none", "reason", "context": [...], "notice"}``, ``notice``
carrying the user notes. The process exits ``DENY_EXIT`` iff a
``pre_tool_use`` is denied (the shim throws); a Stop deny is returned on
stdout with exit 0, because ``session.idle`` cannot block and the shim
carries it into the next turn (§C.3.6).
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, supported_decision
from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, EventName, Harness
from coding_agent_playbook.hook_runtime.harness._render import (
    context_items,
    dump,
    field_text,
    reason_text,
)
from coding_agent_playbook.hook_runtime.harness._tools import build_tool_call
from coding_agent_playbook.hook_runtime.harness.payload import (
    build_event,
    decode_object,
    fault,
    opt_str,
)
from coding_agent_playbook.hook_runtime.harness.wire import (
    CLAUDE_EVENT_NAMES,
    DENY_EXIT,
    ForeignPayload,
    WireOutput,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.dispatch.decision import CombinedResult
    from coding_agent_playbook.hook_runtime.dispatch.event import ToolCall
    from coding_agent_playbook.hook_runtime.harness.payload import Payload
    from coding_agent_playbook.hook_runtime.harness.wire import ParseContext, ParseOutcome

__all__ = [
    "NATIVE_TOOL_NAMES",
    "OPENCODE_SHIM_REL",
    "V1_ARG_ALIASES",
    "WIRE_VERSION",
    "parse_opencode",
    "render_opencode",
]

WIRE_VERSION: Final = 1

#: The generated V1 shim that spawns this dispatcher, repo-relative (§C.3.1). The
#: runtime owns the value so ``doctor`` can check the shim without importing the
#: engine; ``hook_registrations.OPENCODE_SHIM_PATH`` is this same constant.
OPENCODE_SHIM_REL: Final = ".opencode/plugins/playbook-hooks.js"

#: The inverse of the shim's ``TOOL`` map (§C.3.2): Claude-shaped -> OpenCode V1 name.
#: ``Task`` is accepted beside ``Agent`` (PR #52765 uses it).
NATIVE_TOOL_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "Bash": "bash",
        "Edit": "edit",
        "Write": "write",
        "Read": "read",
        "Glob": "glob",
        "Grep": "grep",
        "WebFetch": "webfetch",
        "WebSearch": "websearch",
        "Agent": "task",
        "Task": "task",
        "TodoWrite": "todowrite",
        "AskUserQuestion": "question",
        "Skill": "skill",
    }
)

#: The shim's ``ALIAS`` table (§C.3.3, §D.2.2): V1 native argument -> the
#: snake_case alias the shim adds beside it. Both spellings reach the
#: normalizer, which reads either; a glob/grep ``path`` is a search directory
#: and is never aliased to ``file_path``. test_wire_contract pins the template to it.
V1_ARG_ALIASES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "filePath": "file_path",
        "oldString": "old_string",
        "newString": "new_string",
        "replaceAll": "replace_all",
        "patchText": "patch_text",
        "include": "glob",
    }
)


def parse_opencode(payload: bytes, ctx: ParseContext) -> ParseOutcome:
    """Normalize the shim's payload, or say why it is foreign or faulty.

    Example::

        parse_opencode(b'{"hook_event_name": "Stop", "session_id": "s", "cwd": "/r"}',
                       ParseContext(argv_event=EventName.STOP, env={}, project_dir="/r"))
    """
    decoded = decode_object(payload, truncated=ctx.truncated)
    if isinstance(decoded, str):
        return fault(ctx, decoded)
    if decoded.get("hook_event_name") != CLAUDE_EVENT_NAMES[ctx.argv_event]:
        return ForeignPayload(event=ctx.argv_event, marker="event_mismatch")
    project_dir = ctx.project_dir or opt_str(decoded, "cwd")
    if not project_dir:
        return fault(ctx, "no project dir: --project-dir is missing and so is cwd", decoded)
    return build_event(
        decoded, ctx, harness=Harness.OPENCODE, project_dir=project_dir, tool_builder=_tool
    )


def _tool(payload: Payload, ev: CanonicalEvent, ctx: ParseContext) -> ToolCall | str:
    return build_tool_call(payload, ev, ctx, native_names=NATIVE_TOOL_NAMES)


def render_opencode(event: EventName, combined: CombinedResult) -> WireOutput:
    """The ``playbook.hook.wire/1`` stdout and exit code for ``combined`` on ``event``.

    An ask never reaches the wire: OpenCode has no ask primitive, so one that
    survived ``combine`` is rendered as the deny it degrades to (§C.3.4).

    Example::

        >>> render_opencode(EventName.PRE_TOOL_USE, CombinedResult(decision=Decision.DENY)).exit_code
        10
    """
    decision = supported_decision(event, combined.decision)
    if decision is Decision.ASK:
        decision = Decision.DENY
    body = {
        "v": WIRE_VERSION,
        "decision": decision.value,
        "reason": reason_text(combined, decision) if decision is Decision.DENY else "",
        "context": list(context_items(combined)) if decision is Decision.CONTEXT else [],
        "notice": field_text("\n".join(combined.user_notes)),
    }
    denied = decision is Decision.DENY and event is EventName.PRE_TOOL_USE
    return WireOutput(dump(body), "", DENY_EXIT if denied else 0)
