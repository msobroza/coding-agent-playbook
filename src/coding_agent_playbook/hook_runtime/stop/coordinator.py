"""The Stop coordinator's policy (specs/prK-lifecycle-hooks.md §D.5.1, §D.5.2, §D.5.5, §D.5.6).

stop-ci-parity-gate owns it; every other Stop hook is a stage it plans. One
:meth:`StopCoordinator.run`:

1. ``PLAYBOOK_GATE=off`` (hook process env only) lets the Stop through with
   one note per session; ``permission_mode == "plan"`` is silent;
2. the stop chain is loaded (§D.5.1: reset on a new turn or an inactive
   ``stop_hook_active``) and the working tree fingerprinted. When the tree
   equals ``HEAD^{tree}`` or the last green tree, only ``needs_diff=False``
   stages remain; with nothing applicable the Stop is silent;
3. a chain at ``max_blocks``, or a tree unchanged since its last block, lets
   the Stop through with ``Playbook gate RED at <stage> — NOT verified.``;
4. deterministic stages run in ``STOP_STAGE_ORDER`` within ``budget_s``
   (``tests-nudge`` only when ``drift``..``verify-claim`` are not red); the
   execution stages only when nothing is red **and** the user approved this
   exact stage list (§B.4);
5. any red gives **one** deny with the combined reason (§D.5.4); all green
   records the tree as last green (a tree that was already settled ran no
   diff stage, so it gets no new "verified locally" note). A skipped stage is
   ``NOT verified``, never green, and every stage failure fails open.

``StopScope(can_block=False)`` (OpenCode, whose ``session.idle`` cannot
block) returns the red result without spending budget; an ``agent_id`` scope
keeps a subagent's chain apart (§D.5.6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.stop import chain as chains
from coding_agent_playbook.hook_runtime.stop.output import (
    GATE_OFF_NOTE,
    compose_reason,
    green_note,
    not_verified_note,
    red_note,
    untrusted_note,
)
from coding_agent_playbook.hook_runtime.stop.stages import (
    DEFAULT_BUDGET_S,
    STOP_STAGE_ORDER,
    StageResult,
    StopPlan,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.deps import Clock, TrustPort
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.git.safe_git import Fingerprint, GitPort
    from coding_agent_playbook.hook_runtime.session import SessionState
    from coding_agent_playbook.hook_runtime.state import StateStore
    from coding_agent_playbook.hook_runtime.stop.chain import StopChain
    from coding_agent_playbook.hook_runtime.stop.stages import SkipCategory, Stage

__all__ = [
    "DEFAULT_MAX_BLOCKS",
    "CoordinatorDeps",
    "GatePolicy",
    "StopCoordinator",
    "StopOutcome",
    "StopScope",
]

#: ``[hooks.stop-ci-parity-gate] max_blocks`` default and range (§B.1).
DEFAULT_MAX_BLOCKS: Final = 2
_MAX_BLOCKS_RANGE: Final = (1, 8)
#: tests-nudge runs only when no stage up to this one is red (§E.0.4: stages 0-7).
_NUDGE: Final = "tests-nudge"
_NUDGE_GATE: Final = STOP_STAGE_ORDER.index("verify-claim")


@dataclass(frozen=True, slots=True, kw_only=True)
class GatePolicy:
    """``guard_config.stop_gate``'s runtime knobs; ``stages`` are its rendered records.

    The records are what an execution approval hashes (§B.4), so any change
    to the stage list needs re-approval.

    Example::

        >>> GatePolicy.from_table({"max_blocks": 99}).max_blocks
        8
    """

    budget_s: float = DEFAULT_BUDGET_S
    max_blocks: int = DEFAULT_MAX_BLOCKS
    stages: tuple[Any, ...] = ()

    @classmethod
    def from_table(cls, table: object) -> GatePolicy:
        """The policy of a rendered ``stop_gate`` table; anything malformed is its default."""
        if not isinstance(table, dict):
            return cls()
        blocks, stages = table.get("max_blocks"), table.get("stages")
        low, high = _MAX_BLOCKS_RANGE
        return cls(
            budget_s=_budget(table.get("budget_s")),
            max_blocks=min(high, max(low, blocks)) if type(blocks) is int else DEFAULT_MAX_BLOCKS,
            stages=tuple(stages) if isinstance(stages, list) else (),
        )

    def stages_sha256(self) -> str:
        """The digest an execution approval must match (``security.trust.sha256_of_json``)."""
        from coding_agent_playbook.security.trust import sha256_of_json  # only for exec stages

        return sha256_of_json(list(self.stages))


@dataclass(frozen=True, slots=True)
class StopScope:
    """Whose stop chain this is: the session's (``agent_id=None``) or one subagent's.

    ``can_block=False`` (OpenCode) reports a red gate without spending budget.
    """

    agent_id: str | None = None
    can_block: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class CoordinatorDeps:
    """What one Stop may use: its planned stages and the dispatch's seams.

    ``deadline`` is the latest ``clock.monotonic()`` any stage may run to;
    ``timeouts`` the per-stage cap in seconds (default: the remaining budget);
    ``trust`` opens the user-local store, only when an execution stage is
    planned; ``gate_off`` is ``PLAYBOOK_GATE=off`` from the hook process env.
    """

    stages: tuple[Stage, ...]
    git: GitPort
    store: StateStore
    session: SessionState
    clock: Clock
    deadline: float
    trust: Callable[[], TrustPort | None]
    ledger: tuple[Mapping[str, Any], ...] = ()
    timeouts: Mapping[str, float] = field(default_factory=dict)
    gate_off: bool = False


@dataclass(frozen=True, slots=True)
class StopOutcome:
    """The coordinator's verdict: a deny with the combined reason, or notes only.

    ``rule_id`` names the first red stage, or why a red gate was let through.
    """

    deny: bool = False
    reason: str = ""
    notes: tuple[str, ...] = ()
    rule_id: str = ""


@dataclass(frozen=True, slots=True)
class _Stop:
    """One Stop's context while its results are composed."""

    deps: CoordinatorDeps
    chain: StopChain
    document: str
    fingerprint: Fingerprint | None
    settled: bool = False  # the tree is HEAD's or the last green one: no diff stage ran

    @property
    def tree(self) -> str | None:
        return None if self.fingerprint is None else self.fingerprint.key


