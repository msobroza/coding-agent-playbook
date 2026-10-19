"""The ``allowlists`` and ``network`` tables of ``guard_config.json`` (prK §D.8.2, §E.4, §E.5).

One rendered view of the allowlist data the §E.4 safety guards read from their
merged configs (engine ``HOOK.md``, overlays, ``[guardrails]`` and
``[hooks.<hook-id>]``), so a reader of the file (a reviewer, ``playbook ci``)
sees one source:

- ``dependencies``: dependency-allowlist-guard's ``allowlist``, PEP 503-normalized
  and sorted (empty: tier (b) asks instead of denying);
- ``required_index``: its internal index (``""``: none required);
- ``egress_hosts``: exfil-channel-guard's ``allowed_hosts``, lower-cased and sorted.

``network`` is ``{"mode": ...}``: network-egress-guard's mode once an overlay
activated it (``ask`` / ``enforce``), else ``""``. The session briefing states
it (§E.1 item 8), so the model does not burn turns retrying blocked hosts.

A guard that is off contributes nothing. Machine-independent, like every
``guard_config`` table (§D.8.3). Stdlib-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.detector.pep503 import canonical_name

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

__all__ = ["DEPENDENCY_HOOK", "EGRESS_HOOK", "NETWORK_HOOK", "allowlists_table", "network_table"]

DEPENDENCY_HOOK: Final = "dependency-allowlist-guard"
EGRESS_HOOK: Final = "exfil-channel-guard"
NETWORK_HOOK: Final = "network-egress-guard"
_NETWORK_MODES: Final = ("ask", "enforce")


def allowlists_table(hooks: Sequence[ResolvedHook]) -> dict[str, Any]:
    """``{dependencies, required_index, egress_hosts}`` from the on hooks' merged configs.

    Example::

        >>> allowlists_table([])
        {'dependencies': [], 'required_index': '', 'egress_hosts': []}
    """
    deps = _config(hooks, DEPENDENCY_HOOK)
    egress = _config(hooks, EGRESS_HOOK)
    required = deps.get("required_index")
    return {
        "dependencies": sorted({canonical_name(n) for n in _strings(deps.get("allowlist"))}),
        "required_index": required if isinstance(required, str) else "",
        "egress_hosts": sorted({h.lower() for h in _strings(egress.get("allowed_hosts"))}),
    }


def network_table(hooks: Sequence[ResolvedHook]) -> dict[str, str]:
    """``{"mode": "ask" | "enforce"}`` while network-egress-guard is active, else ``{"mode": ""}``.

    Example::

        >>> network_table([])
        {'mode': ''}
    """
    mode = _config(hooks, NETWORK_HOOK).get("mode")
    return {"mode": mode if mode in _NETWORK_MODES else ""}


def _config(hooks: Sequence[ResolvedHook], hook_id: str) -> dict[str, Any]:
    hook = next((h for h in hooks if h.id == hook_id), None)
    handler = None if hook is None else hook.handlers.get("pre_tool_use")
    return dict(handler.config) if handler is not None else {}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
