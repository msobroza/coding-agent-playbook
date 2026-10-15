"""Sync-time hook policy (specs/prK-lifecycle-hooks.md §A.6, §A.7, §A.11, §B.5).

``coding_agent_playbook.hook_policy`` is the spec's ``hook_policy.py``. It is a
package so each concern stays under the file-size budget; import from here,
not from the submodules. Today it carries the one home of the event, tool-class
and adapter-support tables (:mod:`.tables`), the additive layer merge
(:mod:`.merge`, with the H14 override rules in :mod:`.override_rules`), and the
effective view (:mod:`.effective`) with its ``guard_config.json`` hook records
(:mod:`.resolved`).

Stdlib-only and sync-time only: ``hook_runtime`` never imports it, it reads the
compiled ``guard_config.json`` instead (§D.8).
"""

from __future__ import annotations

from coding_agent_playbook.hook_policy.effective import resolve_effective_hooks
from coding_agent_playbook.hook_policy.merge import (
    NO_HANDLER_SCHEMAS,
    ConfigKeySpec,
    ConfigSchemaLookup,
    HookLayerMerger,
    HookViolation,
    KeyPolicy,
    merge_config,
    merge_hook_layers,
    split_hook_layers,
)
from coding_agent_playbook.hook_policy.resolved import (
    EffectiveHooks,
    HandlerKind,
    ResolvedHandler,
    ResolvedHook,
    SkippedHook,
)
from coding_agent_playbook.hook_policy.tables import (
    ADVISORY_RULE_PREFIX,
    ADVISORY_RULE_PRIORITY,
    DEGRADED_EVENTS,
    HOOK_CAPABLE_ADAPTERS,
    HOOK_EVENTS,
    HOOK_SCRIPTS_DIR,
    HOOK_SUPPORT,
    ON_ERROR_STRENGTH,
    TOOL_CLASS_NAMES,
    EventSpec,
)

__all__ = [
    "ADVISORY_RULE_PREFIX",
    "ADVISORY_RULE_PRIORITY",
    "DEGRADED_EVENTS",
    "HOOK_CAPABLE_ADAPTERS",
    "HOOK_EVENTS",
    "HOOK_SCRIPTS_DIR",
    "HOOK_SUPPORT",
    "NO_HANDLER_SCHEMAS",
    "ON_ERROR_STRENGTH",
    "TOOL_CLASS_NAMES",
    "ConfigKeySpec",
    "ConfigSchemaLookup",
    "EffectiveHooks",
    "EventSpec",
    "HandlerKind",
    "HookLayerMerger",
    "HookViolation",
    "KeyPolicy",
    "ResolvedHandler",
    "ResolvedHook",
    "SkippedHook",
    "merge_config",
    "merge_hook_layers",
    "resolve_effective_hooks",
    "split_hook_layers",
]
