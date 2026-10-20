"""stop-drift-and-orphan-gate: the ``drift`` Stop stage (specs/prK-hook-pack.md §E.1, §E.0.4).

Generated outputs that drifted from the lockfile, or orphans a sync would
delete, block the end of the turn with one line: ``Playbook drift: <files>.
Run playbook validate && playbook sync before finishing.``

- :class:`DriftStage` implements K2's ``Stage`` contract: deterministic, stage
  0, ``needs_diff=False`` (with ``[output] commit = false`` the outputs are
  gitignored, so the working-tree fingerprint never sees a hand edit of
  them). It applies only when the session ledger shows a write that touched a
  canonical source, a detector input or a generated output (a Bash write into
  an output dir included); a Read never activates it.
- The fast path is ``_drift.drift_fast_path``. When it is clean and canonical
  sources or detector inputs were touched, the slow path runs ``playbook sync
  --check`` as a child (it renders, so never in-process: L3): only a render
  sees a lockfile orphan whose canonical source was deleted.
- A child that stopped before any drift report because something is in the
  way of the output prints ``Cannot verify <path>: …``: that is ``red`` with a
  ``cannot verify`` finding for ``<path>`` (``_drift.sync_check_findings``).
- Any other error or timeout is ``skipped`` (``NOT verified``), never green.

The Stop coordinator (stop-ci-parity-gate) plans the stage through
:func:`drift_stage` and owns the one-block-per-fingerprint budget. Only when
the coordinator is not selected (disabled, or absent from the config) does the
dispatcher call this hook's own binding: it runs the stage alone, blocks once
per distinct finding per session and then only notes, approximating that budget.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.proc import ProcTimeout
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.handlers.protect._source_changed import run_playbook
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult, StopPlan

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.handlers.protect._drift import DriftFinding
    from coding_agent_playbook.hook_runtime.stop.stages import SkipCategory

    type FastPath = Callable[..., list[DriftFinding]]

__all__ = [
    "CONFIG_SCHEMA",
    "STAGE_NAME",
    "DriftStage",
    "drift_stage",
    "stop_drift_and_orphan_gate",
    "touched_categories",
]

STAGE_NAME: Final = "drift"
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "stage": ConfigKey("string", "replace", (STAGE_NAME,)),
}
#: Ledger categories that activate the stage, and the ones that also need a render.
_ACTIVATING: Final = frozenset({"canonical", "detector_input", "generated"})
_NEEDS_RENDER: Final = frozenset({"canonical", "detector_input"})
#: Tool classes that never write: their ledger lines never activate the stage (an MCP
#: tool or a subagent may write, so they count).
_READ_ONLY: Final = frozenset({"read", "search", "web"})
_UNCHANGED_NOTE: Final = "Playbook drift is unchanged since the last block: NOT verified."
_SKIPPED_NOTE: Final = "Playbook drift check skipped ({category}): NOT verified."


def touched_categories(plan: StopPlan) -> frozenset[str]:
    """The ledger categories of every line that may have written something.

    Example::

        >>> touched_categories(plan)  # doctest: +SKIP
        frozenset({'generated'})
    """
    found: set[str] = set()
    for line in plan.ledger:
        cats = line.get("cats")
        if line.get("tc") not in _READ_ONLY and isinstance(cats, list):
            found.update(cat for cat in cats if isinstance(cat, str))
    return frozenset(found)


def _drift_fast_path(root: str, cfg: GuardConfig, *, platform: str) -> list[DriftFinding]:
    """``_drift.drift_fast_path``, imported only once the stage runs (lockfile, tomllib: §D.1)."""
    from coding_agent_playbook.hook_runtime.handlers.protect._drift import drift_fast_path

    return drift_fast_path(root, cfg, platform=platform)


@dataclass(frozen=True, slots=True, kw_only=True)
class DriftStage:
    """The ``drift`` stage of one Stop: ``fast_path`` is injectable for the zero-read test.

    Example::

        >>> stage = drift_stage(ev, ctx)  # doctest: +SKIP
        >>> stage.run(plan, ctx.deadline).status if stage.applies(plan) else "inactive"
        'green'
    """

    ctx: HandlerContext
    repo_root: str
    fast_path: FastPath = _drift_fast_path
    name: str = STAGE_NAME
    cost: StageCost = StageCost.DETERMINISTIC
    needs_diff: bool = False
    mode: str = "block"

    def applies(self, plan: StopPlan) -> bool:
        """Active only when the ledger shows a write to a source, an input or an output."""
        return bool(touched_categories(plan) & _ACTIVATING)

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """``red`` with the one drift line, ``green``, or ``skipped`` on any failure."""
        try:
            findings = self._findings(plan, deadline)
        except ProcTimeout:
            return _skipped("timeout")
        except Exception:  # a stage that failed is never reported green (§E.0.5)
            return _skipped("crash")
        if findings is None:
            return _skipped("timeout")
        if not findings:
            return StageResult(STAGE_NAME, "green")
        from coding_agent_playbook.hook_runtime.handlers.protect._drift import drift_line

        return StageResult(STAGE_NAME, "red", lines=(drift_line(findings),))

    def _findings(self, plan: StopPlan, deadline: float) -> list[DriftFinding] | None:
        found = self.fast_path(self.repo_root, self.ctx.cfg, platform=self.ctx.platform)
        if found or not touched_categories(plan) & _NEEDS_RENDER:
            return found
        ctx = dataclasses.replace(self.ctx, deadline=deadline)
        checked = run_playbook(ctx, self.repo_root, ["sync", "--check"])
        if checked is None:
            return None  # no time left for the child: not verified
        from coding_agent_playbook.hook_runtime.handlers.protect._drift import sync_check_findings

        return [] if checked.returncode == 0 else sync_check_findings(checked.stdout)


def drift_stage(ev: CanonicalEvent, ctx: HandlerContext) -> DriftStage | None:
    """The ``drift`` stage for ``ev``'s repository (``None`` outside one): the coordinator's factory.

    Example::

        >>> drift_stage(stop_event, ctx).name  # doctest: +SKIP
        'drift'
    """
    return None if ev.repo is None else DriftStage(ctx=ctx, repo_root=ev.repo.worktree_root)


@register_hook_handler(
    "stop_drift_and_orphan_gate",
    events=["stop"],
    decisions=["deny", "none"],
    config_schema=CONFIG_SCHEMA,
)
def stop_drift_and_orphan_gate(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Run the ``drift`` stage alone (no coordinator selected): deny once, then note.

    Example::

        >>> stop_drift_and_orphan_gate(stop_after_hand_edit, ctx).reason.splitlines()[-1]
        ... # doctest: +SKIP
        'Run playbook validate && playbook sync before finishing.'
    """
    stage = drift_stage(ev, ctx)
    if stage is None or ctx.hatches.gate_off:
        return None
    ledger = tuple(ctx.ledger.read()) if ctx.ledger is not None else ()
    plan = StopPlan(event=ev, stages=(stage,), ledger=ledger)
    if not stage.applies(plan):
        return None
    return _standalone(ctx, stage.run(plan, ctx.deadline))


