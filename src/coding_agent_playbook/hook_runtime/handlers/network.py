"""network-egress-guard: keep agent egress on the approved hosts (specs/prK-hook-pack.md §E.5).

An overlay-tier mechanism: the engine ships it inert (``tier: overlay``,
``mode: off``) and an air-gapped overlay activates it with a same-id override
(``tier: default``, ``mandatory: true``, ``mode: enforce`` and its hosts).
``pre_tool_use`` on shell calls (a speed bump: the native sandbox network
allowlist is the barrier only when managed settings enforce it) and on
WebFetch / WebSearch (a boundary).

- Hosts come from ``_net_targets`` (strings only, never resolved) and match
  by suffix against ``allowed_hosts`` plus ``gateway_hosts`` (the overlay's
  LLM gateway); loopback is always allowed.
- ``enforce``: an unapproved host and ``WebSearch`` -> deny; ``ask`` mode asks
  instead. WebFetch to an approved host asks when its query string is longer
  than ``webfetch_max_query_chars`` (data can leave in a URL).
- A destination nobody can read (a variable, ``git submodule update``, an
  install from the configured index, a command the parser could not follow)
  -> ask in both modes: a hook cannot see pip.conf or ``.gitmodules``.

No prefilter declaration: runner launchers (``uvx ruff``) hide the install
from the effective argv0, so the dispatcher's argv0 set cannot select this
guard; ``_net_targets`` dispatches on the program name itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.event import ToolClass
from coding_agent_playbook.hook_runtime.handlers._net_targets import segment_target
from coding_agent_playbook.hook_runtime.judges.hosts import host_matches, is_loopback, url_host
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.handlers._net_targets import NetTarget, Remotes
    from coding_agent_playbook.hook_runtime.registry import HandlerContext

__all__ = ["CONFIG_SCHEMA", "MODES", "network_egress_guard"]

#: Weakest first: the ``strictest`` order of ``mode`` (``[guardrails.network]`` may raise it).
MODES: Final = ("off", "ask", "enforce")
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "mode": ConfigKey("string", "strictest", MODES),
    "allowed_hosts": ConfigKey("list", "relax"),
    "gateway_hosts": ConfigKey("list", "relax"),
    "webfetch_max_query_chars": ConfigKey("integer", "relax"),
}
_DEFAULT_MAX_QUERY: Final = 256
_CONFIRM: Final = "Confirm with the user."
_BLOCKED: Final = (
    "Use the approved internal hosts (internal index or mirror); do not retry public hosts."
)
#: The outbound shapes, for a command the parser could not follow or a PowerShell one
#: (it then asks); PowerShell names are case-insensitive, hence the flag.
_RAW_NETWORK: Final = re.compile(
    r"\b(?:curl|wget|nc|ncat|ssh|scp|sftp|rsync|ftp|telnet|huggingface-cli)\b"
    r"|\b(?:Invoke-WebRequest|Invoke-RestMethod|iwr|irm|Start-BitsTransfer)\b"
    r"|\bgit\b[^\n;|&]{0,64}?\b(?:clone|fetch|pull|push|ls-remote|submodule)\b"
    r"|\b(?:pip3?|uv|uvx|pipx|poetry|pdm|conda|npm|npx)\b[^\n;|&]{0,64}?\b(?:install|add|run)\b"
    r"|\bdocker\b[^\n;|&]{0,32}?\bpull\b",
    re.IGNORECASE,
)

#: ``block`` is a deny in enforce mode and an ask otherwise; ``ask`` asks in both.
type _Strength = Literal["block", "ask"]


@dataclass(frozen=True, slots=True)
class _Verdict:
    """One judged destination: how strong, its rule id and the reason's first line."""

    strength: _Strength
    rule: str
    line: str


@dataclass(frozen=True, slots=True)
class _HostPolicy:
    """The approved host suffixes (allowed plus gateway) and the WebFetch query cap."""

    hosts: tuple[str, ...]
    max_query: int

    @classmethod
    def of(cls, config: HookConfig) -> _HostPolicy:
        allowed = config.strings("allowed_hosts", blanks="drop_blank")
        gateway = config.strings("gateway_hosts", blanks="drop_blank")
        max_query = config.integer("webfetch_max_query_chars", _DEFAULT_MAX_QUERY, minimum=0)
        return cls(tuple(dict.fromkeys((*allowed, *gateway))), max_query)

    def allows(self, host: str) -> bool:
        return is_loopback(host) or host_matches(host, self.hosts)