class StopCoordinator:
    """The policy of one Stop under ``policy``, for ``scope``.

    Example::

        >>> StopCoordinator(GatePolicy()).run(stop_event, deps).deny  # doctest: +SKIP
        True
    """

    def __init__(self, policy: GatePolicy, scope: StopScope | None = None) -> None:
        self.policy = policy
        self.scope = scope or StopScope()

    def run(self, ev: CanonicalEvent, deps: CoordinatorDeps) -> StopOutcome:
        """Plan, budget-check, run and compose one Stop (module docstring)."""
        if deps.gate_off:
            first = deps.session.once("stop:gate_off")
            return StopOutcome(notes=(GATE_OFF_NOTE,) if first else (), rule_id="gate_off")
        if ev.permission_mode == "plan":
            return StopOutcome()
        document = chains.chain_document(ev.session_id, self.scope.agent_id)
        chain = chains.load_chain(deps.store, document).for_event(ev)
        fingerprint = _quiet(deps.git.fingerprint)
        settled = fingerprint is not None and _settled(fingerprint, deps.store)
        plan = self._plan(ev, deps, fingerprint, settled=settled)
        if not plan.stages:
            return StopOutcome()
        held = self._held(chain, fingerprint)
        if held is not None:
            return held
        results = self._run_stages(plan, deps)
        return self._compose(results, _Stop(deps, chain, document, fingerprint, settled))

    def _plan(
        self,
        ev: CanonicalEvent,
        deps: CoordinatorDeps,
        fingerprint: Fingerprint | None,
        *,
        settled: bool,
    ) -> StopPlan:
        plan = StopPlan(
            event=ev,
            stages=deps.stages,
            fingerprint=fingerprint,
            ledger=deps.ledger,
            budget_s=self.policy.budget_s,
        )
        if settled:
            plan = plan.only(needs_diff=False)
        applicable = tuple(stage for stage in plan.stages if _applies(stage, plan))
        head = _quiet(deps.git.head_tree) if applicable else None
        return StopPlan(
            event=ev,
            stages=applicable,
            fingerprint=fingerprint,
            head_tree=head,
            ledger=deps.ledger,
            budget_s=self.policy.budget_s,
        )

    def _held(self, chain: StopChain, fingerprint: Fingerprint | None) -> StopOutcome | None:
        """A red gate let through: the block budget is spent, or the tree has not changed."""
        if not self.scope.can_block:
            return None
        if chain.blocks >= self.policy.max_blocks:
            return StopOutcome(notes=(red_note(chain.last_stage),), rule_id="budget_exhausted")
        if fingerprint is not None and fingerprint.key == chain.last_blocked_fp:
            return StopOutcome(notes=(red_note(chain.last_stage),), rule_id="unchanged")
        return None

    def _run_stages(self, plan: StopPlan, deps: CoordinatorDeps) -> list[StageResult]:
        end = min(deps.clock.monotonic() + self.policy.budget_s, deps.deadline)
        results: list[StageResult] = []
        for stage in plan.deterministic:
            if stage.name == _NUDGE and _red_through_verify_claim(results):
                continue
            results.append(_run_one(stage, plan, deps, end))
        if plan.execution and not any(r.status == "red" for r in results):
            results.extend(self._run_execution(plan, deps))
        return results

    def _run_execution(self, plan: StopPlan, deps: CoordinatorDeps) -> list[StageResult]:
        """The execution stages, only with the user's approval of this exact stage list."""
        trust = deps.trust()
        if trust is None or not trust.allows_execution(self.policy.stages_sha256()):
            return [_skipped(stage.name, "untrusted") for stage in plan.execution]
        return [_run_one(stage, plan, deps, deps.deadline) for stage in plan.execution]

    def _compose(self, results: list[StageResult], stop: _Stop) -> StopOutcome:
        notes = _notes(results, stop.deps.session)
        red = [r for r in results if r.status == "red"]
        if red:
            return self._block(red, results, stop, notes)
        notes.extend(
            f"[{r.stage}] {line}" for r in results if r.status == "warn" for line in r.lines
        )
        # A settled tree ran no CI-parity stage, so it is not "verified locally" anew.
        if stop.fingerprint is not None and not stop.settled and all(map(_counts_green, results)):
            notes.extend(self._record_green(results, stop.fingerprint, stop.deps))
        return StopOutcome(notes=tuple(notes))

    def _block(
        self, red: list[StageResult], results: list[StageResult], stop: _Stop, notes: list[str]
    ) -> StopOutcome:
        warn = [r for r in results if r.status == "warn"]
        stage = red[0].stage
        if not self.scope.can_block:
            reason = compose_reason(red, warn, tree=stop.tree, block_no=None, max_blocks=0)
            return StopOutcome(deny=True, reason=reason, notes=tuple(notes), rule_id=stage)
        blocked = stop.chain.blocked(stop.tree, stage)
        if not chains.save_chain(stop.deps.store, stop.document, blocked):
            # Stateless: a budget that cannot be counted could block forever (§D.4).
            return StopOutcome(notes=(*notes, red_note(stage)), rule_id=stage)
        reason = compose_reason(
            red, warn, tree=stop.tree, block_no=blocked.blocks, max_blocks=self.policy.max_blocks
        )
        return StopOutcome(deny=True, reason=reason, notes=tuple(notes), rule_id=stage)

    def _record_green(
        self, results: list[StageResult], fingerprint: Fingerprint, deps: CoordinatorDeps
    ) -> list[str]:
        """Remember the green tree (worktree-level: never from a subagent's scoped stage list)."""
        if self.scope.agent_id is None:
            chains.write_last_green(deps.store, fingerprint.key)
        if not deps.session.once(f"stop:green:{fingerprint.key}"):
            return []
        return [green_note(r.stage for r in results if r.verified)]


