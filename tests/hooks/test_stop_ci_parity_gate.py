"""stop-ci-parity-gate: the Stop coordinator as shipped (specs/prK-hook-pack.md §E.2, §D.5).

Driven through ``playbook-hook simulate stop`` with the golden Claude Stop
payloads, against a repository synced with the coordinator and K5's
``drift`` stage hook. ``FakeGit`` answers the fingerprint, ``FakeProc``
refuses every spawn: the drift fast path needs no tool. The drift hook is
never fanned out on its own; its finding reaches the model only inside the
coordinator's one combined reason, emitted as JSON on exit 0.
"""

from __future__ import annotations

import dataclasses
import json
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook._sentinel import sentinel_line
from coding_agent_playbook.hook_runtime.config import GUARD_CONFIG_REL
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.git import Fingerprint
from coding_agent_playbook.hook_runtime.handlers.stop_drift_and_orphan_gate import DriftStage
from coding_agent_playbook.hook_runtime.registry import load_builtin
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME, session_key
from tests.hook_payloads import load_hook_payload
from tests.hook_runtime.fakes import FakeGit, FakeProc
from tests.hooks.pack_repo import PackRepo, engine_hook

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport

HOOK_ID: Final = "stop-ci-parity-gate"
DRIFT_ID: Final = "stop-drift-and-orphan-gate"
RULE: Final = ".continue/rules/10-x.md"
TREE: Final = "1a2b3c4d" * 5
DRIFT_LINE: Final = (
    '[drift] Playbook drift: ".continue/rules/10-x.md" (hash mismatch). '
    "Run playbook validate && playbook sync before finishing."
)


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    """The coordinator and the drift stage hook on; one locked Continue rule."""
    pack_repo.write(RULE, f"{sentinel_line('html')}\n# x\n")
    pack_repo.install_pack([HOOK_ID, DRIFT_ID])
    pack_repo.lock_outputs(RULE)
    return pack_repo


def _payload(repo: PackRepo, case: str) -> tuple[bytes, str]:
    golden = load_hook_payload("claude_code", "stop", case)
    payload = repo.relocate(golden)
    return payload, str(json.loads(payload)["session_id"])


def _hand_edit(repo: PackRepo, state: Path, session_id: str) -> None:
    """A hand edit of the generated rule, recorded in the session ledger as post_tool_use did."""
    repo.write(RULE, f"{sentinel_line('html')}\n# hand edit\n")
    ledger = state / STATE_DIR_NAME / "sessions" / session_key(session_id) / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    line = {"v": 1, "ev": "post_tool_use", "tc": "edit", "paths": [RULE], "cats": ["generated"]}
    ledger.write_text(json.dumps(line) + "\n", encoding="utf-8")


def _stop(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    payload: bytes,
    *,
    git: FakeGit,
    state: Path | None = None,
    proc: FakeProc | None = None,
) -> SimulateReport:
    runtime = deps(git=git, proc=proc or FakeProc())
    return repo.simulate(payload, runtime, event=EventName.STOP, state=state)


def _changed() -> FakeGit:
    fingerprint = Fingerprint(tree_id=TREE, aux="", mode="tree", unchanged_vs_head=False)
    return FakeGit(fingerprint_value=fingerprint, head_tree_id="f" * 40)


def test_unchanged_tree_zero_tool_calls(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    payload, _ = _payload(repo, "plain")
    unchanged = Fingerprint(tree_id=TREE, aux="", mode="tree", unchanged_vs_head=True)
    git, proc = FakeGit(fingerprint_value=unchanged), FakeProc()

    report = _stop(repo, deps, payload, git=git, proc=proc, state=tmp_path / "state")

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.wire.stdout == ""
    assert (proc.calls, git.calls) == ([], [("fingerprint", ())])


def test_block_is_json_on_exit_0_never_exit_2(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    payload, session_id = _payload(repo, "plain")
    state = tmp_path / "state"
    _hand_edit(repo, state, session_id)

    wire = _stop(repo, deps, payload, git=_changed(), state=state).trace.wire

    assert (wire.exit_code, wire.stderr) == (0, "")
    body = json.loads(wire.stdout)
    assert body["decision"] == "block"
    assert body["reason"].startswith("Playbook gate RED — fix before finishing (tree 1a2b3c4d")


def test_drift_stage_wired_into_combined_reason(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    payload, session_id = _payload(repo, "plain")
    chained, _ = _payload(repo, "block_chain")  # same turn, stop_hook_active = true
    state = tmp_path / "state"
    _hand_edit(repo, state, session_id)

    first = _stop(repo, deps, payload, git=_changed(), state=state)
    second = _stop(repo, deps, chained, git=_changed(), state=state)

    assert [ran.selected.record.id for ran in first.trace.ran] == [HOOK_ID]  # drift not fanned out
    assert first.trace.combined.reason.splitlines() == [
        "Playbook gate RED — fix before finishing (tree 1a2b3c4d, block 1/2):",
        DRIFT_LINE,
    ]
    assert second.trace.combined.decision is Decision.NONE  # the same tree: never a second block
    assert second.trace.combined.user_notes == ("Playbook gate RED at drift — NOT verified.",)


def test_shipped_hook_matches_its_pack_row() -> None:
    fm = engine_hook(HOOK_ID).frontmatter
    assert fm.handler is not None and fm.handler.builtin is not None

    declaration = load_builtin(fm.handler.builtin)

    assert (fm.tier, tuple(fm.events), tuple(fm.decisions), fm.on_error) == (
        "default",
        ("stop",),
        ("deny", "none"),
        "open",
    )
    assert fm.supports == ["claude_code", "opencode"]
    assert set(fm.handler.config) <= set(declaration.config_schema)
    assert {e.value for e in declaration.events} == {"stop", "subagent_stop"}


def test_stop_gate_records_the_drift_stage_as_its_class_declares(repo: PackRepo) -> None:
    rendered = json.loads((repo.root / GUARD_CONFIG_REL).read_bytes())
    defaults = {f.name: f.default for f in dataclasses.fields(DriftStage)}

    [record] = rendered["stop_gate"]["stages"]

    assert (record["name"], record["owner"], record["cost"]) == ("drift", DRIFT_ID, "deterministic")
    assert record["needs_diff"] is defaults["needs_diff"] is False
    assert rendered["deadlines_ms"]["stop"] == 3_000  # budget_s only: no execution stage
