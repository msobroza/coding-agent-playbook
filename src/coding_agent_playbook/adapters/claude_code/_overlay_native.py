"""The native twins of the §E.5 overlay guards in ``.claude/settings.json`` (specs/prK-hook-pack.md §E.5).

While an overlay has activated network-egress-guard or
sensitive-data-read-guard (on, and ``mode`` not ``off``), Claude Code also gets
the rows it enforces itself, which hold when the hook interpreter is missing:

- network-egress-guard: ``sandbox.network.allowedDomains`` from
  ``allowed_hosts + gateway_hosts`` (pre-allows hosts for *sandboxed* Bash; a
  barrier only when managed settings enforce the sandbox and
  ``strictAllowlist``), and in ``enforce`` mode ``permissions.deny``
  ``WebSearch``;
- sensitive-data-read-guard: ``sandbox.filesystem.denyRead`` from
  ``deny_globs`` (binds sandboxed Bash only), and in ``enforce`` mode one
  ``permissions.deny`` ``Read(<glob>)`` row per deny glob.

Deny rows only in ``enforce``: a native deny preempts the hook, so in ``ask``
mode it would turn the guard's ask into a deny. No ``!`` exemption row is
rendered for ``allow_globs``: in one ``permissions.deny`` list a negation could
re-allow a secrets-path-guard row, so the native rows are the coarser backstop
(the hook still exempts the allow globs). Globs use secrets-path-guard's
anchoring (``**/<glob>``, ``./<glob>``). The rows go through K3's
managed-array merge: one lock entry per string, user entries untouched, ours
removed when the guard is off.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.adapters.claude_code._secret_native import (
    DENY_POINTER,
    DENY_READ_POINTER,
    gitignore_patterns,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

__all__ = [
    "ALLOWED_DOMAINS_POINTER",
    "NETWORK_EGRESS_GUARD",
    "SENSITIVE_DATA_READ_GUARD",
    "network_native_rows",
    "sensitive_read_native_rows",
]

NETWORK_EGRESS_GUARD: Final = "network-egress-guard"
SENSITIVE_DATA_READ_GUARD: Final = "sensitive-data-read-guard"
ALLOWED_DOMAINS_POINTER: Final = "/sandbox/network/allowedDomains"
_ACTIVE_MODES: Final = ("ask", "enforce")
_ENFORCE: Final = "enforce"
_ANY_BELOW: Final = "/**"


def network_native_rows(hooks: Iterable[ResolvedHook]) -> dict[str, tuple[str, ...]]:
    """The managed strings per pointer while network-egress-guard is active, else ``{}``.

    Example::

        >>> network_native_rows([])
        {}
    """
    config = _active_config(hooks, NETWORK_EGRESS_GUARD)
    if config is None:
        return {}
    hosts = [*_strings(config.get("allowed_hosts")), *_strings(config.get("gateway_hosts"))]
    rows: dict[str, tuple[str, ...]] = {}
    domains = _unique(host.strip().lower() for host in hosts)
    if domains:
        rows[ALLOWED_DOMAINS_POINTER] = domains
    if config.get("mode") == _ENFORCE:
        rows[DENY_POINTER] = ("WebSearch",)
    return rows


def sensitive_read_native_rows(hooks: Iterable[ResolvedHook]) -> dict[str, tuple[str, ...]]:
    """The managed strings per pointer while sensitive-data-read-guard is active, else ``{}``.

    Example::

        >>> sensitive_read_native_rows([])
        {}
    """
    config = _active_config(hooks, SENSITIVE_DATA_READ_GUARD)
    if config is None:
        return {}
    patterns = gitignore_patterns(_strings(config.get("deny_globs")), (), {})
    if not patterns:
        return {}
    rows = {DENY_READ_POINTER: _unique(_sandbox_path(pattern) for pattern in patterns)}
    if config.get("mode") == _ENFORCE:
        rows[DENY_POINTER] = tuple(f"Read({pattern})" for pattern in patterns)
    return rows


def _active_config(hooks: Iterable[ResolvedHook], hook_id: str) -> Mapping[str, Any] | None:
    """``hook_id``'s merged ``pre_tool_use`` config when it is on and not ``mode: off``."""
    hook = next((h for h in hooks if h.id == hook_id), None)
    handler = None if hook is None else hook.handlers.get("pre_tool_use")
    if handler is None or handler.config.get("mode") not in _ACTIVE_MODES:
        return None
    return handler.config


def _sandbox_path(pattern: str) -> str:
    """A gitignore-anchored glob as a sandbox path: a directory stands for its contents."""
    return pattern[: -len(_ANY_BELOW)] if pattern.endswith(_ANY_BELOW) else pattern


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))