def _standalone(ctx: HandlerContext, result: StageResult) -> HandlerResult | None:
    """The stage verdict as this hook's own result: one block per distinct finding."""
    hook_id = ctx.hook.id
    if result.status == "skipped":
        note = _SKIPPED_NOTE.format(category=result.skip_category)
        return HandlerResult(
            decision=Decision.NONE, hook_id=hook_id, rule_id="skipped", user_note=note
        )
    if result.status != "red":
        return None
    from coding_agent_playbook.hook_runtime.handlers.protect._drift import DRIFT_ADVICE

    # Two lines: the deny reason cap (160 characters a line) would cut the advice.
    reason = "\n".join(
        line.replace(f" {DRIFT_ADVICE}", f"\n{DRIFT_ADVICE}") for line in result.lines
    )
    digest = hashlib.sha256(reason.encode("utf-8")).hexdigest()[:16]
    if ctx.session.once(f"drift:block:{digest}"):
        return HandlerResult(
            decision=Decision.DENY, hook_id=hook_id, rule_id="drift", reason=reason
        )
    return HandlerResult(
        decision=Decision.NONE, hook_id=hook_id, rule_id="drift", user_note=_UNCHANGED_NOTE
    )


def _skipped(category: SkipCategory) -> StageResult:
    return StageResult(STAGE_NAME, "skipped", skip_category=category)
