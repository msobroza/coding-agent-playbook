"""``playbook-hook doctor``'s guard-decision-log summary (specs/prK-hook-pack.md §E.5, principle 17).

One ``decision-log:<hook_id>`` row per guard that decided something in the
last ``--since`` days: deny and ask counts, the override rate (asks the user
approved) and degraded events. It is the evidence to read before flipping an
``ask`` to ``deny`` or promoting an opt-in hook. Informational only (``ok``):
a busy guard is not a broken install. No log, no rows. Read-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._doctor_checks import Check
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME, iso_utc
from coding_agent_playbook.security.decision_summary import read_decisions, summarize_decisions

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.event import RepoInfo

__all__ = ["CHECK_PREFIX", "DEFAULT_SINCE_DAYS", "decision_log_checks"]

#: The doctor check name of one guard's row: ``decision-log:<hook_id>``.
CHECK_PREFIX: Final = "decision-log"
DEFAULT_SINCE_DAYS: Final = 30
_DAY_S: Final = 86_400


def decision_log_checks(
    repo: RepoInfo, deps: RuntimeDeps, *, since_days: int = DEFAULT_SINCE_DAYS
) -> list[Check]:
    """One ``ok`` row per guard in ``repo``'s decision log over the last ``since_days`` days.

    Example::

        >>> [c.detail for c in decision_log_checks(repo, deps)]  # doctest: +SKIP
        ['deny 2, ask 4, override 1 (25%), degraded 0']
    """
    state = deps.state.root if deps.state is not None else Path(repo.git_dir) / STATE_DIR_NAME
    since = iso_utc(deps.clock.time() - since_days * _DAY_S)
    summaries = summarize_decisions(read_decisions(state, since_ts=since))
    return [
        Check(
            f"{CHECK_PREFIX}:{summary.hook_id}", "ok", f"{summary.line()} (last {since_days} days)"
        )
        for summary in summaries
    ]
