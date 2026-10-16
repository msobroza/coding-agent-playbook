"""subagent-stop-verify: the coordinator engine, scoped to one subagent (specs/prK-hook-pack.md §E.2, §D.5.6).

Each case runs ``playbook-hook simulate subagent_stop`` with the golden Claude
``SubagentStop`` payload relocated into a :class:`PackRepo` whose stop gate
and this hook are on. ``agent_transcript_path`` points at a JSONL file the
test writes (the subagent's tool inputs); ``FakeStageRunner`` stands in for
ruff and ``FakeGit`` for the fingerprint.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime._head_snapshot import HeadSnapshot, head_snapshot_doc
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.handlers.subagent_verify import (
    EXEC_LOCK,
    NO_STAGES_NOTE,
    TRANSCRIPT_NOTE,
    ExecLocked,
)
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME, StateStore
from coding_agent_playbook.hook_runtime.stop.stages import StageResult
from tests.hook_payloads import load_hook_payload
from tests.hook_runtime.fakes import FakeClock, FakeStageRunner, FakeTrustStore
from tests.hooks.stop_kit import changed_git, ruff_row, script_ruff

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from coding_agent_playbook.hook_runtime.stop.stages import StopPlan
    from tests.hook_payloads import HookPayloadCase
    from tests.hook_runtime.fakes import FakeGit
    from tests.hooks.pack_repo import PackRepo

    type Payload = Callable[[str, str, str], HookPayloadCase]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "subagent-stop-verify"
GATE_ID: Final = "stop-ci-parity-gate"
F401: Final = ruff_row("a.py", "F401", "`os` imported but unused", 1)
RED_NOTE: Final = "Playbook gate RED at lint — NOT verified."


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.write("a.py", "import os\n")
    pack_repo.write("b.py", "import sys\n")
    pack_repo.install_pack([GATE_ID, HOOK_ID])
    return pack_repo


def _tool_use(name: str, **tool_input: Any) -> dict[str, Any]:
    block = {"type": "tool_use", "id": f"toolu_{name}", "name": name, "input": tool_input}
    return {"type": "assistant", "message": {"role": "assistant", "content": [block]}}


def _transcript(tmp_path: Path, records: Iterable[dict[str, Any]]) -> Path:
    path = tmp_path / "agent_42.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), "utf-8")
    return path


def _edits(repo: PackRepo, tmp_path: Path, *rels: str) -> Path:
    head = {"type": "user", "message": {"role": "user", "content": "Fix the parser."}}
    uses = [_tool_use("Read", file_path=str(repo.root / "b.py"))]
    uses += [
        _tool_use("Edit", file_path=str(repo.root / rel), old_string="a", new_string="b")
        for rel in rels
    ]
    return _transcript(tmp_path, [head, *uses])


def _payload(
    repo: PackRepo,
    transcript: Path,
    *,
    message: str = "Fixed the parser.",
    active: bool = False,
    agent_type: str = "code-reviewer",
) -> bytes:
    body = json.loads(repo.relocate(load_hook_payload("claude_code", "subagent_stop", "verify")))
    body.update(
        agent_transcript_path=str(transcript),
        last_assistant_message=message,
        stop_hook_active=active,
        agent_type=agent_type,
    )
    return json.dumps(body).encode("utf-8")


def _ruff(*rows: dict[str, Any]) -> FakeStageRunner:
    runner = FakeStageRunner()
    script_ruff(runner, worktree=rows)
    return runner


def _verify(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    payload: bytes,
    state: Path,
    *,
    runner: FakeStageRunner,
    git: FakeGit | None = None,
) -> SimulateReport:
    runtime = deps(git=git or changed_git(), stage_runner=runner, trust=FakeTrustStore())
    return repo.simulate(payload, runtime, event=EventName.SUBAGENT_STOP, state=state)


def test_edit_on_a_py_with_ruff_error_denies(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    payload = _payload(repo, _edits(repo, tmp_path, "a.py"))

    report = _verify(repo, deps, payload, tmp_path / "state", runner=_ruff(F401))

    assert report.trace.combined.decision is Decision.DENY
    assert report.trace.combined.reason.splitlines()[1:] == [
        '[lint] "a.py":1 F401 `os` imported but unused'
    ]
    assert json.loads(report.trace.wire.stdout)["decision"] == "block"


def test_error_only_in_untouched_b_py_none(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    payload = _payload(repo, _edits(repo, tmp_path, "a.py"))
    b_error = ruff_row("b.py", "F401", "`sys` imported but unused", 1)

    report = _verify(repo, deps, payload, tmp_path / "state", runner=_ruff(b_error))

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.reason == ""


def test_read_only_transcript_skipped(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    transcript = _transcript(tmp_path, [_tool_use("Read", file_path=str(repo.root / "a.py"))])
    runner = _ruff(F401)

    report = _verify(repo, deps, _payload(repo, transcript), tmp_path / "state", runner=runner)

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.user_notes == ()
    assert runner.calls == []


def test_third_stop_none_plus_note(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    transcript, state = _edits(repo, tmp_path, "a.py"), tmp_path / "state"
    trees = ("a1" * 20, "b2" * 20, "c3" * 20)  # the subagent changes the tree each time

    reports = [
        _verify(
            repo,
            deps,
            _payload(repo, transcript, active=n > 0),
            state,
            runner=_ruff(F401),
            git=changed_git(tree),
        )
        for n, tree in enumerate(trees)
    ]

    decisions = [r.trace.combined.decision for r in reports]
    assert decisions == [Decision.DENY, Decision.DENY, Decision.NONE]
    assert "block 2/2" in reports[1].trace.combined.reason.splitlines()[0]
    assert reports[2].trace.combined.user_notes == (RED_NOTE,)


def test_agent_type_outside_allowlist_not_dispatched(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    pack_repo.write("a.py", "import os\n")
    pack_repo.install_pack([GATE_ID, HOOK_ID], per_hook={HOOK_ID: {"agent_types": ["implementer"]}})
    transcript = _edits(pack_repo, tmp_path, "a.py")
    runner = _ruff(F401)

    outside = _verify(
        pack_repo, deps, _payload(pack_repo, transcript), tmp_path / "s1", runner=runner
    )
    inside = _verify(
        pack_repo,
        deps,
        _payload(pack_repo, transcript, agent_type="implementer"),
        tmp_path / "s2",
        runner=_ruff(F401),
    )

    assert (outside.trace.combined.decision, runner.calls) == (Decision.NONE, [])
    assert inside.trace.combined.decision is Decision.DENY


@pytest.mark.parametrize("text", ["not json\n", '{"type": "assistant"}\n[1, 2]\n'])
def test_unparseable_transcript_fails_open_not_verified(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path, text: str
) -> None:
    transcript = tmp_path / "agent_42.jsonl"
    transcript.write_text(text, "utf-8")
    runner = _ruff(F401)

    report = _verify(repo, deps, _payload(repo, transcript), tmp_path / "state", runner=runner)

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.user_notes == (TRANSCRIPT_NOTE,)
    assert runner.calls == []


def test_missing_transcript_fails_open_not_verified(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    payload = _payload(repo, tmp_path / "gone.jsonl")

    report = _verify(repo, deps, payload, tmp_path / "state", runner=_ruff(F401))

    assert report.trace.combined.user_notes == (TRANSCRIPT_NOTE,)


def test_success_claim_while_red_names_contradiction(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    payload = _payload(repo, _edits(repo, tmp_path, "a.py"), message="All done: tests pass.")

    report = _verify(repo, deps, payload, tmp_path / "state", runner=_ruff(F401))

    lines = report.trace.combined.reason.splitlines()
    assert report.trace.combined.decision is Decision.DENY
    assert lines[1] == (
        '[claim] You said "tests pass", but the gate is red: that claim contradicts it.'
    )
    assert lines[2] == '[lint] "a.py":1 F401 `os` imported but unused'


def test_head_moved_since_session_start_reported_once(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    payload, state = _payload(repo, _edits(repo, tmp_path, "a.py")), tmp_path / "state"
    session_id = json.loads(payload)["session_id"]
    snapshot = state / STATE_DIR_NAME / head_snapshot_doc(session_id)
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(json.dumps(HeadSnapshot("main", "ab" * 20).to_json()), "utf-8")
    git = changed_git(commits={"main": "cd" * 20})

    first = _verify(repo, deps, payload, state, runner=_ruff(), git=git)
    again = _verify(repo, deps, payload, state, runner=_ruff(), git=git)

    moved = 'Default branch "main" moved during this session (abababab -> cdcdcdcd)'
    assert any(note.startswith(moved) for note in first.trace.combined.user_notes)
    assert not any(note.startswith(moved) for note in again.trace.combined.user_notes)


def test_no_head_snapshot_no_report(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    git = changed_git(commits={"main": "cd" * 20})

    _verify(
        repo,
        deps,
        _payload(repo, _edits(repo, tmp_path, "a.py")),
        tmp_path / "s",
        runner=_ruff(),
        git=git,
    )

    assert not any(method == "rev_commit" for method, _ in git.calls)


def test_gate_off_says_so_once_and_reads_no_transcript(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    payload, state = _payload(repo, tmp_path / "never-read.jsonl"), tmp_path / "state"
    runtime = deps(git=changed_git(), stage_runner=_ruff(F401), env={"PLAYBOOK_GATE": "off"})

    first = repo.simulate(payload, runtime, event=EventName.SUBAGENT_STOP, state=state)
    second = repo.simulate(payload, runtime, event=EventName.SUBAGENT_STOP, state=state)

    assert first.trace.combined.decision is Decision.NONE
    assert first.trace.combined.user_notes == (
        "Playbook stop gate disabled (PLAYBOOK_GATE=off): work NOT verified.",
    )
    assert second.trace.combined.user_notes == ()


def test_without_the_stop_gate_records_not_verified_once(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    pack_repo.write("a.py", "import os\n")
    pack_repo.install_pack([HOOK_ID])  # stop-ci-parity-gate off: no lint record rendered
    payload, state = _payload(pack_repo, _edits(pack_repo, tmp_path, "a.py")), tmp_path / "s"

    first = _verify(pack_repo, deps, payload, state, runner=_ruff(F401))
    second = _verify(pack_repo, deps, payload, state, runner=_ruff(F401))

    assert first.trace.combined.decision is Decision.NONE
    assert first.trace.combined.user_notes == (NO_STAGES_NOTE,)
    assert second.trace.combined.user_notes == ()


# --- execution stages are serialized -----------------------------------------------------


class _Exec:
    """A scripted execution stage that records its runs."""

    name = "typecheck"
    needs_diff = True
    mode = "block"

    def __init__(self) -> None:
        from coding_agent_playbook.hook_runtime.stop.stages import StageCost

        self.cost = StageCost.EXECUTION
        self.runs = 0

    def applies(self, plan: StopPlan) -> bool:
        return True

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        self.runs += 1
        return StageResult(self.name, "green")


def test_exec_stage_waits_for_the_exec_lock(tmp_path: Path) -> None:
    store = StateStore(tmp_path / STATE_DIR_NAME)
    inner, clock = _Exec(), FakeClock()
    locked = ExecLocked(inner, store, clock)
    plan: Any = None

    with store.lock(EXEC_LOCK):  # another subagent's mypy holds it
        busy = locked.run(plan, clock.monotonic())
    free = locked.run(plan, clock.monotonic() + 1.0)

    assert (busy.status, busy.skip_category, inner.runs) == ("skipped", "timeout", 1)
    assert free.status == "green"
    assert (tmp_path / STATE_DIR_NAME / "locks" / f"{EXEC_LOCK}.lock").is_file()


def test_golden_claude_payload(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path, hook_payload: Payload
) -> None:
    """The ``ssv_edit_lint_red`` golden pins parse, reason and wire at once."""
    golden = hook_payload("claude_code", "subagent_stop", "ssv_edit_lint_red")
    (repo.root / ".agent").mkdir()
    edit = _tool_use("Edit", file_path=str(repo.root / "a.py"), old_string="a", new_string="b")
    (repo.root / ".agent" / "agent_42.jsonl").write_text(json.dumps(edit) + "\n", "utf-8")

    report = _verify(repo, deps, repo.relocate(golden), tmp_path / "state", runner=_ruff(F401))

    expected, combined = golden.expected["result"], report.trace.combined
    assert (combined.decision.value, combined.reason) == (expected["decision"], expected["reason"])
    assert report.trace.wire == golden.wire()
