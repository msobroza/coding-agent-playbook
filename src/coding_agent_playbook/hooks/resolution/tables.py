"""The one home of the hook event, tool-class and adapter-support tables.

Every consumer reads these instead of re-declaring them: validate's
``classify_hook`` (H3-H5, H9-H11), the Claude and OpenCode renderers (§C.2.2,
§C.3), and the built-in adapters' ``hook_support`` ClassVars, which are taken
from :data:`HOOK_SUPPORT` (specs/prK-lifecycle-hooks.md §A.11, §C.1.2, §C.5.1).

Sync-time only, stdlib plus the import-light ``hook_runtime`` tables it shares
with the dispatcher (each table has one source): the dispatcher reads the
rendered ``guard_config.json``, never this module (§D.8). Every table is
read-only, so a caller cannot widen what another caller sees.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.hook_schema import ADVISORY_RULE_PREFIX, ADVISORY_RULE_PRIORITY
from coding_agent_playbook.hook_runtime.decision import EVENT_DECISIONS
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.harness.wire import CLAUDE_EVENT_NAMES
from coding_agent_playbook.hook_runtime.policy import (
    ENGINE_DEADLINE_CAP_MS as RUNTIME_DEADLINE_CAP_MS,
)
from coding_agent_playbook.hook_runtime.policy import ON_ERROR_ALLOWED

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ADVISORY_RULE_PREFIX",
    "ADVISORY_RULE_PRIORITY",
    "DEGRADED_EVENTS",
    "ENGINE_DEADLINE_CAP_MS",
    "HOOK_CAPABLE_ADAPTERS",
    "HOOK_EVENTS",
    "HOOK_SCRIPTS_DIR",
    "HOOK_SUPPORT",
    "MATCHER_VALUES",
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


def _spec(event: EventName, matcher: str = "") -> EventSpec:
    """``event``'s row, its decisions and ``on_error`` values taken from the runtime's tables."""
    return EventSpec(
        CLAUDE_EVENT_NAMES[event],
        frozenset(decision.value for decision in EVENT_DECISIONS[event]),
        frozenset(ON_ERROR_ALLOWED[event]),
        frozenset(matcher.split()),
    )


_TOOL_MATCHER = "tools tool_names paths command"
_MATCHER_FIELDS: Final[Mapping[EventName, str]] = MappingProxyType(
    {
        EventName.SESSION_START: "sources",
        EventName.PRE_TOOL_USE: _TOOL_MATCHER,
        EventName.POST_TOOL_USE: _TOOL_MATCHER,
        EventName.POST_TOOL_USE_FAILURE: _TOOL_MATCHER,
        EventName.SUBAGENT_STOP: "agent_types",
        EventName.PRE_COMPACT: "triggers",
    }
)

#: Canonical events in canonical order: renderers append new event keys to
#: ``.claude/settings.json`` in this order (§C.2.2). Event names, Claude names,
#: decisions and ``on_error`` values have one source, the runtime (``hook_runtime``
#: ``event``, ``harness``, ``decision``, ``policy``); sync adds the matcher fields.
HOOK_EVENTS: Final[Mapping[str, EventSpec]] = MappingProxyType(
    {event.value: _spec(event, _MATCHER_FIELDS.get(event, "")) for event in EventName}
)


#: The matcher fields with a closed vocabulary (§A.2): an authored value outside
#: it could never match, so validate rejects it (H4). The other fields are open.
MATCHER_VALUES: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "sources": frozenset({"startup", "resume", "clear", "compact", "fork"}),
        "triggers": frozenset({"manual", "auto"}),
    }
)

#: The most a whole event may take, per event (the §D.4 timeout formula):
#: ``deadline_ms = min(cap, Σ timeout_ms of its enabled hooks)``. A hook timeout
#: above its event's cap is clamped, with a validate warning (H9). The runtime's
#: ``policy.ENGINE_DEADLINE_CAP_MS`` is the source; this is its string-keyed view.
ENGINE_DEADLINE_CAP_MS: Final[Mapping[str, int]] = MappingProxyType(
    {event.value: cap for event, cap in RUNTIME_DEADLINE_CAP_MS.items()}
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
