"""One Stop stage run without the coordinator (specs/prK-lifecycle-hooks.md §D.5.1).

When stop-ci-parity-gate is disabled or absent, the dispatcher calls a stage
hook's own ``stop`` binding. :func:`run_alone` approximates the coordinator's
budget for that one stage: a red result denies once per distinct reason per
session and only notes afterwards; ``warn`` lines and a skip (``NOT
verified``) go to the user; ``PLAYBOOK_GATE=off`` silences it.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.stop.output import not_verified_note, red_note
from coding_agent_playbook.hook_runtime.stop.stages import StageResult, StopPlan

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.stop.stages import Stage

__all__ = ["run_alone"]

_DIGEST_CHARS: Final = 16


def run_alone(stage: Stage, ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """``stage``'s verdict as its hook's own Stop result (module docstring).

    Example::

        >>> run_alone(gate_integrity_stage(ev, ctx), ev, ctx).decision  # doctest: +SKIP
        <Decision.DENY: 'deny'>
    """
    if ctx.hatches.gate_off:
        return None
    ledger = tuple(ctx.ledger.read()) if ctx.ledger is not None else ()
    plan = StopPlan(event=ev, stages=(stage,), ledger=ledger, head_tree=_head(ctx))
    if not stage.applies(plan):
        return None
    try:
        result = stage.run(plan, ctx.deadline)
    except Exception:  # a stage that failed is never reported green (§E.0.5)
        result = StageResult(stage.name, "skipped", skip_category="crash")
    return _as_result(result, ctx)


def _as_result(result: StageResult, ctx: HandlerContext) -> HandlerResult | None:
    notes = list(result.user_lines)
    if result.status == "skipped":
        notes.append(not_verified_note(result))
    elif result.status == "warn":
        notes.extend(f"[{result.stage}] {line}" for line in result.lines)
    if result.status != "red":
        return _note(ctx, notes, result.stage) if notes else None
    reason = "\n".join(f"[{result.stage}] {line}" for line in result.lines)
    digest = hashlib.sha256(reason.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]
    if not ctx.session.once(f"{result.stage}:block:{digest}"):
        return _note(ctx, [*notes, red_note(result.stage)], result.stage)
    return HandlerResult(
        decision=Decision.DENY,
        hook_id=ctx.hook.id,
        rule_id=result.stage,
        reason=reason,
        user_note="\n".join(notes),
    )


def _note(ctx: HandlerContext, notes: list[str], stage: str) -> HandlerResult:
    return HandlerResult(
        decision=Decision.NONE, hook_id=ctx.hook.id, rule_id=stage, user_note="\n".join(notes)
    )


def _head(ctx: HandlerContext) -> str | None:
    try:
        return ctx.git.head_tree()
    except Exception:  # unknown HEAD: the stage treats it as unborn
        return None
