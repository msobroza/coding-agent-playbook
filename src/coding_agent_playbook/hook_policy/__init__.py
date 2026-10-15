"""Sync-time hook policy (specs/prK-lifecycle-hooks.md §A.6, §A.7, §A.11, §B.5).

``coding_agent_playbook.hook_policy`` is the spec's ``hook_policy.py``. It is a
package so each concern stays under the file-size budget; import from here,
not from the submodules. Today it carries the one home of the event, tool-class
and adapter-support tables (:mod:`.tables`), the additive layer merge
(:mod:`.merge`, with the H14 override rules in :mod:`.override_rules`), the
effective view (:mod:`.effective`, a linked rule's ``lint_codes`` resolved by
:mod:`.lint_codes`) with its ``guard_config.json`` hook records
(:mod:`.resolved`), their advisory projection (:mod:`.advisory`) and their
per-adapter labels (:mod:`.labels`), and the
trust contract ``playbook validate`` enforces: per hook (:mod:`.contract`),
across hooks and config (:mod:`.contract_set`), and against the handler
registry (:mod:`.handler_catalog`, H6/H21's registry half).

Sync-time only, stdlib plus the import-light ``hook_runtime`` tables and
registry it shares with the dispatcher: ``hook_runtime`` never imports it, it
reads the compiled ``guard_config.json`` instead (§D.8).
"""

from __future__ import annotations

from coding_agent_playbook.hook_policy._findings import HookIssue, Severity
from coding_agent_playbook.hook_policy.advisory import (
    ADAPTER_LABELS,
    advisory_block,
    advisory_text,
    enforcement_line,
    enforcement_targets,
)
from coding_agent_playbook.hook_policy.contract import HookCheckContext, classify_hook
from coding_agent_playbook.hook_policy.contract_set import HookSetInputs, classify_hook_set
from coding_agent_playbook.hook_policy.effective import (
    effective_applies_if,
    merged_handler_config,
    resolve_effective_hooks,
)
from coding_agent_playbook.hook_policy.handler_catalog import (
    CatalogEntry,
    HandlerCatalog,
    RegistryCatalog,
    config_findings,
    registry_findings,
)
from coding_agent_playbook.hook_policy.labels import HOOK_LABELS, HookLabel, adapter_label
from coding_agent_playbook.hook_policy.lint_codes import (
    LINT_CODES_KEY,
    linked_lint_config,
    resolve_lint_codes,
)
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
    APPLICABILITY_GATES,
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
    ENGINE_DEADLINE_CAP_MS,
    HOOK_CAPABLE_ADAPTERS,
    HOOK_EVENTS,
    HOOK_SCRIPTS_DIR,
    HOOK_SUPPORT,
    MATCHER_VALUES,
    ON_ERROR_STRENGTH,
    TOOL_CLASS_NAMES,
    EventSpec,
)

__all__ = [
    "ADAPTER_LABELS",
    "ADVISORY_RULE_PREFIX",
    "ADVISORY_RULE_PRIORITY",
    "APPLICABILITY_GATES",
    "DEGRADED_EVENTS",
    "ENGINE_DEADLINE_CAP_MS",
    "HOOK_CAPABLE_ADAPTERS",
    "HOOK_EVENTS",
    "HOOK_LABELS",
    "HOOK_SCRIPTS_DIR",
    "HOOK_SUPPORT",
    "LINT_CODES_KEY",
    "MATCHER_VALUES",
    "NO_HANDLER_SCHEMAS",
    "ON_ERROR_STRENGTH",
    "TOOL_CLASS_NAMES",
    "CatalogEntry",
    "ConfigKeySpec",
    "ConfigSchemaLookup",
    "EffectiveHooks",
    "EventSpec",
    "HandlerCatalog",
    "HandlerKind",
    "HookCheckContext",
    "HookIssue",
    "HookLabel",
    "HookLayerMerger",
    "HookSetInputs",
    "HookViolation",
    "KeyPolicy",
    "RegistryCatalog",
    "ResolvedHandler",
    "ResolvedHook",
    "Severity",
    "SkippedHook",
    "adapter_label",
    "advisory_block",
    "advisory_text",
    "classify_hook",
    "classify_hook_set",
    "config_findings",
    "effective_applies_if",
    "enforcement_line",
    "enforcement_targets",
    "linked_lint_config",
    "merge_config",
    "merge_hook_layers",
    "merged_handler_config",
    "registry_findings",
    "resolve_effective_hooks",
    "resolve_lint_codes",
    "split_hook_layers",
]
