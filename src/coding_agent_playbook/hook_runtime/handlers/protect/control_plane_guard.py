"""control-plane-guard: stop the agent disabling or rewriting its own guardrails (specs/prK-hook-pack.md §E.1).

Each write target is routed to its control-plane row (``_shared.control_plane_paths``):

- rows decided by the path alone: the hook state dir and the trust store
  (any write denies), ``extra_paths`` (deny), the hook sources
  (``playbook/hooks/**``, an overlay checkout's ``src/*/resources/hooks/**``,
  the engine checkout's ``catalog/core/hooks/**`` and
  ``catalog/plugins/*/hooks/**``) and plugin carriers (any creation or edit asks);
- new files under the hook-artifact dirs that no lock row vouches for deny
  (an agent-created ``fnmatch.py`` would shadow the stdlib inside the guard);
  existing generated files are guard-generated-outputs';
- content rows (settings, config, MCP, OpenCode, pre-commit, ``hooks:``
  frontmatter): a file-tool edit is simulated in memory
  (``edit_preview``), both versions are parsed and diffed, and the row's
  verdict applies. An edit that cannot be simulated (``apply_patch``, an
  ``old_string`` that does not match) or a file that does not parse asks.

A Bash write onto a control-plane file cannot be simulated: rows that can
deny deny (a speed bump), ask-only rows ask. The Bash command rows (pty- or
pipe-fed ``playbook sync``, ``claude mcp add``) are in ``_control_plane_shell``.

The reason is always the one line :data:`REASON`: it never tells the agent
how to change the configuration. Nothing here spawns a process; the JSON,
TOML and text verdict modules (``tomllib`` with the TOML one) are imported
only on their branch, so an Edit of a ``.py`` file or a plain Bash command
loads none of them.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.config.reader import read_small_file
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.handlers._shared.control_plane_paths import (
    load_plane,
    route_of,
)
from coding_agent_playbook.hook_runtime.handlers._shared.edit_preview import preview_after
from coding_agent_playbook.hook_runtime.handlers._shared.targets import (
    file_write_paths,
    shell_target,
)
from coding_agent_playbook.hook_runtime.handlers.protect._control_plane_shell import (
    command_verdict,
    names_state_dir,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.handlers._shared.control_plane_paths import (
        ControlPlane,
        RouteKind,
    )
    from coding_agent_playbook.hook_runtime.shell.parse import ShellCommand

__all__ = ["CONFIG_SCHEMA", "REASON", "control_plane_guard"]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {"extra_paths": ConfigKey("list", "extend")}
#: The one reason every verdict gives: it names no file and no way around it.
REASON: Final = "Guardrail configuration is user-owned; ask the user to change it."

type Verdict = tuple[Decision, str]
type PlaneFn = Callable[[], ControlPlane]

_PASS: Final[Verdict] = (Decision.NONE, "")
#: Rows decided by the path alone, whatever the tool.
_BY_PATH: Final[Mapping[str, Decision]] = {
    "state": Decision.DENY,
    "trust_store": Decision.DENY,
    "extra": Decision.DENY,
    "hook_source": Decision.ASK,
    "plugin_carrier": Decision.ASK,
}
#: A Bash write cannot be simulated: the strongest verdict of its row.
_BY_SHELL: Final[Mapping[str, Decision]] = {
    **_BY_PATH,
    "settings": Decision.DENY,
    "config": Decision.DENY,
    "local_config": Decision.DENY,
    "precommit": Decision.DENY,
    "mcp": Decision.ASK,
    "opencode_config": Decision.ASK,
    "frontmatter_carrier": Decision.ASK,
}
#: Control-plane files are small; a larger one is not simulated (it asks).
_READ_LIMIT: Final = 4 * 1024 * 1024


@register_hook_handler(
    "control_plane_guard",
    events=["pre_tool_use"],
    decisions=["deny", "ask", "none"],
    config_schema=CONFIG_SCHEMA,
)
def control_plane_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny or ask on an edit of user-owned guardrail configuration; ``None`` (pass) otherwise.

    Example::

        >>> control_plane_guard(write_disable_all_hooks, ctx).reason  # doctest: +SKIP
        'Guardrail configuration is user-owned; ask the user to change it.'
    """
    tool = ev.tool
    if tool is None or ev.repo is None:
        return None
    plane = functools.cache(lambda: _load(ev, ctx))
    verdicts = [_file_verdict(path, tool, plane()) for path in file_write_paths(tool)]
    if tool.command is not None:
        verdicts.extend(_shell_verdicts(tool.command, ev, ctx, plane))
    decision, rule = max(verdicts, key=lambda verdict: verdict[0].rank, default=_PASS)
    if decision is Decision.NONE:
        return None
    return HandlerResult(decision=decision, hook_id=ctx.hook.id, rule_id=rule, reason=REASON)


