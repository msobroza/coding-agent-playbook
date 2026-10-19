"""The Hooks block of ``playbook check`` (specs/prK-lifecycle-hooks.md §A.8, §C.1.1).

:func:`format_hooks_section` prints the ``=== Hooks ===`` block. Every on hook
is labelled per enabled adapter (``enforced`` / ``degraded`` / ``advisory`` /
``—``, from the adapter class's ``hook_support``), so advice is never mistaken
for enforcement (QC-10); every off hook gets its reason. The scoped drift lines
moved to ``lockfile.drift.drift_entries`` (shared with the ``drift`` Stop stage).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.adapters.registry import discover_adapters
from coding_agent_playbook.hook_policy import adapter_label, resolve_effective_hooks

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.config.tables.hooks import GuardrailsConfig, HooksConfig
    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.validation.context import SyncContext

__all__ = ["format_hooks_section"]

_ABSENT: Final = "off — no [hooks] table (add [hooks] enabled = true or re-run 'playbook init')"
_DISABLED: Final = "off — [hooks] enabled is not true"
_HOOKS_OFF: Final = "hooks are off"


def format_hooks_section(ctx: SyncContext) -> str:
    """The ``=== Hooks ===`` block: the ``[hooks]`` switch, then one line per hook, by id.

    Example::

        print(format_hooks_section(SyncContext.from_repo(repo_root)))
    """
    lines = ["=== Hooks ==="]
    try:
        cfg = ctx.policy_tables.hooks_config()
        guardrails = ctx.policy_tables.guardrails_config()
    except ValueError as exc:
        lines.extend(f"  ✗ {problem}" for problem in str(exc).splitlines())
        lines.append("  [hooks] cannot be read; run 'playbook validate'.")
        return "\n".join(lines)
    lines.append(f"  [hooks]: {_switch_state(ctx, cfg)}")
    lines.extend(_hook_lines(ctx, cfg, guardrails))
    return "\n".join(lines)


def _switch_state(ctx: SyncContext, cfg: HooksConfig) -> str:
    if ctx.policy_tables.hooks is None:
        return _ABSENT
    return "on" if cfg.enabled else _DISABLED


def _hook_lines(ctx: SyncContext, cfg: HooksConfig, guardrails: GuardrailsConfig) -> list[str]:
    """``Hooks (<on> on / <total> total):`` then ``[✓]`` labelled / ``[✗]`` skipped lines."""
    view = resolve_effective_hooks(
        ctx.hooks_resolved,
        ctx.rules_resolved,
        cfg,
        guardrails,
        ctx.facts,
        ctx.repo_root,
        adapters_enabled=ctx.config.adapters_enabled,
    )
    on = {hook.id: hook for hook in view.resolved}
    reasons = {skipped.id: skipped.reason for skipped in view.skipped}
    ids = sorted({hook.frontmatter.id for hook in ctx.hooks_resolved})
    support = _hook_support(ctx)
    lines = [f"  Hooks ({len(on)} on / {len(ids)} total):"]
    for hook_id in ids:
        if hook_id in on:
            lines.append(f"    [✓] {hook_id} ({_labels(on[hook_id], support)})")
        else:
            lines.append(f"    [✗] {hook_id} (skipped: {reasons.get(hook_id, _HOOKS_OFF)})")
    return lines if ids else [*lines, "    (none)"]


def _hook_support(ctx: SyncContext) -> dict[str, Mapping[str, frozenset[str]]]:
    """Each enabled adapter's class-level ``hook_support``, by adapter name."""
    adapters = discover_adapters(ctx.config)
    return {name: type(adapter).hook_support for name, adapter in sorted(adapters.items())}


def _labels(hook: ResolvedHook, support: Mapping[str, Mapping[str, frozenset[str]]]) -> str:
    return ", ".join(
        f"{name}: {adapter_label(hook, name, events)}" for name, events in support.items()
    )
