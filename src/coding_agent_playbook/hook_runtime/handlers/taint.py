"""taint-escalation: risky actions ask once the session has read untrusted content (specs/prK-hook-pack.md §E.4).

Opt-in. Content-free: nothing is scanned for injected instructions (a rejected
entry); the session is marked by where content came from, a per-session flag
in ``<state>`` (``SessionState.flags``):

- ``taint_escalation:marker`` (``post_tool_use``): WebFetch / WebSearch, and an
  ``mcp__*`` tool whose name matches ``config.mcp_taint_pattern``;
- ``taint_escalation`` (``pre_tool_use``) marks a Read / Grep / Glob outside the
  repository itself: the pre-tool dispatcher already sees every read (for
  secrets-path-guard), so the post-tool registration never widens to ``Read``.
  The harness's own config dirs (``~/.claude``, ``$CLAUDE_CONFIG_DIR``,
  ``~/.config/opencode``) are the user's, not untrusted content.

Once marked, normally allowed actions ask, naming the source: outbound network
(exfil rows and any client to a non-loopback host, ``allowed_hosts`` or not),
``git push``, package installs, control-plane edits (control-plane-guard's
table) and reads of ``$HOME`` dotfiles outside the repository. The flag clears
only with a new session, or ``taint_escalation:session_start`` with source
``clear``; a compaction keeps it (the summary may carry the content).
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.event import ToolClass
from coding_agent_playbook.hook_runtime.judges.hosts import is_loopback
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.security.files import user_home

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

__all__ = [
    "CONFIG_SCHEMA",
    "DEFAULT_MCP_TAINT_PATTERN",
    "TAINT_SOURCES",
    "taint_clear",
    "taint_escalation",
    "taint_marker",
]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {"mcp_taint_pattern": ConfigKey("string")}
DEFAULT_MCP_TAINT_PATTERN: Final = "fetch|browse|http|url|web|search|scrape"
#: Session flag -> the source category the reason names, in reason order.
TAINT_SOURCES: Final[Mapping[str, str]] = {
    "taint:web": "web content",
    "taint:mcp": "an MCP tool's output",
    "taint:read": "a read outside the repo",
}
_READS: Final = frozenset({ToolClass.READ, ToolClass.SEARCH})
_WRITES: Final = frozenset({ToolClass.EDIT, ToolClass.WRITE, ToolClass.NOTEBOOK_EDIT})
_HARNESS_DIRS: Final = (".claude", ".config/opencode")


@register_hook_handler("taint_escalation", events=["pre_tool_use"], decisions=["ask", "none"])
def taint_escalation(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Ask before a risky action in a tainted session; mark one on a read outside the repo.

    Example::

        >>> taint_escalation(bash("git push origin feat"), tainted_ctx).reason  # doctest: +SKIP
        'This session has read untrusted content (web content); confirm before pushing commits.'
    """
    tool = ev.tool
    if tool is None or ev.repo is None:
        return None
    flags = ctx.session.flags()
    sources = [label for flag, label in TAINT_SOURCES.items() if flag in flags]
    action = _risky_action(tool, ev, ctx) if sources else None
    if tool.tool_classes & _READS and any(_untrusted_read(p, ctx) for p in tool.paths):
        ctx.session.set_flag("taint:read")
    if action is None:
        return None
    rule, what = action
    reason = (
        f"This session has read untrusted content ({', '.join(sources)}); confirm before {what}."
    )
    return HandlerResult(decision=Decision.ASK, hook_id=ctx.hook.id, rule_id=rule, reason=reason)


