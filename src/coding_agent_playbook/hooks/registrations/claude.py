"""Claude Code rendering of a registration plan (specs/prK-lifecycle-hooks.md §C.2.1, §C.2.2, §C.2.7).

:func:`to_claude_group` is the managed matcher group with its closed key set and
the exact launcher command; :func:`matcher_union` its matcher string;
:func:`render_claude_launcher` the committed launcher, from a packaged
one-placeholder template (``str.replace``, never Jinja: L7).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.generated_output.sentinel import sentinel_line
from coding_agent_playbook.hook_runtime.cli import ASYNC_FLAG
from coding_agent_playbook.hook_runtime.event import Harness
from coding_agent_playbook.hook_runtime.stop.stages import DEFAULT_BUDGET_S
from coding_agent_playbook.hooks.registrations._templates import (
    SENTINEL_PLACEHOLDER,
    fill_placeholder,
    shim_template,
)
from coding_agent_playbook.hooks.registrations.launcher import LAUNCHER_TOKEN
from coding_agent_playbook.hooks.registrations.plan import (
    STOP_EVENTS,
    deadlines_ms,
    plan_registrations,
)
from coding_agent_playbook.hooks.resolution.tables import TOOL_CLASS_NAMES

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.artifacts.hook_schema import HookMatcher
    from coding_agent_playbook.hooks.registrations.plan import HookRegistration, RegistrationMember

__all__ = [
    "STOP_STATUS_MESSAGE",
    "STRICT_LAUNCH_FLAG",
    "claude_command",
    "claude_settings_projection",
    "matcher_union",
    "render_claude_launcher",
    "to_claude_group",
]

#: Makes the launcher exit 1 on a missing pin or a crash (overlay strict mode, OQ-18).
STRICT_LAUNCH_FLAG: Final = "--strict-launch"
#: Shown by Claude while the Stop coordinator runs; only stop events carry it.
STOP_STATUS_MESSAGE: Final = "playbook: verifying before stop"

_TOOL_EVENTS: Final = frozenset({"pre_tool_use", "post_tool_use", "post_tool_use_failure"})
_TRIGGERS: Final = frozenset({"manual", "auto"})
#: A matcher fragment Claude reads as an exact name (§C.2.2); anything else is a regex.
_PLAIN_NAME: Final = re.compile(r"[A-Za-z0-9_-]+")
_REGEX_META: Final = re.compile(r"([.^$*+?()\[\]{}|\\/])")
_PROJECT_ROOT: Final = (
    "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
)
_LAUNCHER_TEMPLATE: Final = "claude-launch.sh"
_CLAUDE: Final = Harness.CLAUDE_CODE.value


def matcher_union(event: str, matchers: Sequence[HookMatcher]) -> str | None:
    """The Claude matcher of a registration, or None when it must be omitted (§C.2.2).

    Tool events: ``*`` when a member matches every tool, a sorted exact list
    (``Edit`` never matches ``NotebookEdit``) when every name is plain, else the
    whole list anchored ``^(?:…)$``. ``subagent_stop``: the agent types (anchored
    once a ``plugin:agent`` name appears), omitted when a member is unfiltered.
    ``pre_compact``: the one trigger, omitted for both. Other events: omitted.

    Example: ``matcher_union("pre_tool_use", [HookMatcher(tools=["edit"])]) == "Edit|MultiEdit"``.
    """
    if event in _TOOL_EVENTS:
        return _tool_union(matchers)
    if event == "subagent_stop":
        return _agent_union(matchers)
    if event == "pre_compact":
        return _trigger_union(matchers)
    return None


def _tool_union(matchers: Sequence[HookMatcher]) -> str | None:
    if not matchers:
        return None
    if any(not m.tools and not m.tool_names for m in matchers):
        return "*"
    names = {
        name
        for m in matchers
        for tool_class in m.tools
        for name in TOOL_CLASS_NAMES.get(tool_class, {}).get(_CLAUDE, ())
    }
    names.update(name for m in matchers for name in m.tool_names)
    # The union is only a pre-filter (the dispatcher matches in-process), so a
    # member naming no known tool widens it to every tool rather than to none.
    return _exact_or_anchored(sorted(names)) if names else "*"


def _agent_union(matchers: Sequence[HookMatcher]) -> str | None:
    if not matchers or any(not m.agent_types for m in matchers):
        return None
    names = sorted({name for m in matchers for name in m.agent_types})
    if all(_PLAIN_NAME.fullmatch(name) for name in names):
        return "|".join(names)
    # Agent types are exact names, so a non-plain one is escaped, not read as a regex.
    return "^(?:" + "|".join(_REGEX_META.sub(r"\\\1", name) for name in names) + ")$"


def _trigger_union(matchers: Sequence[HookMatcher]) -> str | None:
    if not matchers or any(not m.triggers for m in matchers):
        return None
    triggers = {t for m in matchers for t in m.triggers} & _TRIGGERS
    return None if triggers == _TRIGGERS or not triggers else next(iter(triggers))


def _exact_or_anchored(names: Sequence[str]) -> str:
    """``A|B|C`` when every fragment is a plain name, else the list anchored as one regex."""
    joined = "|".join(names)
    if all(_PLAIN_NAME.fullmatch(name) for name in names):
        return joined
    # Any regex character makes Claude read the whole matcher as an unanchored regex.
    return f"^(?:{joined})$"


def claude_command(event: str, *, strict: bool = False, asynchronous: bool = False) -> str:
    """The exact shell-form command of a registration (§C.2.1).

    No ``--config`` and no digest, so the bytes never change when only
    ``guard_config.json`` does; the project root comes from Claude's
    ``CLAUDE_PROJECT_DIR``, falling back to the git top level, never the cwd.
    ``asynchronous`` appends ``--async`` (the OQ-19 ``post_tool_use`` dispatch).

    Example: ``claude_command("stop").endswith("dispatch stop --harness claude_code")``.
    """
    flag = f"{STRICT_LAUNCH_FLAG} " if strict else ""
    tail = f" {ASYNC_FLAG}" if asynchronous else ""
    return f'sh "{_PROJECT_ROOT}{LAUNCHER_TOKEN}" {flag}dispatch {event} --harness {_CLAUDE}{tail}'


def to_claude_group(reg: HookRegistration) -> dict[str, Any]:
    """The managed matcher group: ``matcher`` (when any) and exactly one command handler.

    Handler keys are closed: ``type``, ``command``, ``timeout``, plus
    ``statusMessage`` on stop events, ``onFailure: block`` in strict mode only
    and ``async: true`` on OQ-19's one non-deciding ``post_tool_use``
    registration only. Never ``if``, ``args`` or a non-command type (L6).

    Example: ``to_claude_group(reg)["hooks"][0]["type"] == "command"``.
    """
    handler: dict[str, Any] = {
        "type": "command",
        "command": claude_command(reg.event, strict=reg.strict, asynchronous=reg.asynchronous),
        "timeout": reg.timeout_s,
    }
    if reg.event in STOP_EVENTS:
        handler["statusMessage"] = STOP_STATUS_MESSAGE
    if reg.strict:
        handler["onFailure"] = "block"
    if reg.asynchronous:
        handler["async"] = True
    group: dict[str, Any] = {}
    matcher = matcher_union(reg.event, reg.matchers)
    if matcher is not None:
        group["matcher"] = matcher
    group["hooks"] = [handler]
    return group


def claude_settings_projection(
    members: Sequence[RegistrationMember], *, stop_budget_s: float = DEFAULT_BUDGET_S
) -> dict[str, Any]:
    """``{"hooks": {ClaudeEvent: [group]}}`` for ``members`` alone: the debug projection.

    Example: ``claude_settings_projection([DeclaredMember.from_frontmatter(fm)])``.
    """
    limits = deadlines_ms(members, stop_budget_s=stop_budget_s)
    events: dict[str, list[dict[str, Any]]] = {}
    for reg in plan_registrations(members, _CLAUDE, deadlines=limits):
        # PostToolUse can hold two groups: the synchronous one and OQ-19's async one.
        events.setdefault(reg.claude_event, []).append(to_claude_group(reg))
    return {"hooks": events}


def render_claude_launcher() -> str:
    """The committed ``.claude/hooks/playbook/launch.sh`` bytes (§C.2.7).

    The packaged template's one placeholder becomes the ``#`` sentinel line, so
    line 1 marks the file engine-owned; there is no shebang (it runs as
    ``sh launch.sh``) and nothing machine-specific, so every clone renders it equal.

    Example: ``render_claude_launcher().splitlines()[0] == sentinel_line("hash")``.
    """
    template = shim_template(_LAUNCHER_TEMPLATE)
    return fill_placeholder(template, SENTINEL_PLACEHOLDER, sentinel_line("hash"))
