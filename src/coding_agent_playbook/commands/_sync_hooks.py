"""The hooks half of ``playbook sync`` (specs/prK-lifecycle-hooks.md §C.1.3, §C.1.5, §B.1).

- :func:`resolve_sync_hooks`: the committed ``[hooks]`` / ``[guardrails]``
  policy and ``hook_policy.resolve_effective_hooks``, the single gating path
  (``filter_applies_if`` is never widened for hooks), with bodies rendered;
- :func:`write_runtime_outputs`: the sync-level ``guard_config.json`` and the
  copied scripts, into the output root in every mode (so ``--check`` compares
  them), whenever hooks are enabled and a hook-capable adapter is on. Its
  ``protected`` table is this sync's written set as lock rows, the adapters'
  scan dirs and the layer packages (specs/prK-hook-pack.md §E.0.5);
- :func:`check_settings_readable`: refuses a ``settings.json`` the Claude Code
  merge would choke on *before* any adapter writes;
- :func:`finish_write`: write mode's pins, summary lines and approvals;
- :func:`opencode_restart_notice`: the §C.1.5 restart line, from the previous
  and the new lockfile's whole-file shim entry (both ``[output] commit``
  settings; never in a check, where no lockfile is written).

An absent ``[hooks]`` table means zero byte change plus one notice line: an
engine upgrade never switches executable hooks on.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from coding_agent_playbook import __version__ as _installed_version
from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.claude_settings import (
    CLAUDE_SETTINGS_PATH,
    decode_settings,
    parse_settings,
)
from coding_agent_playbook.commands import _sync_hook_local
from coding_agent_playbook.commands._sync_lockfile import HookDispatch
from coding_agent_playbook.commands._sync_output import shared_outputs
from coding_agent_playbook.guard_config import (
    SYNC_OUTPUT_LOCATIONS,
    GuardConfigInputs,
    ProtectInputs,
    adapter_output_dirs,
    copy_hook_scripts,
    protected_rows,
    render_guard_config,
    resolve_resource_roots,
    write_guard_config,
)
from coding_agent_playbook.hook_policy import (
    HOOK_CAPABLE_ADAPTERS,
    HOOK_LABELS,
    RegistryCatalog,
    adapter_label,
    resolve_effective_hooks,
)
from coding_agent_playbook.hook_registrations import OPENCODE_SHIM_PATH
from coding_agent_playbook.hooks_config import GuardrailsConfig, HooksConfig
from coding_agent_playbook.lockfile import Provenance
from coding_agent_playbook.orchestrator import engine_package_of

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.adapters.claude_settings import MergeResult, SettingsMergeError
    from coding_agent_playbook.commands._sync_hook_local import SyncHookDeps
    from coding_agent_playbook.commands._sync_lockfile import ProvenanceRecorder
    from coding_agent_playbook.hook_policy import ResolvedHook, SkippedHook
    from coding_agent_playbook.lockfile import Lockfile
    from coding_agent_playbook.orchestrator import SyncContext

__all__ = [
    "HOOKS_NOTICE",
    "HookPolicyError",
    "SyncHooks",
    "check_settings_readable",
    "finish_write",
    "layer_packages",
    "opencode_restart_notice",
    "report_settings_error",
    "resolve_sync_hooks",
    "runtime_enabled",
    "settings_merge",
    "summary_lines",
    "write_runtime_outputs",
]

#: The one line an absent ``[hooks]`` table earns (§B.1).
HOOKS_NOTICE: Final = "hooks available: add [hooks] enabled = true or re-run playbook init"
_CLAUDE: Final = "claude_code"


class HookPolicyError(ValueError):
    """The committed ``[hooks]`` / ``[guardrails]`` table cannot be parsed (validate's H21)."""


@dataclass(frozen=True)
class SyncHooks:
    """The hooks of one sync: the committed policy and the effective view, bodies rendered.

    Example::

        hooks = resolve_sync_hooks(ctx, render_body)
        [hook.id for hook in hooks.resolved]
    """

    config: HooksConfig = field(default_factory=HooksConfig)
    guardrails: GuardrailsConfig = field(default_factory=GuardrailsConfig)
    table_present: bool = False
    resolved: tuple[ResolvedHook, ...] = ()
    skipped: tuple[SkippedHook, ...] = ()
    warnings: tuple[str, ...] = ()

    def dispatch(self, source_root: Path, prior_lock: Lockfile | None) -> HookDispatch:
        """What every adapter's ``begin_sync`` / ``write_hook`` receives."""
        return HookDispatch(self.resolved, source_root, prior_lock, self.config)


def resolve_sync_hooks(
    ctx: SyncContext, render_body: Callable[[ResolvedHook], ResolvedHook]
) -> SyncHooks:
    """Parse the committed policy, resolve the on hooks, and render each body with ``render_body``.

    Raises :class:`HookPolicyError` for a malformed table (the validate gate
    reports it first in write and ``--check`` mode).

    Example: ``resolve_sync_hooks(ctx, lambda hook: hook)``.
    """
    try:
        config = ctx.policy_tables.hooks_config()
        guardrails = ctx.policy_tables.guardrails_config()
    except ValueError as exc:
        raise HookPolicyError(str(exc)) from exc
    view = resolve_effective_hooks(
        ctx.hooks_resolved,
        ctx.rules_resolved,
        config,
        guardrails,
        ctx.facts,
        ctx.repo_root,
        adapters_enabled=ctx.config.adapters_enabled,
        handlers=RegistryCatalog(),  # builtins from another distribution become entry points
    )
    return SyncHooks(
        config=config,
        guardrails=guardrails,
        table_present=ctx.policy_tables.hooks is not None,
        resolved=tuple(render_body(hook) for hook in view.resolved),
        skipped=tuple(view.skipped),
        warnings=tuple(view.warnings),
    )


def runtime_enabled(ctx: SyncContext, hooks: SyncHooks) -> bool:
    """Whether the sync-level runtime outputs and pins exist: enabled + a hook-capable adapter."""
    return hooks.config.enabled and any(
        name in HOOK_CAPABLE_ADAPTERS for name in ctx.config.adapters_enabled
    )


def write_runtime_outputs(
    ctx: SyncContext, hooks: SyncHooks, out_root: Path, recorder: ProvenanceRecorder
) -> None:
    """Write ``guard_config.json`` and the script copies into ``out_root``; record provenance.

    Example: ``write_runtime_outputs(ctx, hooks, scratch, recorder)``.
    """
    if not runtime_enabled(ctx, hooks):
        return
    inputs = GuardConfigInputs(
        hooks=hooks.resolved,
        hooks_config=hooks.config,
        guardrails=hooks.guardrails,
        engine_version=ctx.config.engine_version or _installed_version,
        generated=_generated_locations(ctx.adapters),
        protected=_protect_inputs(ctx, out_root, recorder),
    )
    path = write_guard_config(out_root, render_guard_config(inputs))
    recorder.record([path], Provenance(kind="runtime"))
    for copy in copy_hook_scripts(hooks.resolved, out_root):
        origin = Provenance(kind="hook", artifact_id=copy.hook.id, source=copy.hook.source_package)
        recorder.record(copy.paths, origin)


def _protect_inputs(
    ctx: SyncContext, out_root: Path, recorder: ProvenanceRecorder
) -> ProtectInputs:
    """The ``protected`` table's inputs: what the adapters wrote, where they scan, the layers."""
    rows = protected_rows(
        recorder.provenance, recorder.managed, out_root, shared=shared_outputs(ctx.adapters)
    )
    return ProtectInputs(rows, adapter_output_dirs(ctx.adapters, out_root), layer_packages(ctx))


def layer_packages(ctx: SyncContext) -> tuple[str, ...]:
    """The importable artifact layers: the engine package, then ``overlays_enabled`` (packs too).

    Example: ``layer_packages(ctx) == ("coding_agent_playbook",)`` without overlays.
    """
    return (engine_package_of(ctx.artifact_source), *ctx.config.overlays_enabled)


def _generated_locations(adapters: Mapping[str, Adapter]) -> list[str]:
    locations = {loc for adapter in adapters.values() for loc in type(adapter).output_locations}
    return sorted(locations | set(SYNC_OUTPUT_LOCATIONS))


def check_settings_readable(ctx: SyncContext, hooks: SyncHooks, prior: Lockfile | None) -> None:
    """Raise ``SettingsMergeError`` now if the Claude Code merge would refuse ``settings.json``.

    Only when that merge runs: Claude Code is enabled and either a hook
    targets it or the prior lockfile owns elements of the file. Called before
    any adapter writes, so invalid JSON never leaves a half-written sync (a
    merge-time error, such as a mixed group, can still stop one mid-way).

    Example: ``check_settings_readable(ctx, hooks, previous_lockfile)``.
    """
    if _CLAUDE not in ctx.config.adapters_enabled:
        return
    targeted = any(_CLAUDE in hook.supports for hook in hooks.resolved)
    owned = prior is not None and any(
        entry.scope and entry.path == CLAUDE_SETTINGS_PATH for entry in prior.entries
    )
    if not (targeted or owned or hooks.config.render_remediation_allow):
        return
    try:
        data = (ctx.repo_root / CLAUDE_SETTINGS_PATH).read_bytes()
    except FileNotFoundError:
        return
    parse_settings(decode_settings(data))


def report_settings_error(exc: SettingsMergeError, *, check: bool) -> int:
    """Explain a ``settings.json`` that cannot be merged; return 1 (never a traceback).

    Example: ``return report_settings_error(exc, check=True)``.
    """
    if check:
        print(f"Cannot verify {exc.path}: {exc.message} at {exc.line}:{exc.col}.")
        print("Fix the file (Claude Code rejects it too), then re-run 'playbook sync --check'.")
        return 1
    print(f"error: {exc}", file=sys.stderr)
    print(f"error: playbook sync stopped; {exc.path} was not changed.", file=sys.stderr)
    return 1


def summary_lines(hooks: SyncHooks, adapters: Mapping[str, Adapter]) -> list[str]:
    """The §C.1.5 lines: the notice, the per-adapter label counts and the settings merge.

    Example: ``summary_lines(hooks, ctx.adapters)[0].startswith("✓ Hooks:")``.
    """
    lines: list[str] = []
    if not hooks.table_present:
        lines.append(HOOKS_NOTICE)
    elif hooks.config.enabled:
        lines.append(_hooks_line(hooks, adapters))
    merge = settings_merge(adapters)
    if merge is not None and merge.changed:
        lines.append(
            f"✓ {CLAUDE_SETTINGS_PATH}: {merge.updated} managed entries updated, "
            f"{merge.removed} removed (user keys untouched)"
        )
        lines.extend(f"note: {note}" for note in merge.notes)
    return lines


def _hooks_line(hooks: SyncHooks, adapters: Mapping[str, Adapter]) -> str:
    skipped = f", {len(hooks.skipped)} skipped" if hooks.skipped else ""
    per_adapter = "; ".join(
        f"{name}: {counts}"
        for name, adapter in adapters.items()
        if (counts := _label_counts(hooks.resolved, name, type(adapter).hook_support))
    )
    detail = f" ({per_adapter})" if per_adapter else ""
    return f"✓ Hooks: {len(hooks.resolved)} enabled{skipped}{detail}"


def _label_counts(
    resolved: tuple[ResolvedHook, ...], name: str, support: Mapping[str, frozenset[str]]
) -> str:
    labels = [adapter_label(hook, name, support) for hook in resolved]
    return ", ".join(
        f"{labels.count(label)} {label}"
        for label in HOOK_LABELS
        if label != "—" and labels.count(label)
    )


def settings_merge(adapters: Mapping[str, Adapter]) -> MergeResult | None:
    """What this sync's ``settings.json`` merge did, or None when it never ran."""
    adapter = adapters.get(_CLAUDE)
    return adapter.settings_merge if isinstance(adapter, ClaudeCodeAdapter) else None


def finish_write(
    ctx: SyncContext, hooks: SyncHooks, deps: SyncHookDeps, *, restart_notice: str | None = None
) -> None:
    """Write mode, after the lockfile is saved: pins, summary lines and warnings, approvals.

    ``restart_notice`` (from :func:`opencode_restart_notice`) prints after the
    summary lines, before any warning or trust question.

    Example: ``finish_write(ctx, hooks, SyncHookDeps(), restart_notice=None)``.
    """
    live = runtime_enabled(ctx, hooks)
    if live:
        version = ctx.config.engine_version or _installed_version
        roots = resolve_resource_roots(layer_packages(ctx))
        _sync_hook_local.write_pins(
            ctx.repo_root, deps, engine_version=version, resource_roots=roots
        )
    for line in summary_lines(hooks, ctx.adapters):
        print(line)
    if restart_notice is not None:
        print(restart_notice)
    merge = settings_merge(ctx.adapters)
    for warning in [*hooks.warnings, *(merge.warnings if merge is not None else ())]:
        print(f"warning: {warning}", file=sys.stderr)
    if live:
        _sync_hook_local.approve_pending(hooks.resolved, ctx.repo_root, deps)


def opencode_restart_notice(previous: Lockfile | None, current: Lockfile) -> str | None:
    """The restart line when this sync wrote, changed or removed the OpenCode shim, else None.

    OpenCode V1 has no plugin hot reload, so new shim bytes (a ``REG``
    change) wait for a restart; ``guard_config.json`` is read on every
    dispatch and never needs one (§C.3.2 "Reload behavior").

    Example::

        >>> opencode_restart_notice(None, Lockfile(2, "1.0", "", [])) is None
        True
    """
    before, after = _shim_sha256(previous), _shim_sha256(current)
    if before == after:
        return None
    if after is None:
        return f"! {OPENCODE_SHIM_PATH} removed: restart OpenCode to unload it"
    return f"! {OPENCODE_SHIM_PATH} changed: restart OpenCode to load it"


def _shim_sha256(lock: Lockfile | None) -> str | None:
    """The sha256 of ``lock``'s whole-file shim entry; a scoped entry never vouches for bytes."""
    entries = lock.entries if lock is not None else ()
    return next(
        (e.sha256 for e in entries if e.path == OPENCODE_SHIM_PATH and e.is_whole_file), None
    )
