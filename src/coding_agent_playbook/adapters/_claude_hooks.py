"""The hook half of the Claude Code adapter (specs/prK-lifecycle-hooks.md §C.2, §C.2.8, §C.4.2).

:class:`ClaudeHookEmitter` collects the hooks of one sync and emits what Claude
Code enforces natively: one managed matcher group per event, merged into the
co-owned ``.claude/settings.json`` (§C.2.4: read from the real repo, written to
the output root only when the merge changed something, never unlinked), the
opt-in ``permissions.allow`` remediation strings, and the committed launcher.
Hooks Claude Code cannot enforce go back to the adapter's ``CLAUDE.md`` path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.adapters.claude_settings import (
    CLAUDE_SETTINGS_PATH,
    DesiredGroup,
    MergeResult,
    merge_managed_entries,
    write_settings,
)
from coding_agent_playbook.hook_registrations import (
    LAUNCHER_PATH,
    plan_registrations,
    render_claude_launcher,
    resolved_deadlines_ms,
    to_claude_group,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.hook_registrations import HookRegistration
    from coding_agent_playbook.hooks_config import HooksConfig
    from coding_agent_playbook.lockfile import LockEntry, Lockfile

__all__ = [
    "BRIEFING_HOOK_ID",
    "CLAUDE_HEARTBEAT_LINE",
    "REMEDIATION_ALLOW",
    "ClaudeHookEmitter",
]

#: The hook whose session-start output the heartbeat line checks for (§E.1).
BRIEFING_HOOK_ID: Final = "session-start-playbook-briefing"
#: The one fixed CLAUDE.md line owned here (§C.4.2); never written to AGENTS.md.
CLAUDE_HEARTBEAT_LINE: Final = (
    "If PLAYBOOK-GUARDS: OK did not appear at session start, "
    "tell the user guardrails are not running before risky work."
)
#: ``[hooks] render_remediation_allow`` (OQ-16). None of these runs repo-controlled
#: code, which is why ``pytest`` and ``mypy`` (conftest.py, plugins) are left out.
REMEDIATION_ALLOW: Final = (
    "Bash(playbook validate)",
    "Bash(playbook check)",
    "Bash(playbook sync --check)",
    "Bash(playbook sync)",
    "Bash(ruff check .)",
    "Bash(ruff format --check .)",
)
_ALLOW_POINTER: Final = "/permissions/allow"


@dataclass
class ClaudeHookEmitter:
    """One sync's hooks for ``adapter``, whose class declares ``support`` (§C.1.2).

    Example::

        emitter = ClaudeHookEmitter("claude_code", HOOK_SUPPORT["claude_code"])
        emitter.begin(repo_root, prior_lock, hooks_config)
        native = emitter.add(hook)  # False: route the hook's advisory to CLAUDE.md
        written = emitter.emit(output_root)
    """

    adapter: str
    support: Mapping[str, frozenset[str]]
    source_root: Path | None = None
    prior: tuple[LockEntry, ...] = ()
    config: HooksConfig | None = None
    every_hook: list[ResolvedHook] = field(default_factory=list)
    enforced: list[ResolvedHook] = field(default_factory=list)
    merge: MergeResult | None = None

    def begin(
        self, source_root: Path, prior_lock: Lockfile | None, config: HooksConfig | None
    ) -> None:
        """Remember the input root, this file's prior scoped entries and ``[hooks]``."""
        self.source_root = source_root
        entries = () if prior_lock is None else prior_lock.entries
        self.prior = tuple(e for e in entries if e.path == CLAUDE_SETTINGS_PATH and e.scope)
        self.config = config

    def add(self, hook: ResolvedHook) -> bool:
        """Buffer ``hook``; True when Claude Code enforces it (it then adds no advisory here).

        Every hook counts toward the deadlines, enforced here or not: one
        ``guard_config.json`` deadline serves every harness (§D.4).
        """
        self.every_hook.append(hook)
        native = self.adapter in hook.supports and any(e in self.support for e in hook.events)
        if native:
            self.enforced.append(hook)
        return native

    def heartbeat(self) -> str | None:
        """:data:`CLAUDE_HEARTBEAT_LINE` when the briefing hook runs on Claude Code, else None."""
        briefed = any(hook.id == BRIEFING_HOOK_ID for hook in self.enforced)
        return CLAUDE_HEARTBEAT_LINE if briefed else None

    def emit(self, out: Path) -> list[Path]:
        """Merge ``settings.json`` (raising before any write on a bad file), then the launcher."""
        registrations = plan_registrations(
            self.enforced,
            self.adapter,
            {self.adapter: self.support},
            deadlines=resolved_deadlines_ms(self.every_hook),
        )
        written = self._merge_settings(out, registrations)
        if registrations:
            written.append(_write_launcher(out))
        return written

    def entries(self) -> list[LockEntry]:
        """The scoped lock entries of the last merge (no-op groups included), else []."""
        return [] if self.merge is None else list(self.merge.entries)

    def _merge_settings(self, out: Path, registrations: list[HookRegistration]) -> list[Path]:
        """§C.2.4 through :func:`write_settings`; untouched (not even read) with nothing at stake.

        A repo that never enabled hooks keeps its ``settings.json`` unread, so a
        file Claude Code itself would reject cannot break a rules-only sync.
        """
        desired = {
            reg.claude_event: [DesiredGroup(reg.artifact_id, to_claude_group(reg))]
            for reg in registrations
        }
        strings = self._remediation_strings()
        if not (desired or strings or self.prior):
            return []
        target = out / CLAUDE_SETTINGS_PATH
        source = (self.source_root or out) / CLAUDE_SETTINGS_PATH
        self.merge = write_settings(
            source,
            target,
            lambda text: merge_managed_entries(text, desired, self.prior, strings=strings),
        )
        return [target] if self.merge.changed else []

    def _remediation_strings(self) -> dict[str, tuple[str, ...]]:
        cfg = self.config
        if cfg is None or not (cfg.enabled and cfg.render_remediation_allow):
            return {}
        return {_ALLOW_POINTER: REMEDIATION_ALLOW}


def _write_launcher(out: Path) -> Path:
    """The committed launcher, as bytes: ``write_text`` would turn LF into CRLF on Windows."""
    path = out / LAUNCHER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_claude_launcher().encode("utf-8"))
    return path