@register_hook_handler(
    "taint_escalation:marker",
    events=["post_tool_use"],
    decisions=["ask", "none"],  # the hook's set (H5); the marker returns None
    config_schema=CONFIG_SCHEMA,
)
def taint_marker(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Mark the session after WebFetch / WebSearch or a fetching MCP tool; always ``None``.

    Example::

        >>> taint_marker(webfetch_done, ctx) is None  # doctest: +SKIP
        True
    """
    tool = ev.tool
    if tool is None:
        return None
    if ToolClass.WEB in tool.tool_classes:
        ctx.session.set_flag("taint:web")
    elif ToolClass.MCP in tool.tool_classes and _mcp_pattern(ctx.config).search(tool.name):
        ctx.session.set_flag("taint:mcp")
    return None


@register_hook_handler(
    "taint_escalation:session_start",
    events=["session_start"],
    decisions=["ask", "none"],  # the hook's set (H5); the clear returns None
)
def taint_clear(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Clear the taint on ``session_start`` with source ``clear`` (never on a compaction).

    Example::

        >>> taint_clear(start(source="clear"), ctx) is None  # doctest: +SKIP
        True
    """
    if ev.source == "clear":
        for flag in TAINT_SOURCES:
            ctx.session.clear_flag(flag)
    return None


def _risky_action(
    tool: ToolCall, ev: CanonicalEvent, ctx: HandlerContext
) -> tuple[str, str] | None:
    """``(rule, what)`` of the first risky action this call takes, else ``None``."""
    if tool.tool_class is ToolClass.SHELL:
        command = tool.command
        if command is None:
            return None
        if command.parse_error is not None or command.kind == "powershell":
            return "unparsed", "running a command the guard could not read"
        found = (_segment_action(segment) for segment in command.segments)
        return next((a for a in found if a is not None), None) or _control_plane(
            ev, ctx, shell=True
        )
    if tool.tool_classes & _WRITES:
        return _control_plane(ev, ctx, shell=False)
    dotfile = next((p for p in tool.paths if _home_dotfile(p, ctx)), None)
    return (
        None if dotfile is None else ("secret_adjacent_read", f"reading {quote_data(dotfile.path)}")
    )


def _segment_action(segment: Segment) -> tuple[str, str] | None:
    from coding_agent_playbook.hook_runtime.handlers._egress import network_hosts, segment_egress
    from coding_agent_playbook.hook_runtime.judges.install_commands import install_requests
    from coding_agent_playbook.hook_runtime.shell.git_command import parse_git

    git = parse_git(segment)
    if git is not None and git.subcommand == "push":
        return "push", "pushing commits"
    if install_requests(segment):
        return "install", "installing packages"
    if segment_egress(segment, dict) is not None:
        return "egress", "sending data off the machine"
    host = next((h for h in network_hosts(segment) if h and not is_loopback(h)), None)
    return None if host is None else ("network", f"contacting {quote_data(host)}")


def _control_plane(
    ev: CanonicalEvent, ctx: HandlerContext, *, shell: bool
) -> tuple[str, str] | None:
    """An edit of the guard configuration control-plane-guard owns (settings, hooks, MCP, ...)."""
    from coding_agent_playbook.hook_runtime.handlers._control_plane_paths import (
        load_plane,
        route_of,
    )

    paths = _shell_writes(ev, ctx) if shell else list(ev.tool.write_paths if ev.tool else ())
    if not paths or ev.repo is None:
        return None
    plane = load_plane(
        ctx.cfg,
        ev.repo,
        env=ctx.env,
        home=ctx.home,
        platform=ctx.platform,
        project_dir=ev.project_dir,
    )
    route = next((r for p in paths if (r := route_of(plane, p)) is not None), None)
    return None if route is None else ("control_plane", f"editing guard configuration ({route})")


def _shell_writes(ev: CanonicalEvent, ctx: HandlerContext) -> list[NormalizedPath]:
    from coding_agent_playbook.hook_runtime.handlers._targets import shell_write_targets
    from coding_agent_playbook.hook_runtime.shell.parse import write_targets

    return shell_write_targets(ev, ctx, write_targets)


def _untrusted_read(path: NormalizedPath, ctx: HandlerContext) -> bool:
    """A read outside every worktree of the repo, the harness's own config dirs excepted."""
    return path.outside_repo and not _under(path.realpath, _harness_dirs(ctx))


def _home_dotfile(path: NormalizedPath, ctx: HandlerContext) -> bool:
    """A ``$HOME`` dotfile or dot-directory outside the repo (a credential's usual home)."""
    home = os.path.realpath(ctx.home or user_home())
    if not path.outside_repo or not path.realpath.startswith(home + os.sep):
        return False
    first = path.realpath[len(home) + 1 :].split(os.sep, 1)[0]
    return first.startswith(".") and not _under(path.realpath, _harness_dirs(ctx))


def _harness_dirs(ctx: HandlerContext) -> list[str]:
    home = ctx.home or user_home()
    dirs = [os.path.join(home, rel) for rel in _HARNESS_DIRS]
    configured = ctx.env.get("CLAUDE_CONFIG_DIR")
    return [os.path.realpath(d) for d in (*dirs, *([configured] if configured else []))]


def _under(path: str, roots: Iterable[str]) -> bool:
    return any(path == root or path.startswith(root + os.sep) for root in roots)


def _mcp_pattern(config: Mapping[str, object]) -> re.Pattern[str]:
    source = config.get("mcp_taint_pattern")
    try:
        return re.compile(
            source if isinstance(source, str) and source else DEFAULT_MCP_TAINT_PATTERN, re.I
        )
    except re.error:
        return re.compile(DEFAULT_MCP_TAINT_PATTERN, re.I)
