"""subagent-stop-verify: check an editing subagent's work inside its own context (specs/prK-hook-pack.md §E.2).

On ``subagent_stop`` (Claude only) it runs the Stop coordinator engine
(§D.5.6) so a red gate blocks the **subagent's** stop and the fix happens in
its context window, not the controller's:

- **Who.** Only subagents whose ``agent_type`` is in ``[hooks.subagent-stop-verify]
  agent_types`` (empty: every type). A subagent whose transcript shows no
  Edit/Write/MultiEdit is read-only and skipped.
- **Scope.** The stages named in ``stages`` (default ``["lint"]``), built from
  the same ``stop_gate`` records as the parent gate. ``lint`` reports only
  findings in the files the subagent edited, read read-only from
  ``agent_transcript_path``. Execution stages need the same user trust entry
  and are serialized through ``locks/exec-stage.lock``.
- **Budget.** The chain and fingerprint state are keyed by ``agent_id``, at
  most ``max_blocks`` (default 2) blocks per subagent; then a note.
- **Claims.** A success claim while the gate is red adds a contradiction line
  to the reason; while it is unverified, a note.
- **Failure.** A transcript that cannot be parsed fails open with ``NOT verified``.
- **HEAD moved.** When the ``session_start`` HEAD snapshot exists (OQ-28), a
  default branch that moved since is reported, never rewritten.
"""

from __future__ import annotations

import dataclasses
from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.config.guard_tables import (
    DEFAULT_MAX_BLOCKS,
    MAX_BLOCKS_RANGE,
)
from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.dispatch.caps import OutputCaps, quote_data
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.paths import normalize_path
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.git.head_snapshot import head_moved_note
from coding_agent_playbook.hook_runtime.handlers.verify._agent_transcript import (
    TranscriptError,
    edited_files,
)
from coding_agent_playbook.hook_runtime.handlers.verify._lint_stage import LintStage
from coding_agent_playbook.hook_runtime.handlers.verify._verify_claim import completion_claim
from coding_agent_playbook.hook_runtime.handlers.verify.stop_ci_parity_gate import (
    WRITE_MARGIN_S,
    build_stage,
    trust_opener,
)
from coding_agent_playbook.hook_runtime.state.store import StateUnavailable
from coding_agent_playbook.hook_runtime.stop.coordinator import (
    CoordinatorDeps,
    GatePolicy,
    StopCoordinator,
    StopScope,
)
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult
from coding_agent_playbook.hook_runtime.stop.tools import seconds_left

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.dispatch.deps import Clock
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, RepoInfo
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.state.store import StateStore
    from coding_agent_playbook.hook_runtime.stop.coordinator import StopOutcome
    from coding_agent_playbook.hook_runtime.stop.stages import Stage, StopPlan

__all__ = [
    "CONFIG_SCHEMA",
    "DEFAULT_STAGES",
    "EXEC_LOCK",
    "SCOPED_STAGES",
    "ExecLocked",
    "subagent_stop_verify",
]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "stages": ConfigKey("list"),
    "agent_types": ConfigKey("list"),
    "max_blocks": ConfigKey("integer"),
}
DEFAULT_STAGES: Final = ("lint",)
#: The stages a subagent may run: its edits' lint and metrics, plus the trusted execution ones.
SCOPED_STAGES: Final = ("lint", "quality-metrics", "typecheck", "tests")
#: The state lock serializing execution stages across concurrent subagents (§D.5.6).
EXEC_LOCK: Final = "exec-stage"
TRANSCRIPT_NOTE: Final = (
    "subagent-stop-verify: the subagent's transcript could not be read; its work is NOT verified."
)
NO_STAGES_NOTE: Final = (
    "subagent-stop-verify: no Stop stage records in this worktree (is stop-ci-parity-gate off?); "
    "the subagent's work is NOT verified."
)
_CLAIM_CHARS: Final = 60


