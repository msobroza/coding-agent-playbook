"""stop-ci-parity-gate: the dispatcher's one Stop handler, the coordinator (specs/prK-hook-pack.md §E.2).

It plans its own stages (the ``stop_gate.stages`` records it owns: ``lint``,
``verify-claim`` and the opted-in ``typecheck`` / ``tests``) and every
Stop-stage hook bound to the event (``config.stage``), ordered by
``STOP_STAGE_ORDER``, never ``priority``, through :data:`STAGE_FACTORIES`,
then hands them to ``stop.coordinator.StopCoordinator``, which owns the
policy: fingerprint skip, block budget, one combined reason per tree, the
``NOT verified`` rule. The selection never fans the stage hooks out while
this handler is selected (``_selection``).

A stage factory is ``(ev, ctx) -> Stage | None``, imported only when its
stage is planned, and gets a context whose ``hook``/``config`` are the stage
hook's own. On ``subagent_stop`` the chain is the subagent's (``agent_id``);
on OpenCode the gate cannot block, so the red result is returned as is
(§D.5.6). The stage list comes from ``guard_config.stop_gate``, rendered at
sync; nothing here reads a command from an agent-editable file.
"""

from __future__ import annotations

import dataclasses
import importlib
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime._ports import open_trust_store
from coding_agent_playbook.hook_runtime._selection import select_stage_hooks, stage_of
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.event import EventName, Harness
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.stop.coordinator import (
    CoordinatorDeps,
    GatePolicy,
    StopCoordinator,
    StopScope,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.hook_runtime.config import HookRecord
    from coding_agent_playbook.hook_runtime.deps import TrustPort
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, RepoInfo
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.stop.coordinator import StopOutcome
    from coding_agent_playbook.hook_runtime.stop.stages import Stage

    type StageFactory = Callable[[CanonicalEvent, HandlerContext], Stage | None]

__all__ = [
    "CONFIG_SCHEMA",
    "STAGE_FACTORIES",
    "WRITE_MARGIN_S",
    "build_stage",
    "coordinator_deps",
    "stop_ci_parity_gate",
    "trust_opener",
]

#: ``[hooks.stop-ci-parity-gate]`` (§B.1). Sync renders them into ``stop_gate``.
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "stages": ConfigKey("list"),
    "verify_commands": ConfigKey("list"),
    "claim_patterns": ConfigKey("list", "extend"),
    "max_blocks": ConfigKey("integer"),
    "budget_s": ConfigKey("number"),
    "tests_scope": ConfigKey("string", "replace", ("all", "touched")),
}
_HANDLERS: Final = "coding_agent_playbook.hook_runtime.handlers"
#: Stage name -> ``module:function`` building it; a pack track adds a row per stage.
STAGE_FACTORIES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "drift": f"{_HANDLERS}.stop_drift_and_orphan_gate:drift_stage",
        "lint": f"{_HANDLERS}._lint_stage:lint_stage",
        "quality-metrics": f"{_HANDLERS}.quality_metrics:quality_metrics_stage",
        "docstrings": f"{_HANDLERS}.docstring_nonregression:docstrings_stage",
        "gate-integrity": f"{_HANDLERS}.gate_weakening:gate_integrity_stage",
        "secrets": f"{_HANDLERS}.stop_sweep:secrets_stage",
        "verify-claim": f"{_HANDLERS}._verify_claim:verify_claim_stage",
        "output-contract": f"{_HANDLERS}.output_contract:output_contract_stage",
        "tests-nudge": f"{_HANDLERS}.tests_nudge:tests_nudge_stage",
        "typecheck": f"{_HANDLERS}._exec_stages:typecheck_stage",
        "tests": f"{_HANDLERS}._exec_stages:tests_stage",
        "notebooks": f"{_HANDLERS}.notebooks:notebooks_stage",
        "coverage": f"{_HANDLERS}.coverage_diff_gate:coverage_stage",
    }
)
#: Leaves the dispatcher time to compose and write before the watchdog fires.
WRITE_MARGIN_S: Final = 0.25


