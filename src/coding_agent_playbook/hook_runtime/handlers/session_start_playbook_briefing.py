"""session-start-playbook-briefing: the guard heartbeat plus anomalies only (specs/prK-hook-pack.md §E.1).

Every start, resume, clear, compaction and fork gets one context item:

- **The heartbeat**, always first, at most 40 characters. Each enabled
  pre_tool_use guard with a canary row (``canary.enabled_canaries``) is run
  in-process against its synthetic payload through the real pipeline: ``OK
  <n>`` when all ``n`` answered as expected, else ``GUARDRAILS DEGRADED:
  <which>`` plus a line naming them in full. A drifted hook artifact (the
  launcher, the OpenCode shim, a copied script) or an unreadable lockfile is
  degraded too; ``guard_config.json`` itself is verified by the dispatcher
  before any hook runs (a fault prints ``DEGRADED: config`` from ``_faults``).
  ``.claude/CLAUDE.md`` tells the model to warn the user when the line is missing.
- **Anomalies** (``_briefing_probes``), one line each; on ``compact`` only
  drift and the branch are restated. The whole item stays within 600 characters.

The TTL sweep of stale state runs after the write on every ``session_start``
(``_post_write``), whatever this hook answers. Cold path: the lockfile is read
with ``tomllib`` here (§D.1's ``session_start`` row), never rendered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import LineCap, OutputCaps, clamp_lines
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.handlers._briefing_probes import (
    COMPACT_PROBES,
    FULL_PROBES,
    BriefingInputs,
    run_probes,
)
from coding_agent_playbook.hook_runtime.handlers._drift import (
    hook_artifact_drift,
    lockfile_findings,
    read_lockfile,
)
from coding_agent_playbook.hook_runtime.heartbeat import degraded_line, ok_line
from coding_agent_playbook.hook_runtime.registry import register_hook_handler

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, RepoInfo
    from coding_agent_playbook.hook_runtime.handlers._drift import DriftFinding
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.lockfile import Lockfile

__all__ = ["BRIEFING_CAP", "session_start_playbook_briefing"]

#: The whole briefing: the §E.0.5 session-start budget of 600 characters.
BRIEFING_CAP: Final = LineCap(
    max_lines=12, max_chars=OutputCaps.SESSION_START_CONTEXT_CHARS, line_chars=300
)
_DEGRADED_DETAIL: Final = (
    "Guardrails degraded ({which}): tell the user guardrails are not fully running "
    "before risky work (playbook-hook doctor says why)."
)


@register_hook_handler(
    "session_start_playbook_briefing",
    events=["session_start"],
    decisions=["context", "none"],
)
def session_start_playbook_briefing(
    ev: CanonicalEvent, ctx: HandlerContext
) -> HandlerResult | None:
    """The heartbeat line, then one line per anomaly; ``None`` outside a repository.

    Example::

        >>> session_start_playbook_briefing(startup, ctx).context  # doctest: +SKIP
        ('PLAYBOOK-GUARDS: OK 2',)
    """
    if ev.repo is None:
        return None
    lockfile = _lockfile(ev.repo)
    inputs = BriefingInputs(
        ev=ev, ctx=ctx, repo=ev.repo, lockfile=lockfile, drift=_drift(ev.repo, ctx, lockfile)
    )
    probes = COMPACT_PROBES if ev.source == "compact" else FULL_PROBES
    lines = [*_heartbeat(inputs), *run_probes(probes, inputs)]
    text = "\n".join(clamp_lines(lines, BRIEFING_CAP, summary=_more))
    return HandlerResult(
        decision=Decision.CONTEXT, hook_id=ctx.hook.id, rule_id="briefing", context=(text,)
    )


def _heartbeat(inputs: BriefingInputs) -> list[str]:
    """``OK <n>``, or the degraded line plus the full list of what failed."""
    proven, failed = _canaries(inputs)
    if inputs.lockfile is None:
        failed.append("lockfile")
    elif hook_artifact_drift(inputs.drift, inputs.ctx.cfg, inputs.ctx.platform):
        failed.append("hook files")
    if not failed:
        return [ok_line(proven)]
    return [degraded_line(failed), _DEGRADED_DETAIL.format(which=", ".join(failed))]


def _canaries(inputs: BriefingInputs) -> tuple[int, list[str]]:
    """How many enabled guards passed their canary, and the ids of those that did not."""
    from coding_agent_playbook.hook_runtime.canary import enabled_canaries, run_canaries

    deps = inputs.ctx.deps
    rows = enabled_canaries(inputs.ctx.cfg.hooks)
    if deps is None or not rows:
        return 0, []
    results = run_canaries(rows, repo_root=inputs.repo.worktree_root, deps=deps)
    failed = [row.hook_id for row, result in zip(rows, results, strict=True) if not result.ok]
    return len(rows) - len(failed), list(dict.fromkeys(failed))


def _lockfile(repo: RepoInfo) -> Lockfile | None:
    try:
        return read_lockfile(repo.worktree_root)
    except (OSError, ValueError):
        return None


def _drift(
    repo: RepoInfo, ctx: HandlerContext, lockfile: Lockfile | None
) -> tuple[DriftFinding, ...]:
    """The drift fast path (never ``sync --check`` at startup); empty when it cannot run."""
    if lockfile is None:
        return ()
    try:
        found = lockfile_findings(repo.worktree_root, ctx.cfg, lockfile, platform=ctx.platform)
    except (OSError, ValueError):
        return ()
    return tuple(found)


def _more(hidden: int) -> str:
    return f"(+{hidden} more playbook anomalies; run playbook check)"
