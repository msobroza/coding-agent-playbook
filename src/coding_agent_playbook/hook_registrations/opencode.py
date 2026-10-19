"""OpenCode V1 rendering of a registration plan: the shim and its ``REG`` (specs/prK-lifecycle-hooks.md §C.3).

:func:`to_opencode_reg` turns a plan into the one object the packaged shim
template embeds in place of its :data:`REG_PLACEHOLDER`:
``{event: {"timeout_ms": int, "tools": [V1 name, ...] | "*"}}``. The shim's
``wants()`` pre-filters on it, its kill timer reads ``timeout_ms``, and
``session_start`` is always present for the bootstrap and the inactive notice.

Every string in ``REG`` comes from a closed vocabulary (the canonical event
names, :data:`OPENCODE_V1_TOOLS`, ``"*"``), never from a hook author: a
``tool_names`` regex only selects names from the closed table. So the
``str.replace`` placeholder can never carry JS. :func:`plan_opencode_reg` is the
adapter's one call; it takes the deadlines over every enabled hook, exactly as
``guard_config.json`` does, so the shim never kills the dispatcher before its
watchdog has written a decided result (§D.4). :func:`render_opencode_shim`
fills the template into the one file the OpenCode adapter owns,
:data:`OPENCODE_SHIM_PATH` (§C.3.1).
"""

from __future__ import annotations

import json
import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal, NotRequired, TypedDict