@register_hook_handler(
    "stop_ci_parity_gate",
    events=["stop", "subagent_stop"],
    decisions=["deny", "none"],
    config_schema=CONFIG_SCHEMA,
)
def stop_ci_parity_gate(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Run the Stop coordinator over the planned stages; one deny per red tree.

    Example::

        >>> stop_ci_parity_gate(stop_after_bad_edit, ctx).reason.splitlines()[0]
        ... # doctest: +SKIP
        'Playbook gate RED — fix before finishing (tree 1a2b3c4d, block 1/2):'
    """
    if ev.repo is None:
        return None
    policy = GatePolicy.from_table(ctx.cfg.tables.get("stop_gate"))
    scope = StopScope(
        agent_id=ev.agent_id if ev.name is EventName.SUBAGENT_STOP else None,
        can_block=ev.harness is not Harness.OPENCODE,
    )
    outcome = StopCoordinator(policy, scope).run(ev, coordinator_deps(ev, ctx, ev.repo))
    return _result(outcome, ctx.hook.id)


def coordinator_deps(ev: CanonicalEvent, ctx: HandlerContext, repo: RepoInfo) -> CoordinatorDeps:
    """The coordinator's view of this dispatch: planned stages, state, git, trust.

    Example: ``StopCoordinator(policy).run(ev, coordinator_deps(ev, ctx, ev.repo))``.
    """
    stages: list[Stage] = []
    timeouts: dict[str, float] = {}
    for name, timeout_s in _own_stages(ctx):  # first: a stage hook never replaces them
        stage = build_stage(name, ev, ctx)
        if stage is not None:
            stages.append(stage)
            timeouts[name] = timeout_s
    for record in select_stage_hooks(ctx.cfg, ev, ctx.hatches):
        stage = _build(record, ev, ctx)
        if stage is not None and stage.name not in timeouts:  # one stage per name: first id wins
            stages.append(stage)
            timeouts[stage.name] = record.timeout_ms / 1000
    return CoordinatorDeps(
        stages=tuple(stages),
        timeouts=timeouts,
        git=ctx.git,
        store=ctx.session.store,
        session=ctx.session,
        clock=ctx.clock,
        deadline=ctx.deadline - WRITE_MARGIN_S,
        trust=trust_opener(repo, ctx),
        ledger=tuple(ctx.ledger.read()) if ctx.ledger is not None else (),
        gate_off=ctx.hatches.gate_off,
    )


def build_stage(name: str, ev: CanonicalEvent, ctx: HandlerContext) -> Stage | None:
    """Stage ``name`` built by its :data:`STAGE_FACTORIES` row with ``ctx``; ``None`` if unknown.

    subagent-stop-verify builds its scoped stage list this way (§D.5.6).
    Example: ``build_stage("lint", ev, ctx).name == "lint"``.
    """
    factory = _factory(name)
    return None if factory is None else factory(ev, ctx)


def _build(record: HookRecord, ev: CanonicalEvent, ctx: HandlerContext) -> Stage | None:
    """The stage ``record`` contributes, from its factory; ``None`` for an unknown stage name."""
    factory = _factory(stage_of(record, ev.name) or "")
    if factory is None:
        return None
    own: Mapping[str, Any] = record.handlers[ev.name].config
    return factory(ev, dataclasses.replace(ctx, hook=record, config=own))


def _factory(stage: str) -> StageFactory | None:
    """Stage ``stage``'s factory, its module imported only now; ``None`` for an unknown name."""
    target = STAGE_FACTORIES.get(stage)
    if target is None:
        return None
    module, _, attr = target.partition(":")
    factory: StageFactory = getattr(importlib.import_module(module), attr)
    return factory


def _own_stages(ctx: HandlerContext) -> list[tuple[str, float]]:
    """``(name, timeout_s)`` of each ``stop_gate.stages`` record this coordinator owns."""
    table = ctx.cfg.tables.get("stop_gate")
    records = table.get("stages") if isinstance(table, dict) else None
    owned: list[tuple[str, float]] = []
    for record in records if isinstance(records, list) else ():
        if not isinstance(record, dict) or record.get("owner") != ctx.hook.id:
            continue
        name, timeout_s = record.get("name"), record.get("timeout_s")
        if isinstance(name, str) and isinstance(timeout_s, int | float) and timeout_s > 0:
            owned.append((name, float(timeout_s)))
    return owned


def trust_opener(repo: RepoInfo, ctx: HandlerContext) -> Callable[[], TrustPort | None]:
    """Opens the user-local trust store only when an execution stage is planned.

    Example: ``CoordinatorDeps(..., trust=trust_opener(ev.repo, ctx))``.
    """

    def opened() -> TrustPort | None:
        return None if ctx.deps is None else open_trust_store(repo, ctx.deps)

    return opened


def _result(outcome: StopOutcome, hook_id: str) -> HandlerResult | None:
    if not outcome.deny and not outcome.notes:
        return None
    return HandlerResult(
        decision=Decision.DENY if outcome.deny else Decision.NONE,
        hook_id=hook_id,
        rule_id=outcome.rule_id,
        reason=outcome.reason,
        user_note="\n".join(outcome.notes),
    )
