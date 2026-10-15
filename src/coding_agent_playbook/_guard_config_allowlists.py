"""The ``allowlists`` table of ``guard_config.json`` (specs/prK-lifecycle-hooks.md §D.8.2, prK-hook-pack §E.4).

One rendered view of the allowlist data the §E.4 safety guards read from their
merged configs (engine ``HOOK.md``, overlays, ``[guardrails]`` and
``[hooks.<hook-id>]``), so a reader of the file (a reviewer, ``playbook ci``,
network-egress-guard later) sees one source:

- ``dependencies``: dependency-allowlist-guard's ``allowlist``, PEP 503-normalized
  and sorted (empty: tier (b) asks instead of denying);
- ``required_index``: its internal index (``""``: none required);
- ``egress_hosts``: exfil-channel-guard's ``allowed_hosts``, lower-cased and sorted.

A guard that is off contributes nothing. Machine-independent, like every
``guard_config`` table (§D.8.3). Stdlib-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook._pep503 import canonical_name

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_policy import ResolvedHook

__all__ = ["DEPENDENCY_HOOK", "EGRESS_HOOK", "allowlists_table"]

DEPENDENCY_HOOK: Final = "dependency-allowlist-guard"
EGRESS_HOOK: Final = "exfil-channel-guard"


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


def _config(hooks: Sequence[ResolvedHook], hook_id: str) -> dict[str, Any]:
    hook = next((h for h in hooks if h.id == hook_id), None)
    handler = None if hook is None else hook.handlers.get("pre_tool_use")
    return dict(handler.config) if handler is not None else {}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