def _run_one(stage: Stage, plan: StopPlan, deps: CoordinatorDeps, end: float) -> StageResult:
    """One stage under ``min(its timeout, end)``; any failure is a skip, never green."""
    now = deps.clock.monotonic()
    limit = min(end, now + deps.timeouts.get(stage.name, end - now))
    if limit <= now:
        return _skipped(stage.name, "timeout")
    try:
        result = stage.run(plan, limit)
    except Exception:  # a stage that failed fails open, NOT verified (§E.0.5)
        return _skipped(stage.name, "crash")
    if not isinstance(result, StageResult) or result.stage != stage.name:
        return _skipped(stage.name, "crash")
    return result


def _notes(results: Sequence[StageResult], session: SessionState) -> list[str]:
    """User lines, then ``NOT verified`` per skip; the untrusted note once per session."""
    notes = [line for r in results for line in r.user_lines]
    notes.extend(
        not_verified_note(r) for r in results if r.status == "skipped" and not _untrusted(r)
    )
    untrusted = [r.stage for r in results if _untrusted(r)]
    if untrusted and session.once("stop:untrusted"):
        notes.append(untrusted_note(untrusted))
    return notes


def _red_through_verify_claim(results: Sequence[StageResult]) -> bool:
    return any(
        r.status == "red" and STOP_STAGE_ORDER.index(r.stage) <= _NUDGE_GATE for r in results
    )


def _counts_green(result: StageResult) -> bool:
    """Green or warn; an unapproved execution stage is opt-in, so it does not withhold green."""
    return result.verified or _untrusted(result)


def _untrusted(result: StageResult) -> bool:
    return result.skip_category == "untrusted"


def _settled(fingerprint: Fingerprint, store: StateStore) -> bool:
    """The tree is ``HEAD^{tree}`` or the last green one: diff-based stages have nothing new."""
    return fingerprint.unchanged_vs_head or fingerprint.key == chains.read_last_green(store)


def _applies(stage: Stage, plan: StopPlan) -> bool:
    try:
        return stage.applies(plan)
    except Exception:  # let it run: its own failure then reads NOT verified, never silence
        return True


def _quiet[T](read: Callable[[], T]) -> T | None:
    """``read()``, or ``None`` on any git failure: the fingerprint is then unknown (§D.5.3)."""
    try:
        return read()
    except Exception:
        return None


def _skipped(stage: str, category: SkipCategory) -> StageResult:
    return StageResult(stage, "skipped", skip_category=category)


def _budget(value: object) -> float:
    """A positive ``budget_s``, else the default (the runtime re-checks: §D.1 bars sync code)."""
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return DEFAULT_BUDGET_S
    return float(value)
