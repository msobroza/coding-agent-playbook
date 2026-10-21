"""``playbook-hook doctor``'s ignored-call rows (specs/prU-core-python-skills.md D79).

The dispatcher stays inert on a foreign payload and on an event outside git,
and leaves one ``ignored`` decision line for it (``dispatch._ignored``). Doctor
shows one ``ignored:<reason>`` row per reason seen in the last ``--since``
days, most recent first: the count, the last time, the harnesses and events.
It reads the worktree's log and the user-level one (calls outside git).

Two reasons are what a *real* session looks like when it is misconfigured:
``claude_project_dir_unset`` and ``missing_session_id``. Every guard was off for
those calls, so their rows are warnings naming the likely cause. The rest are
``ok``: another harness reading ``.claude/settings.json`` is expected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.diagnostics._doctor_checks import Check
from coding_agent_playbook.hook_runtime.dispatch._ignored import (
    IGNORED,
    NOT_A_REPO,
    user_state_root,
)
from coding_agent_playbook.hook_runtime.state.decision_summary import read_decisions
from coding_agent_playbook.hook_runtime.state.store import STATE_DIR_NAME, iso_utc

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.dispatch.event import RepoInfo

__all__ = ["IGNORED_PREFIX", "MISCONFIGURED", "ignored_call_checks"]

#: The doctor check name of one reason's row: ``ignored:<reason>``.
IGNORED_PREFIX: Final = "ignored"
_DAY_S: Final = 86_400
#: Reason -> why a real session would show it: these rows are warnings.
MISCONFIGURED: Final = {
    "claude_project_dir_unset": (
        "CLAUDE_PROJECT_DIR was not set for the hook, so every guard was off; "
        "check how the hook command is launched"
    ),
    "missing_session_id": (
        "the payload carried no session_id, so every guard was off; "
        "check the harness version and the hook registration"
    ),
}


@dataclass(slots=True)
class _ReasonTally:
    reason: str
    count: int = 0
    last_ts: str = ""
    harnesses: set[str] = field(default_factory=set)
    events: set[str] = field(default_factory=set)

    def add(self, record: dict[str, Any]) -> None:
        self.count += 1
        self.last_ts = max(self.last_ts, str(record.get("ts", "")))
        self.harnesses.add(str(record.get("harness", "?")))
        self.events.add(str(record.get("event", "?")))

    def check(self) -> Check:
        plural = "call" if self.count == 1 else "calls"
        seen = f"{', '.join(sorted(self.harnesses))}: {', '.join(sorted(self.events))}"
        detail = f"{self.count} {plural}, last {self.last_ts} ({seen})"
        if self.reason == NOT_A_REPO:
            detail += "; outside any git repository, where hooks are off"
        hint = MISCONFIGURED.get(self.reason)
        if hint is None:
            return Check(f"{IGNORED_PREFIX}:{self.reason}", "ok", detail)
        detail += f"; likely a misconfigured real session: {hint}"
        return Check(f"{IGNORED_PREFIX}:{self.reason}", "warning", detail)


def ignored_call_checks(
    repo: RepoInfo | None, deps: RuntimeDeps, *, since_days: int
) -> list[Check]:
    """One row per ignored-call reason of the last ``since_days`` days, most recent first.

    ``repo`` is ``None`` outside git: only the user-level log is read then.

    Example::

        >>> [c.name for c in ignored_call_checks(repo, deps, since_days=30)]  # doctest: +SKIP
        ['ignored:claude_project_dir_unset', 'ignored:event_mismatch']
    """
    since = iso_utc(deps.clock.time() - since_days * _DAY_S)
    tallies: dict[str, _ReasonTally] = {}
    for record in _ignored_records(_state_roots(repo, deps), since):
        reason = str(record.get("rule_id") or "unknown")
        tallies.setdefault(reason, _ReasonTally(reason)).add(record)
    ordered = sorted(tallies.values(), key=lambda t: (t.last_ts, t.reason), reverse=True)
    return [tally.check() for tally in ordered]


def _state_roots(repo: RepoInfo | None, deps: RuntimeDeps) -> list[Path]:
    roots = [user_state_root(deps)]
    if deps.state is not None:
        roots.insert(0, deps.state.root)
    elif repo is not None:
        roots.insert(0, Path(repo.git_dir) / STATE_DIR_NAME)
    return roots


def _ignored_records(roots: Iterable[Path], since: str) -> list[dict[str, Any]]:
    return [
        record
        for root in roots
        for record in read_decisions(root, since_ts=since)
        if record.get("decision") == IGNORED and record.get("canary") is not True
    ]