from coding_agent_playbook.generated_output.sentinel import sentinel_line
from coding_agent_playbook.hook_policy import HOOK_EVENTS, TOOL_CLASS_NAMES
from coding_agent_playbook.hook_registrations._templates import (
    SENTINEL_PLACEHOLDER,
    fill_placeholder,
    shim_template,
)
from coding_agent_playbook.hook_registrations.plan import (
    BOOTSTRAP_DEADLINE_MS,
    HookRegistration,
    checked_registration_timeout_s,
    plan_registrations,
    resolved_deadlines_ms,
)
from coding_agent_playbook.hook_runtime.event import Harness
from coding_agent_playbook.hook_runtime.harness.opencode import (
    NATIVE_TOOL_NAMES,
    OPENCODE_SHIM_REL,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from coding_agent_playbook.artifacts.hook_schema import HookMatcher
    from coding_agent_playbook.hook_policy import ResolvedHook

__all__ = [
    "OPENCODE_REG_EVENTS",
    "OPENCODE_SHIM_PATH",
    "OPENCODE_V1_TOOLS",
    "REG_PLACEHOLDER",
    "OpenCodeRegEntry",
    "opencode_reg_json",
    "plan_opencode_reg",
    "render_opencode_shim",
    "to_opencode_reg",
]

#: The one generated OpenCode V1 plugin, repo-relative (§C.3.1). V1's
#: non-recursive ``{plugin,plugins}/*.{ts,js}`` scan finds it, so ``opencode.json``
#: is never touched; every other file under ``.opencode/plugin(s)/`` is the user's.
OPENCODE_SHIM_PATH: Final = OPENCODE_SHIM_REL  # one value: doctor reads it from the runtime
#: Where ``REG`` goes in the template: a JS comment, never code an author controls.
REG_PLACEHOLDER: Final = "/*@@REG@@*/"
_SHIM_TEMPLATE: Final = "opencode-plugin.js"

#: The events the shim forwards, in canonical order: the keys of its ``EVENT``
#: table. ``pre_compact`` has no V1 hook, so it is never one (§C.1.2, §C.5).
OPENCODE_REG_EVENTS: Final = ("session_start", "pre_tool_use", "post_tool_use", "stop")

#: ``tools`` when a member filters no tool: the shim forwards every call.
_ALL_TOOLS: Final = "*"

_OPENCODE: Final = Harness.OPENCODE.value
#: Events whose matcher filters tools, so whose entry carries ``tools``.
_TOOL_EVENTS: Final = frozenset(
    e for e in OPENCODE_REG_EVENTS if "tools" in HOOK_EVENTS[e].matcher_fields
)


def _v1_claude_names() -> Mapping[str, frozenset[str]]:
    """Native V1 tool -> the names the dispatcher fullmatches ``tool_names`` against.

    The inverse of the shim's ``TOOL`` map (``task`` -> ``Agent``, ``Task``),
    plus the tool-class column; a tool the map lacks (``apply_patch``) passes
    through under its own name, as the runtime parser reads it.
    """
    column = {name for row in TOOL_CLASS_NAMES.values() for name in row.get(_OPENCODE, ())}
    natives = column | set(NATIVE_TOOL_NAMES.values())
    return MappingProxyType(
        {
            native: frozenset(c for c, n in NATIVE_TOOL_NAMES.items() if n == native)
            or frozenset({native})
            for native in sorted(natives)
        }
    )


_V1_CLAUDE_NAMES: Final = _v1_claude_names()
#: Every tool name ``REG`` may hold: the closed OpenCode V1 vocabulary.
OPENCODE_V1_TOOLS: Final = frozenset(_V1_CLAUDE_NAMES)


#: One ``REG`` value: the shim's kill timer and, on tool events, its pre-filter.
#: ``async`` (``post_tool_use`` only) is the pre-filter of the fire-and-forget
#: ``--async`` dispatch (OQ-19); functional syntax because ``async`` is a keyword.
OpenCodeRegEntry = TypedDict(
    "OpenCodeRegEntry",
    {
        "timeout_ms": int,
        "tools": NotRequired[list[str] | Literal["*"]],
        "async": NotRequired[list[str] | Literal["*"]],
    },
)


def plan_opencode_reg(hooks: Sequence[ResolvedHook]) -> dict[str, OpenCodeRegEntry]:
    """``REG`` for every enabled hook: the members support OpenCode, the deadlines span all.

    Pass every resolved hook, whatever its ``supports``: ``guard_config.json``
    holds one deadline per event for all harnesses, so the registration
    timeouts must be planned against that same deadline (§D.4).

    Example::

        >>> plan_opencode_reg([hook])  # a 2 s opencode pre_tool_use hook  # doctest: +SKIP
        {'session_start': {'timeout_ms': 4000}, 'pre_tool_use': {'timeout_ms': 4000, 'tools': '*'}}
    """
    regs = plan_registrations(hooks, _OPENCODE, deadlines=resolved_deadlines_ms(hooks))
    return to_opencode_reg(regs)


def to_opencode_reg(regs: Iterable[HookRegistration]) -> dict[str, OpenCodeRegEntry]:
    """The shim's ``REG`` for a plan made for ``opencode``, in canonical event order.

    One key per :data:`OPENCODE_REG_EVENTS` event with a member (any other is
    dropped), ``session_start`` added whenever any key exists, and ``{}``
    otherwise. ``timeout_ms`` is the registration timeout in milliseconds,
    re-checked against the watchdog margin (raises ``RegistrationTimeoutError``).
    An async registration (OQ-19) becomes the ``post_tool_use`` entry's
    ``async`` pre-filter; with no synchronous member its ``tools`` is ``[]``.

    Example::

        >>> to_opencode_reg(plan_registrations(hooks, "opencode"))  # doctest: +SKIP
        {'session_start': {'timeout_ms': 4000}, 'stop': {'timeout_ms': 5000}}
    """
    listed = [reg for reg in regs if reg.event in OPENCODE_REG_EVENTS]
    background = next((reg for reg in listed if reg.asynchronous and reg.members), None)
    by_event = {
        reg.event: reg
        for reg in listed
        if not reg.asynchronous and (reg.members or reg.event == "session_start")
    }
    if background is None and not any(reg.members for reg in by_event.values()):
        return {}
    by_event.setdefault("session_start", _bootstrap())
    reg_table: dict[str, OpenCodeRegEntry] = {
        event: _entry(by_event[event]) for event in OPENCODE_REG_EVENTS if event in by_event
    }
    if background is not None:
        _add_async(reg_table, background)
    return {event: reg_table[event] for event in OPENCODE_REG_EVENTS if event in reg_table}


def opencode_reg_json(reg: Mapping[str, OpenCodeRegEntry]) -> str:
    """``REG`` as the shim embeds it: key-sorted, compact, ASCII-only JSON.

    Example: ``opencode_reg_json({"stop": {"timeout_ms": 5000}}) == '{"stop":{"timeout_ms":5000}}'``.
    """
    return json.dumps(reg, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def render_opencode_shim(
    reg: Mapping[str, OpenCodeRegEntry], *, template: str | None = None
) -> str:
    """The text of :data:`OPENCODE_SHIM_PATH` for ``reg`` (§C.3.1, §C.3.2).

    The packaged template's line-1 placeholder becomes the ``//`` sentinel line
    and :data:`REG_PLACEHOLDER` the :func:`opencode_reg_json` bytes; ``template``
    replaces the packaged text (tests). Raises ValueError unless each
    placeholder occurs exactly once. Pure: no shebang, LF only, nothing
    machine-specific, so every clone renders the same bytes.

    Example: ``render_opencode_shim(reg).splitlines()[0] == sentinel_line("slash")``.
    """
    text = shim_template(_SHIM_TEMPLATE) if template is None else template
    text = fill_placeholder(text, SENTINEL_PLACEHOLDER, sentinel_line("slash"))
    return fill_placeholder(text, REG_PLACEHOLDER, opencode_reg_json(reg))


def _bootstrap() -> HookRegistration:
    """A ``session_start`` with no member: the dispatcher's bootstrap only."""
    timeout_s = checked_registration_timeout_s("session_start", BOOTSTRAP_DEADLINE_MS)
    return HookRegistration(
        event="session_start", members=(), deadline_ms=BOOTSTRAP_DEADLINE_MS, timeout_s=timeout_s
    )


def _add_async(reg_table: dict[str, OpenCodeRegEntry], background: HookRegistration) -> None:
    """Attach the async pre-filter to ``post_tool_use``, creating a tool-less entry if needed."""
    entry = reg_table.get(background.event)
    if entry is None:
        entry = _entry(background)
        entry["tools"] = []  # no synchronous member: the shim never awaits a dispatch here
        reg_table[background.event] = entry
    entry["async"] = _opencode_tools(background.matchers)


def _entry(reg: HookRegistration) -> OpenCodeRegEntry:
    timeout_s = checked_registration_timeout_s(
        reg.event, reg.deadline_ms, formula=lambda _deadline: reg.timeout_s
    )
    entry: OpenCodeRegEntry = {"timeout_ms": timeout_s * 1000}
    if reg.event in _TOOL_EVENTS:
        entry["tools"] = _opencode_tools(reg.matchers)
    return entry


def _opencode_tools(matchers: Sequence[HookMatcher]) -> list[str] | Literal["*"]:
    """The sorted V1 names the members can match, or ``"*"`` when one filters no tool.

    Like Claude's matcher union, this is only a pre-filter (the dispatcher
    matches in-process), so it may be wider than a member, never narrower.
    """
    if not matchers or any(not m.tools and not m.tool_names for m in matchers):
        return _ALL_TOOLS
    names: set[str] = set()
    for matcher in matchers:
        by_class = _class_tools(matcher.tools)
        if by_class is None:
            return _ALL_TOOLS
        names |= by_class | _named_tools(matcher.tool_names)
    return sorted(names)


def _class_tools(classes: Iterable[str]) -> set[str] | None:
    """The V1 names of ``classes`` (``notebook_edit``/``mcp`` add none); None on an unknown one."""
    names: set[str] = set()
    for tool_class in classes:
        row = TOOL_CLASS_NAMES.get(tool_class)
        if row is None:
            return None  # validate rejects it (H4); never let it narrow the pre-filter
        names.update(row.get(_OPENCODE, ()))
    return names


def _named_tools(patterns: Iterable[str]) -> set[str]:
    """The closed-table tools whose native or Claude-shaped name a pattern fullmatches.

    The same test the dispatcher applies (``hook_runtime._selection``), so
    ``Agent`` selects ``task`` and ``mcp__.*`` selects nothing: OpenCode's MCP
    tools are ``<server>_<tool>`` and the shim never forwards them by name.
    """
    return {
        native
        for native, claude_names in _V1_CLAUDE_NAMES.items()
        for pattern in patterns
        if any(_fullmatch(pattern, name) for name in (native, *claude_names))
    }


def _fullmatch(pattern: str, value: str) -> bool:
    try:
        return re.fullmatch(pattern, value) is not None
    except re.error:
        return False  # validate rejects it (H4); a bad pattern selects nothing
