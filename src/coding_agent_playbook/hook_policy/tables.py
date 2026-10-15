"""The one home of the hook event, tool-class and adapter-support tables.

Every consumer reads these instead of re-declaring them: validate's
``classify_hook`` (H3-H5, H9-H11), the Claude and OpenCode renderers (§C.2.2,
§C.3), and the built-in adapters' ``hook_support`` ClassVars, which are taken
from :data:`HOOK_SUPPORT` (specs/prK-lifecycle-hooks.md §A.11, §C.1.2, §C.5.1).

Stdlib-only and sync-time only: the dispatcher reads the rendered
``guard_config.json``, never this module (§D.8). Every table is read-only, so a
caller cannot widen what another caller sees.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook._hook_schema import ADVISORY_RULE_PREFIX, ADVISORY_RULE_PRIORITY

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ADVISORY_RULE_PREFIX",
    "ADVISORY_RULE_PRIORITY",
    "DEGRADED_EVENTS",
    "HOOK_CAPABLE_ADAPTERS",
    "HOOK_EVENTS",
    "HOOK_SCRIPTS_DIR",
    "HOOK_SUPPORT",
    "ON_ERROR_STRENGTH",
    "TOOL_CLASS_NAMES",
    "EventSpec",
]


@dataclass(frozen=True)
class EventSpec:
    """One canonical hook event and what it may carry (the §A.2 event table).

    ``decisions`` are the only decisions a hook may emit on the event,
    ``on_error_allowed`` the failure policies it honours (the rest clamp to
    ``open``), ``matcher_fields`` the ``HookMatcher`` dimensions it accepts.

    Example::

        >>> HOOK_EVENTS["stop"].claude_name
        'Stop'
    """

    claude_name: str
    decisions: frozenset[str]
    on_error_allowed: frozenset[str]
    matcher_fields: frozenset[str]


def _spec(claude_name: str, decisions: str, on_error: str, matcher: str = "") -> EventSpec:
    return EventSpec(
        claude_name,
        frozenset(decisions.split()),
        frozenset(on_error.split()),
        frozenset(matcher.split()),
    )


_TOOL_MATCHER = "tools tool_names paths command"

#: Canonical events in canonical order: renderers append new event keys to
#: ``.claude/settings.json`` in this order (§C.2.2).
HOOK_EVENTS: Final[Mapping[str, EventSpec]] = MappingProxyType(
    {
        "session_start": _spec("SessionStart", "context none", "open", "sources"),
        "user_prompt_submit": _spec("UserPromptSubmit", "deny context none", "deny open"),
        "pre_tool_use": _spec(
            "PreToolUse", "deny ask context none", "ask deny open", _TOOL_MATCHER
        ),
        "post_tool_use": _spec("PostToolUse", "context none", "open", _TOOL_MATCHER),
        "post_tool_use_failure": _spec("PostToolUseFailure", "context none", "open", _TOOL_MATCHER),
        "stop": _spec("Stop", "deny context none", "open"),
        "subagent_stop": _spec("SubagentStop", "deny context none", "open", "agent_types"),
        "pre_compact": _spec("PreCompact", "none", "open", "triggers"),
        "session_end": _spec("SessionEnd", "none", "open"),
    }
)


def _names(
    claude_code: tuple[str, ...], opencode: tuple[str, ...]
) -> Mapping[str, tuple[str, ...]]:
    return MappingProxyType({"claude_code": claude_code, "opencode": opencode})


#: Tool class -> adapter -> harness tool names (§A.2). Claude names are matcher
#: fragments: ``mcp__.*`` is a regex, which makes the rendered matcher anchored
#: (§C.2.2). An empty tuple means the harness has no such tool, so a hook
#: matching that class is ``degraded`` there (validate warns).
TOOL_CLASS_NAMES: Final[Mapping[str, Mapping[str, tuple[str, ...]]]] = MappingProxyType(
    {
        "shell": _names(("Bash", "PowerShell"), ("bash",)),
        # MultiEdit is legacy but still tolerated (§A.2).
        "edit": _names(("Edit", "MultiEdit"), ("edit", "apply_patch")),
        "write": _names(("Write",), ("write", "apply_patch")),
        "notebook_edit": _names(("NotebookEdit",), ()),
        "read": _names(("Read",), ("read",)),
        "search": _names(("Glob", "Grep"), ("glob", "grep")),
        "web": _names(("WebFetch", "WebSearch"), ("webfetch", "websearch")),
        # Task is the older name of Agent.
        "subagent": _names(("Agent", "Task"), ("task",)),
        # OpenCode's <server>_<tool> names are indistinguishable from plugin tools.
        "mcp": _names(("mcp__.*",), ()),
    }
)

_OPENCODE_SUPPORT: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        # ask has no OpenCode primitive; the dispatcher degrades it to deny (§D.3.6).
        "pre_tool_use": frozenset({"deny", "ask", "context", "none"}),
        "post_tool_use": frozenset({"context", "none"}),
        "session_start": frozenset({"context", "none"}),
        "stop": frozenset({"deny", "context", "none"}),
    }
)

#: Adapter -> canonical event -> decisions it renders natively (the §C.5.1
#: matrix). An event missing from an adapter's row is unreachable there (H11).
#: Claude Code renders every decision of every event, so its row is the event
#: table itself.
HOOK_SUPPORT: Final[Mapping[str, Mapping[str, frozenset[str]]]] = MappingProxyType(
    {
        "claude_code": MappingProxyType(
            {event: spec.decisions for event, spec in HOOK_EVENTS.items()}
        ),
        "opencode": _OPENCODE_SUPPORT,
    }
)

#: Reachable but weaker cells (``playbook check`` label ``degraded``): OpenCode's
#: session_start rides an experimental API and its stop is evidence-only (§C.3.6).
DEGRADED_EVENTS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {"claude_code": frozenset(), "opencode": frozenset({"session_start", "stop"})}
)

#: The only adapters a hook may list in ``supports`` (H11).
HOOK_CAPABLE_ADAPTERS: Final[frozenset[str]] = frozenset(HOOK_SUPPORT)

#: ``on_error`` ordered weakest to strictest; an overlay may never lower it (H14).
ON_ERROR_STRENGTH: Final[Mapping[str, int]] = MappingProxyType({"open": 0, "ask": 1, "deny": 2})

#: Repo-relative POSIX dir that sync byte-copies external hook scripts into, as
#: ``<HOOK_SCRIPTS_DIR>/<hook-id>/`` (§C.0); guard_config.json holds only these
#: repo-relative paths, never absolute ones.
HOOK_SCRIPTS_DIR: Final = ".coding-agent-playbook/hooks/scripts"
