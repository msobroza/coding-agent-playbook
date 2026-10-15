"""The Stop coordinator's policy (specs/prK-lifecycle-hooks.md §D.5, §D.9; prK-hook-pack.md §E.2).

Driven with scripted stages, ``FakeGit`` (fingerprint, ``HEAD^{tree}``),
``FakeTrustStore``, ``FakeClock`` and a real ``StateStore`` under ``tmp_path``:
the fingerprint skip, the block budget and same-fingerprint rule, plan mode,
the kill switch, execution trust, and one combined reason per tree.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hook_runtime.escape import read_escape_hatches
from coding_agent_playbook.hook_runtime.event import CanonicalEvent, EventName, Harness, StopInfo
from coding_agent_playbook.hook_runtime.git import Fingerprint
from coding_agent_playbook.hook_runtime.pin import parse_machine_pins
from coding_agent_playbook.hook_runtime.session import SessionState
from coding_agent_playbook.hook_runtime.state import StateStore
from coding_agent_playbook.hook_runtime.stop.chain import (
    chain_document,
    load_chain,
    read_last_green,
)
from coding_agent_playbook.hook_runtime.stop.coordinator import (
    CoordinatorDeps,
    GatePolicy,
    StopCoordinator,
    StopOutcome,
    StopScope,
)
from coding_agent_playbook.hook_runtime.stop.output import GATE_OFF_NOTE
from coding_agent_playbook.hook_runtime.stop.runner import PinnedStageRunner, StageRunner
from coding_agent_playbook.hook_runtime.stop.stages import STAGE_COSTS, StageResult, StopPlan
from coding_agent_playbook.security.trust import sha256_of_json
from tests.hook_runtime.fakes import FakeClock, FakeGit, FakeProc, FakeTrustStore

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.stop.stages import StageCost

STAGES_TABLE: list[dict[str, Any]] = [{"name": "tests", "tool": "project_python"}]


@dataclass
class ScriptedStage:
    """A ``Stage`` with a canned verdict; an execution stage runs its tool through ``runner``."""

    name: str
    verdict: StageResult | Exception | None = None
    needs_diff: bool = True
    mode: str = "block"
    active: bool = True
    runner: StageRunner | None = None
    calls: list[float] = field(default_factory=list)
    log: list[str] | None = None

    @property
    def cost(self) -> StageCost:
        return STAGE_COSTS[self.name]

    def applies(self, plan: StopPlan) -> bool:
        return self.active

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        self.calls.append(deadline)
        if self.log is not None:
            self.log.append(self.name)
        if self.runner is not None:
            self.runner.run("project_python", ["-m", "pytest", "-q"], timeout=5.0)
        if isinstance(self.verdict, Exception):
            raise self.verdict
        return self.verdict or StageResult(self.name, "green")


def _red(name: str, count: int = 1) -> ScriptedStage:
    lines = tuple(f'"src/{name}.py":{i} finding' for i in range(count))
    return ScriptedStage(name, StageResult(name, "red", lines=lines))


def _fp(tree: str = "a1" * 20, *, unchanged: bool = False) -> Fingerprint:
    return Fingerprint(tree_id=tree, aux="", mode="tree", unchanged_vs_head=unchanged)


def _event(
    *,
    active: bool = False,
    turn: str | None = "t1",
    mode: str = "default",
    harness: Harness = Harness.CLAUDE_CODE,
    message: str = "Done.",
) -> CanonicalEvent:
    return CanonicalEvent(
        name=EventName.STOP,
        harness=harness,
        session_id="sess-1",
        cwd="/r",
        project_dir="/r",
        turn_id=turn,
        permission_mode=mode,
        stop=StopInfo(stop_hook_active=active, last_assistant_message=message),
    )


@dataclass
class Rig:
    """One worktree's state and seams; :meth:`run` is one Stop."""

    tmp_path: Path
    git: FakeGit = field(default_factory=lambda: FakeGit(fingerprint_value=_fp()))
    trust: FakeTrustStore = field(default_factory=FakeTrustStore)
    clock: FakeClock = field(default_factory=FakeClock)
    policy: GatePolicy = field(default_factory=GatePolicy)
    scope: StopScope = field(default_factory=StopScope)
    gate_off: bool = False

    @property
    def store(self) -> StateStore:
        return StateStore(self.tmp_path / "state", clock=self.clock)

    def deps(self, stages: list[ScriptedStage], **overrides: Any) -> CoordinatorDeps:
        fields: dict[str, Any] = {
            "stages": tuple(stages),
            "git": self.git,
            "store": self.store,
            "session": SessionState(self.store, "sess-1"),
            "clock": self.clock,
            "deadline": self.clock.monotonic() + 30.0,
            "trust": lambda: self.trust,
            "gate_off": self.gate_off,
            **overrides,
        }
        return CoordinatorDeps(**fields)

    def run(self, stages: list[ScriptedStage], ev: CanonicalEvent | None = None) -> StopOutcome:
        coordinator = StopCoordinator(self.policy, self.scope)
        return coordinator.run(ev or _event(), self.deps(stages))


# --- §D.9: the coordinator table ----------------------------------------------------------