def _load(ev: CanonicalEvent, ctx: HandlerContext) -> ControlPlane:
    assert ev.repo is not None  # checked by the handler before any target is routed
    extra = HookConfig(ctx.config, CONFIG_SCHEMA).strings("extra_paths", blanks="keep", strict=True)
    return load_plane(
        ctx.cfg,
        ev.repo,
        env=ctx.env,
        home=ctx.home,
        platform=ctx.platform,
        project_dir=ev.project_dir,
        extra=extra,
    )


def _file_verdict(npath: NormalizedPath, tool: ToolCall, plane: ControlPlane) -> Verdict:
    """The verdict on one file-tool write path: by path, new artifact, or simulated diff."""
    kind = route_of(plane, npath)
    if kind is None:
        return _PASS
    if kind in _BY_PATH:
        return _BY_PATH[kind], kind
    if kind == "hook_artifact":
        return _new_artifact(plane, npath), kind
    readable, before = _read(npath)
    after = preview_after(tool, before) if readable else None
    if after is None:
        return Decision.ASK, kind  # cannot simulate: never a silent pass
    return _content_verdict(kind, before, after, npath, plane), kind


def _shell_verdicts(
    command: ShellCommand, ev: CanonicalEvent, ctx: HandlerContext, plane: PlaneFn
) -> list[Verdict]:
    """The command rows of each segment, then its write targets routed like file paths."""
    from coding_agent_playbook.hook_runtime.shell.parse import write_targets  # Bash branch only

    found: list[Verdict] = []
    pipes_in: dict[int, bool] = {}  # depth -> the previous segment there pipes into the next
    for segment in command.segments:
        row = command_verdict(segment, piped=pipes_in.get(segment.depth, False))
        if row is not None:
            found.append(row)
        pipes_in[segment.depth] = segment.pipes_to_next
        for raw in write_targets(segment):
            if names_state_dir(raw):
                found.append((Decision.DENY, "state"))
                continue
            found.append(_shell_target_verdict(shell_target(raw, segment, ev, ctx), plane()))
    return found


def _shell_target_verdict(npath: NormalizedPath, plane: ControlPlane) -> Verdict:
    kind = route_of(plane, npath)
    if kind is None:
        return _PASS
    if kind == "hook_artifact":
        return _new_artifact(plane, npath), kind
    return _BY_SHELL[kind], kind


def _new_artifact(plane: ControlPlane, npath: NormalizedPath) -> Decision:
    """A file under the hook-artifact dirs that does not exist and no lock row vouches for."""
    known = npath.exists or npath.key in plane.protected.rows
    return Decision.NONE if known else Decision.DENY


def _content_verdict(
    kind: RouteKind, before: str | None, after: str, npath: NormalizedPath, plane: ControlPlane
) -> Decision:
    """The row's own diff of ``before`` (``None``: absent) and ``after``."""
    if kind in ("config", "local_config"):
        from coding_agent_playbook.hook_runtime.handlers.protect._control_plane_toml import (
            toml_verdict,
        )

        return toml_verdict(before, after, local=kind == "local_config", keys=plane.policy_keys)
    if kind == "precommit":
        from coding_agent_playbook.hook_runtime.handlers.protect._control_plane_text import (
            precommit_verdict,
        )

        return precommit_verdict(before, after, plane.precommit_ids)
    if kind == "frontmatter_carrier":
        from coding_agent_playbook.hook_runtime.handlers.protect._control_plane_text import (
            frontmatter_hooks_verdict,
        )

        return frontmatter_hooks_verdict(before, after)
    return _json_verdict(kind, before, after, npath, plane)


def _json_verdict(
    kind: RouteKind, before: str | None, after: str, npath: NormalizedPath, plane: ControlPlane
) -> Decision:
    from coding_agent_playbook.hook_runtime.handlers.protect import _control_plane_json as cpj

    jsonc = kind == "opencode_config"
    old = {} if before is None else cpj.load_json_object(before, jsonc=jsonc)
    new = cpj.load_json_object(after, jsonc=jsonc)
    if old is None or new is None:
        return Decision.ASK  # a file that does not parse (before or after the edit)
    if kind == "settings":
        managed = [(row.scope, row.sha256) for row in plane.protected.scoped(npath.key)]
        return cpj.settings_verdict(old, new, managed)
    if kind == "mcp":
        return cpj.mcp_verdict(old, new)
    return cpj.opencode_verdict(old, new)


def _read(npath: NormalizedPath) -> tuple[bool, str | None]:
    """``(readable, text)``: ``text`` is ``None`` for a path that does not exist yet."""
    if not npath.exists:
        return True, None
    try:
        data, _ = read_small_file(Path(npath.realpath), _READ_LIMIT)
        return True, data.decode("utf-8")
    except (OSError, ValueError):  # unreadable, not a regular file, too large, not UTF-8
        return False, None