@register_hook_handler(
    "network_egress_guard",
    events=["pre_tool_use"],
    decisions=["deny", "ask", "none"],
    config_schema=CONFIG_SCHEMA,
    config_domain="network",
)
def network_egress_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny (enforce) or ask (ask mode) egress to an unapproved host; inert with ``mode: off``.

    Example::

        >>> network_egress_guard(bash("curl https://pypi.org"), ctx).decision  # doctest: +SKIP
        <Decision.DENY: 'deny'>
    """
    config = HookConfig(ctx.config, CONFIG_SCHEMA)
    mode = config.choice("mode", "off")
    tool = ev.tool
    if mode not in MODES[1:] or tool is None:
        return None
    policy = _HostPolicy.of(config)
    if tool.tool_class is ToolClass.WEB:
        verdict = _web(tool, policy)
    elif tool.tool_class is ToolClass.SHELL:
        verdict = _shell(tool, policy, _remote_lookup(ctx))
    else:
        return None
    return None if verdict is None else _result(verdict, mode == "enforce", ctx)


def _web(tool: ToolCall, policy: _HostPolicy) -> _Verdict | None:
    if tool.name == "WebSearch":
        line = "WebSearch reaches public search engines, which this repository's policy bars."
        return _Verdict("block", "websearch", line)
    url = tool.raw_input.get("url")
    host = url_host(url) if isinstance(url, str) else None
    if host is None:
        return _Verdict(
            "block", "webfetch_url", "This WebFetch URL names no host this guard can read."
        )
    if not policy.allows(host):
        line = f"WebFetch of {quote_data(host)}, which is not an approved host for this repository."
        return _Verdict("block", "webfetch_host", line)
    from urllib.parse import urlsplit  # branch-local (§D.1): WebFetch only

    query = urlsplit(str(url)).query
    if len(query) <= policy.max_query:
        return None
    line = (
        f"This WebFetch URL carries a {len(query)}-character query string (limit "
        f"{policy.max_query}): it may send repository data off the machine."
    )
    return _Verdict("ask", "webfetch_query", line)


def _shell(tool: ToolCall, policy: _HostPolicy, remotes: Callable[[], Remotes]) -> _Verdict | None:
    command = tool.command
    if command is None:
        return None
    if command.parse_error is not None or command.kind == "powershell":
        if _RAW_NETWORK.search(command.text) is None:
            return None
        return _Verdict(
            "ask", "unparsed", "This command could not be read and may reach the network."
        )
    found = [
        verdict
        for segment in command.segments
        if (target := segment_target(segment, remotes)) is not None
        and (verdict := _judge(target, policy)) is not None
    ]
    return next((v for v in found if v.strength == "block"), None) or next(iter(found), None)


def _judge(target: NetTarget, policy: _HostPolicy) -> _Verdict | None:
    off = [host for host in target.hosts if not policy.allows(host)]
    shown = f"`{target.command}`"
    if off:
        line = f"{shown} would contact {quote_data(off[0])}, which is not an approved host."
        return _Verdict("block", "host", line)
    if not target.unknown:
        return None
    if target.kind == "install":
        line = f"{shown} fetches from the configured package index, which this guard cannot see."
        return _Verdict("ask", "install_index", line)
    return _Verdict("ask", "unknown_host", f"{shown} contacts a host this guard cannot read.")


def _result(verdict: _Verdict, enforce: bool, ctx: HandlerContext) -> HandlerResult:
    deny = enforce and verdict.strength == "block"
    advice = _BLOCKED if deny else _CONFIRM
    return HandlerResult(
        decision=Decision.DENY if deny else Decision.ASK,
        hook_id=ctx.hook.id,
        rule_id=verdict.rule,
        reason=f"{'Blocked: ' if deny else ''}{verdict.line}\n{advice}",
    )


def _remote_lookup(ctx: HandlerContext) -> Callable[[], Remotes]:
    """``git remote -v`` as name -> URLs, run on the first call only (a git remote name)."""
    cache: list[Remotes] = []

    def load() -> Remotes:
        if not cache:
            remotes: dict[str, tuple[str, ...]] = {}
            for name, url in ctx.git.remote_urls():
                remotes[name] = (*remotes.get(name, ()), url)
            cache.append(remotes)
        return cache[0]

    return load