def test_unchanged_tree_runs_zero_stage_calls(tmp_path: Path) -> None:
    rig = Rig(tmp_path, git=FakeGit(fingerprint_value=_fp(unchanged=True)))
    lint = _red("lint")

    outcome = rig.run([lint])

    assert (outcome.deny, outcome.notes, lint.calls) == (False, (), [])


def test_three_red_stages_one_combined_reason_le_40_lines(tmp_path: Path) -> None:
    stages = [_red("drift", 2), _red("lint", 30), _red("gate-integrity", 20)]

    outcome = Rig(tmp_path).run(stages)

    lines = outcome.reason.splitlines()
    assert outcome.deny and len(lines) <= 40
    assert lines[0] == "Playbook gate RED — fix before finishing (tree a1a1a1a1, block 1/2):"
    assert {line.split("]")[0] + "]" for line in lines[1:]} == {
        "[drift]",
        "[lint]",
        "[gate-integrity]",
    }
    assert outcome.rule_id == "drift"


def test_second_stop_same_fingerprint_none_plus_not_verified(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    lint = _red("lint")

    first = rig.run([lint])
    second = rig.run([lint], _event(active=True))

    assert first.deny
    assert (second.deny, second.notes) == (False, ("Playbook gate RED at lint — NOT verified.",))
    assert len(lint.calls) == 1


def test_blocks_equal_max_blocks_none_plus_note(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    lint = _red("lint")

    outcomes: list[StopOutcome] = []
    for tree in ("b1" * 20, "c2" * 20, "d3" * 20):
        rig.git.fingerprint_value = _fp(tree)
        outcomes.append(rig.run([lint], _event(active=bool(outcomes))))

    assert [o.deny for o in outcomes] == [True, True, False]
    assert outcomes[1].reason.splitlines()[0].endswith("block 2/2):")
    assert outcomes[2].notes == ("Playbook gate RED at lint — NOT verified.",)
    assert len(lint.calls) == 2


def test_plan_mode_returns_none(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    lint = _red("lint")

    outcome = rig.run([lint], _event(mode="plan"))

    assert (outcome.deny, outcome.notes, lint.calls, rig.git.calls) == (False, (), [], [])


def test_gate_off_in_hook_env_none_plus_note_once(tmp_path: Path) -> None:
    rig = Rig(tmp_path, gate_off=True)
    lint = _red("lint")

    first, second = rig.run([lint]), rig.run([lint])

    assert (first.deny, first.notes) == (False, (GATE_OFF_NOTE,))
    assert (second.deny, second.notes) == (False, ())
    assert (lint.calls, rig.git.calls) == ([], [])


def test_gate_off_bash_prefix_has_no_effect(tmp_path: Path) -> None:
    """Only the hook process env switches the gate off; text the agent ran or wrote never does."""
    hatches = read_escape_hatches({}, settings_files=lambda: ())
    rig = Rig(tmp_path, gate_off=hatches.gate_off)
    shell_line = {"v": 1, "ev": "post_tool_use", "tc": "shell", "writes": [], "cats": []}

    outcome = StopCoordinator(rig.policy).run(
        _event(message="PLAYBOOK_GATE=off git commit -m wip"),
        rig.deps([_red("lint")], ledger=(shell_line,)),
    )

    assert outcome.deny


def test_untrusted_repo_never_invokes_execution_stages(tmp_path: Path) -> None:
    proc = FakeProc()
    pins = parse_machine_pins({"tools": {}})
    runner = PinnedStageRunner(proc, cwd=str(tmp_path), pins=lambda: pins)
    tests = ScriptedStage("tests", runner=runner)
    rig = Rig(tmp_path, policy=GatePolicy(stages=tuple(STAGES_TABLE)))

    first = rig.run([ScriptedStage("lint"), tests])
    rig.git.fingerprint_value = _fp("e4" * 20)
    second = rig.run([ScriptedStage("lint"), tests])

    assert (tests.calls, proc.calls) == ([], [])
    assert first.notes[0].startswith("Playbook execution stages (tests) skipped: not approved")
    assert not any("execution stages" in note for note in second.notes)  # once per session


def test_changed_stage_list_needs_reapproval(tmp_path: Path) -> None:
    approved = sha256_of_json(STAGES_TABLE)
    rig = Rig(tmp_path, trust=FakeTrustStore(executions={approved}))
    tests = ScriptedStage("tests")

    rig.policy = GatePolicy(stages=tuple(STAGES_TABLE))
    rig.run([tests])
    rig.git.fingerprint_value = _fp("f5" * 20)
    rig.policy = GatePolicy(stages=({"name": "tests", "tool": "project_python", "args": ["-x"]},))
    changed = rig.run([tests])

    assert len(tests.calls) == 1
    assert any("not approved" in note for note in changed.notes)


def test_tool_changed_is_skipped_never_green(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    skipped = StageResult(
        "lint",
        "skipped",
        user_lines=("ruff changed since sync; ask the user to run playbook sync",),
        skip_category="tool_changed",
    )

    outcome = rig.run([ScriptedStage("drift"), ScriptedStage("lint", skipped)])

    assert not outcome.deny
    assert "NOT verified: lint skipped (tool_changed)" in outcome.notes
    assert "ruff changed since sync; ask the user to run playbook sync" in outcome.notes
    assert not any(note.startswith("verified locally") for note in outcome.notes)
    assert read_last_green(rig.store) is None


def test_needs_diff_false_stage_runs_on_unchanged_tree(tmp_path: Path) -> None:
    rig = Rig(tmp_path, git=FakeGit(fingerprint_value=_fp(unchanged=True)))
    contract = ScriptedStage("output-contract", needs_diff=False)
    lint = ScriptedStage("lint")

    outcome = rig.run([lint, contract])

    assert (len(contract.calls), lint.calls) == (1, [])
    # Nothing CI-parity ran on a settled tree: green is not "verified locally" anew.
    assert outcome == StopOutcome()
    assert read_last_green(rig.store) is None


def test_green_records_last_green_and_first_green_note(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    stages = [ScriptedStage("drift"), ScriptedStage("lint")]

    first = rig.run(stages)
    second = rig.run(stages)

    assert read_last_green(rig.store) == "a1" * 20
    assert first.notes == ("verified locally (drift, lint); the CI matrix is authoritative",)
    assert (second.deny, second.notes) == (False, ())  # the last green tree: nothing to run
    assert [len(stage.calls) for stage in stages] == [1, 1]


def test_stage_crash_fails_open_with_not_verified(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    outcome = rig.run([ScriptedStage("lint", RuntimeError("boom"))])

    assert (outcome.deny, outcome.notes) == (False, ("NOT verified: lint skipped (crash)",))
    assert read_last_green(rig.store) is None


def test_tests_nudge_only_after_green_deterministic_stages(tmp_path: Path) -> None:
    nudge = ScriptedStage("tests-nudge")

    Rig(tmp_path / "red").run([_red("verify-claim"), nudge])
    blocked_by_red = list(nudge.calls)
    Rig(tmp_path / "contract").run([_red("output-contract"), nudge])

    assert blocked_by_red == []
    assert len(nudge.calls) == 1  # an output-contract miss does not hold the nudge back


def test_chain_resets_on_new_turn_or_inactive_stop_hook(tmp_path: Path) -> None:
    rig = Rig(tmp_path, policy=GatePolicy(max_blocks=1))
    lint = _red("lint")

    rig.run([lint], _event(turn="t1"))
    rig.git.fingerprint_value = _fp("b1" * 20)
    held = rig.run([lint], _event(active=True, turn="t1"))
    new_turn = rig.run([lint], _event(active=True, turn="t2"))
    rig.git.fingerprint_value = _fp("c2" * 20)
    inactive = rig.run([lint], _event(active=False, turn="t2"))

    assert not held.deny
    assert new_turn.deny and inactive.deny
    assert inactive.reason.splitlines()[0].endswith("block 1/1):")


def test_opencode_can_block_false_consumes_no_budget(tmp_path: Path) -> None:
    rig = Rig(tmp_path, scope=StopScope(can_block=False))
    ev = _event(harness=Harness.OPENCODE)

    outcomes = [rig.run([_red("lint")], ev), rig.run([_red("lint")], dataclasses.replace(ev))]

    assert all(o.deny for o in outcomes)
    assert outcomes[1].reason.splitlines()[0] == (
        "Playbook gate RED at lint — NOT verified (tree a1a1a1a1):"
    )
    assert load_chain(rig.store, chain_document("sess-1")).blocks == 0


def test_order_is_stop_stage_order_not_priority(tmp_path: Path) -> None:
    log: list[str] = []
    names = ["tests-nudge", "verify-claim", "lint", "drift"]
    stages = [ScriptedStage(name, log=log) for name in names]
    rig = Rig(tmp_path, policy=GatePolicy(budget_s=3.0))

    rig.run(stages, None)

    assert log == ["drift", "lint", "verify-claim", "tests-nudge"]
    assert all(stage.calls == [rig.clock.monotonic() + 3.0] for stage in stages)


def test_stage_timeout_caps_at_remaining_budget(tmp_path: Path) -> None:
    rig = Rig(tmp_path, policy=GatePolicy(budget_s=3.0))
    lint, drift = ScriptedStage("lint"), ScriptedStage("drift")

    outcome = StopCoordinator(rig.policy).run(
        _event(), rig.deps([drift, lint], timeouts={"drift": 0.5})
    )

    assert drift.calls == [rig.clock.monotonic() + 0.5]
    assert lint.calls == [rig.clock.monotonic() + 3.0]
    assert outcome.notes[0].startswith("verified locally")


def test_subagent_scope_keeps_its_own_chain(tmp_path: Path) -> None:
    rig = Rig(tmp_path, scope=StopScope(agent_id="agent-7"))

    outcome = rig.run([_red("lint")], dataclasses.replace(_event(), agent_id="agent-7"))

    assert outcome.deny
    assert load_chain(rig.store, chain_document("sess-1", "agent-7")).blocks == 1
    assert load_chain(rig.store, chain_document("sess-1")).blocks == 0