@dataclass(frozen=True, slots=True)
class ExecLocked:
    """An execution stage that runs only while it holds ``locks/exec-stage.lock``.

    A busy lock past the stage's deadline is a ``timeout`` skip (NOT verified);
    a stateless store runs the stage unserialized rather than not at all.

    Example: ``ExecLocked(typecheck_stage(ev, ctx), ctx.session.store, ctx.clock)``.
    """

    inner: Stage
    store: StateStore
    clock: Clock

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def cost(self) -> StageCost:
        return self.inner.cost

    @property
    def needs_diff(self) -> bool:
        return self.inner.needs_diff

    @property
    def mode(self) -> str:
        return self.inner.mode

    def applies(self, plan: StopPlan) -> bool:
        """As the wrapped stage."""
        return self.inner.applies(plan)

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """The wrapped stage's verdict, run under the lock."""
        with ExitStack() as held:
            try:
                wait = seconds_left(self.clock, deadline)
                held.enter_context(self.store.lock(EXEC_LOCK, timeout_s=wait))
            except StateUnavailable:
                if self.store.usable:  # another subagent's mypy or pytest holds it
                    return StageResult(self.name, "skipped", skip_category="timeout")
            return self.inner.run(plan, deadline)


@register_hook_handler(
    "subagent_stop_verify",
    events=["subagent_stop"],
    decisions=["deny", "none"],
    config_schema=CONFIG_SCHEMA,
)
def subagent_stop_verify(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Block an editing subagent's stop while its scoped gate is red (module docstring).

    Example::

        >>> subagent_stop_verify(subagent_stop_after_bad_edit, ctx).decision  # doctest: +SKIP
        <Decision.DENY: 'deny'>
    """
    config = HookConfig(ctx.config, CONFIG_SCHEMA)
    if ev.repo is None or ev.stop is None or not _allowed(ev.agent_type, config):
        return None
    coordinator = StopCoordinator(_policy(ctx, config), StopScope(agent_id=ev.agent_id))
    if ctx.hatches.gate_off:  # the coordinator says so once per session
        return _result(coordinator.run(ev, _deps(ev.repo, ctx, (), frozenset())), ev, ctx)
    try:
        edited = edited_files(ev.stop.agent_transcript_path)
    except TranscriptError:
        return _note(ctx, [TRANSCRIPT_NOTE])
    touched = _repo_paths(edited, ev, ctx)
    if not touched:  # a read-only subagent
        return None
    stages = _scoped_stages(ev, ctx, touched)
    if not stages:
        return _note(ctx, [NO_STAGES_NOTE]) if ctx.session.once("subagent:no-stages") else None
    return _result(coordinator.run(ev, _deps(ev.repo, ctx, stages, touched)), ev, ctx)


def _allowed(agent_type: str | None, config: HookConfig) -> bool:
    """The ``agent_types`` allowlist: no str item (or no list) admits every subagent."""
    allowed = config.strings("agent_types", blanks="keep")
    return not allowed or agent_type in allowed


def _policy(ctx: HandlerContext, config: HookConfig) -> GatePolicy:
    """The parent gate's table (same stage records, same trust digest) with this hook's budget."""
    base = GatePolicy.from_gate(ctx.cfg.tables.stop_gate())
    low, high = MAX_BLOCKS_RANGE
    budget = config.integer(
        "max_blocks", DEFAULT_MAX_BLOCKS, minimum=low, maximum=high, below="clamp", above="clamp"
    )
    return dataclasses.replace(base, max_blocks=budget)


def _repo_paths(edited: tuple[str, ...], ev: CanonicalEvent, ctx: HandlerContext) -> frozenset[str]:
    """The edited paths inside this repository, repo-relative, resolved from the subagent's cwd."""
    found: set[str] = set()
    for raw in edited:
        path = normalize_path(raw, base=ev.cwd, repo=ev.repo, home=ctx.home, platform=ctx.platform)
        if path.repo_rel is not None and not path.sibling_worktree:
            found.add(path.repo_rel)
    return frozenset(found)


def _scoped_stages(
    ev: CanonicalEvent, ctx: HandlerContext, touched: frozenset[str]
) -> tuple[Stage, ...]:
    """The configured stages, built like the parent gate's; lint scoped, exec stages locked."""
    configured = HookConfig(ctx.config, CONFIG_SCHEMA).strings("stages", blanks="keep")
    names = configured or DEFAULT_STAGES  # no str item (or no list) reads as the default
    stages: list[Stage] = []
    for name in dict.fromkeys(n for n in names if n in SCOPED_STAGES):
        stage = build_stage(name, ev, ctx)
        if isinstance(stage, LintStage):
            stage = dataclasses.replace(stage, only=touched)
        if stage is not None and stage.cost is StageCost.EXECUTION:
            stage = ExecLocked(stage, ctx.session.store, ctx.clock)
        if stage is not None:
            stages.append(stage)
    return tuple(stages)


def _deps(
    repo: RepoInfo, ctx: HandlerContext, stages: tuple[Stage, ...], touched: frozenset[str]
) -> CoordinatorDeps:
    return CoordinatorDeps(
        stages=stages,
        timeouts=_timeouts(ctx),
        git=ctx.git,
        store=ctx.session.store,
        session=ctx.session,
        clock=ctx.clock,
        deadline=ctx.deadline - WRITE_MARGIN_S,
        trust=trust_opener(repo, ctx),
        ledger=_ledger(touched),
        gate_off=ctx.hatches.gate_off,
    )


def _timeouts(ctx: HandlerContext) -> dict[str, float]:
    """Each rendered stage record's ``timeout_s``, by stage name (the first record wins)."""
    timeouts: dict[str, float] = {}
    for record in ctx.cfg.tables.stop_gate().stages:
        if record.timeout_s is not None:
            timeouts.setdefault(record.name, record.timeout_s)
    return timeouts


def _ledger(touched: frozenset[str]) -> tuple[Mapping[str, Any], ...]:
    """The subagent's edits as one ledger line, so ledger-reading stages see its scope."""
    if not touched:
        return ()
    cats = ["py"] if any(rel.endswith(".py") for rel in touched) else []
    line = {"v": 1, "ev": "post_tool_use", "tc": "edit", "paths": sorted(touched), "cats": cats}
    return (line,)


def _result(outcome: StopOutcome, ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """The coordinator's verdict, plus the claim contradiction and the HEAD-moved report."""
    claim = completion_claim(ev, ctx.cfg)
    reason, notes = outcome.reason, list(outcome.notes)
    if claim is not None and outcome.deny:
        reason = _with_contradiction(reason, claim)
    elif claim is not None and any("NOT verified" in note for note in notes):
        notes.append(f"The subagent says {quote_data(claim, _CLAIM_CHARS)}, but NOT verified.")
    moved = head_moved_note(ctx.session, ctx.git, ev.session_id)
    if moved is not None:
        notes.append(moved)
    if not outcome.deny and not notes:
        return None
    return HandlerResult(
        decision=Decision.DENY if outcome.deny else Decision.NONE,
        hook_id=ctx.hook.id,
        rule_id=outcome.rule_id,
        reason=reason,
        user_note="\n".join(notes),
    )


def _with_contradiction(reason: str, claim: str) -> str:
    """``reason`` with the contradiction right after its header, still within 40 lines."""
    header, *body = reason.splitlines()
    line = (
        f"[claim] You said {quote_data(claim, _CLAIM_CHARS)}, but the gate is red: "
        "that claim contradicts it."
    )
    return "\n".join([header, line, *body][: OutputCaps.STOP_REASON.max_lines])


def _note(ctx: HandlerContext, notes: list[str]) -> HandlerResult:
    return HandlerResult(
        decision=Decision.NONE,
        hook_id=ctx.hook.id,
        rule_id="not_verified",
        user_note="\n".join(notes),
    )
