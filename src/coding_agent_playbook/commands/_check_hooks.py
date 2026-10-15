"""The hook parts of ``playbook check`` (specs/prK-lifecycle-hooks.md §A.8, §C.1.1, §C.2.6).

- :func:`format_hooks_section`: the ``=== Hooks ===`` block. Every on hook is
  labelled per enabled adapter (``enforced`` / ``degraded`` / ``advisory`` /
  ``—``, from the adapter class's ``hook_support``), so advice is never
  mistaken for enforcement (QC-10); every off hook gets its reason.
- :func:`scoped_drift`: drift lines for scoped lock entries. A co-owned file
  (``.claude/settings.json``) is judged element by element, so user keys, user
  hook groups and reformatting never count as drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.adapters._settings_drift import managed_entry_drift
from coding_agent_playbook.adapters.claude_settings import (
    SettingsMergeError,
    decode_settings,
    parse_settings,
)
from coding_agent_playbook.hook_policy import adapter_label, resolve_effective_hooks
from coding_agent_playbook.orchestrator import discover_adapters

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.hooks_config import GuardrailsConfig, HooksConfig
    from coding_agent_playbook.lockfile import LockEntry
    from coding_agent_playbook.orchestrator import SyncContext

__all__ = ["format_hooks_section", "scoped_drift"]

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


def scoped_drift(repo_root: Path, entries: Iterable[LockEntry]) -> list[str]:
    """``managed entry edited|missing: <path>#<pointer>`` / ``unreadable: <path> (...)`` lines.

    Whole-file entries are ignored here. An absent file reads as ``{}``, so its
    entries are each ``missing``; a file Claude Code would reject is one
    ``unreadable`` line.

    Example::

        drift.extend(scoped_drift(ctx.repo_root, lockfile.entries))
    """
    by_path: dict[str, list[LockEntry]] = {}
    for entry in entries:
        if entry.scope:
            by_path.setdefault(entry.path, []).append(entry)
    lines: list[str] = []
    for rel, scoped in by_path.items():
        try:
            doc = parse_settings(decode_settings(_read(repo_root / rel), path=rel), path=rel)
        except SettingsMergeError as exc:
            lines.append(f"  unreadable: {rel} (line {exc.line}, col {exc.col}: {exc.message})")
            continue
        except OSError as exc:  # a directory, no permission: still one line, never a traceback
            lines.append(f"  unreadable: {rel} ({exc.strerror or exc})")
            continue
        lines.extend(f"  {drift.line()}" for drift in managed_entry_drift(doc, scoped))
    return lines


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
