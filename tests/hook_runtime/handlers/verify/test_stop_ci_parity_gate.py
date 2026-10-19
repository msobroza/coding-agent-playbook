"""stop-ci-parity-gate: the Stop coordinator as shipped (specs/prK-hook-pack.md §E.2, §D.5).

Driven through ``playbook-hook simulate stop`` with the golden Claude Stop
payloads, against a repository synced with the coordinator and K5's
``drift`` stage hook. ``FakeGit`` answers the fingerprint, ``FakeProc``
refuses every spawn: the drift fast path needs no tool, and the coordinator's
own ``lint`` stage runs ruff through ``FakeStageRunner`` (``tests.hook_runtime.handlers.stop_kit``).
The drift hook is never fanned out on its own; its finding reaches the model
only inside the coordinator's one combined reason, emitted as JSON on exit 0.
The execution stages are ``test_stop_ci_parity_gate_exec``'s.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.generated_output.sentinel import sentinel_line
from coding_agent_playbook.guard_config import DetectInputs
from coding_agent_playbook.hook_runtime.config.schema import GUARD_CONFIG_REL
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.git.safe_git import Fingerprint
from coding_agent_playbook.hook_runtime.handlers.stop_drift_and_orphan_gate import DriftStage
from coding_agent_playbook.hook_runtime.registry import load_builtin
from coding_agent_playbook.hook_runtime.state.store import STATE_DIR_NAME, session_key
from tests.hook_payloads import load_hook_payload
from tests.hook_runtime.fakes import FakeGit, FakeProc, FakeStageRunner, StageCall
from tests.hook_runtime.handlers.pack_repo import PackRepo, engine_hook
from tests.hook_runtime.handlers.stop_kit import (
    HEAD_TREE,
    NO_CLAIM,
    changed_git,
    py_edit,
    reason_lines,
    ruff_row,
    script_ruff,
    seed_ledger,
    session_of,
    stop,
    stop_payload,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport

pytestmark = pytest.mark.catalog

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

    records = rendered["stop_gate"]["stages"]
    [record] = [r for r in records if r["name"] == "drift"]

    assert (record["name"], record["owner"], record["cost"]) == ("drift", DRIFT_ID, "deterministic")
    assert record["needs_diff"] is defaults["needs_diff"] is False
    assert rendered["deadlines_ms"]["stop"] == 3_000  # budget_s only: no execution stage
    assert [r["name"] for r in records] == ["drift", "lint", "verify-claim"]  # its own stages


# --- lint: attribution against the HEAD baseline -------------------------------------------

F401: Final = ruff_row("src/x.py", "F401", "`os` imported but unused", 12)
HEADER: Final = "Playbook gate RED — fix before finishing (tree 1a2b3c4d, block 1/2):"


@pytest.fixture
def linted(pack_repo: PackRepo) -> PackRepo:
    """The coordinator alone: its ``lint`` and ``verify-claim`` stages, no verify command."""
    pack_repo.write("src/x.py", "import os\n")
    pack_repo.install_pack([HOOK_ID])
    return pack_repo


def test_new_ruff_error_single_block(
    linted: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    runner = FakeStageRunner()
    script_ruff(runner, worktree=[F401])

    report = stop(
        linted, deps, stop_payload(linted), git=changed_git(), state=tmp_path, runner=runner
    )

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report) == [HEADER, '[lint] "src/x.py":12 F401 `os` imported but unused']
    assert [call.args[0] for call in runner.calls] == ["check", "format", "check", "format"]


def test_only_preexisting_error_none(
    linted: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    runner = FakeStageRunner()
    moved = ruff_row("src/x.py", "F401", "`os` imported but unused", 30)  # same tuple, new line
    script_ruff(runner, worktree=[moved], baseline=[F401])

    report = stop(
        linted, deps, stop_payload(linted), git=changed_git(), state=tmp_path, runner=runner
    )

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.user_notes == (
        "verified locally (lint); the CI matrix is authoritative",
    )


def test_newly_unformatted_file_blocks(
    linted: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    runner = FakeStageRunner()
    script_ruff(runner, unformatted=["src/y.py", "src/old.py"], baseline_unformatted=["src/old.py"])

    report = stop(
        linted, deps, stop_payload(linted), git=changed_git(), state=tmp_path, runner=runner
    )

    assert reason_lines(report)[1:] == [
        '[lint] "src/y.py" needs reformatting (ruff format) (1 new; 1 pre-existing ignored)'
    ]


def test_lint_baseline_cached_per_head_tree(
    linted: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    runner = FakeStageRunner()
    script_ruff(runner, worktree=[F401], baseline=[F401])
    trees = ("a" * 40, "b" * 40, "c" * 40)
    gits = [
        changed_git(trees[0]),
        changed_git(trees[1]),
        changed_git(trees[2], head_tree_id="e" * 40),
    ]

    for git in gits:
        stop(linted, deps, stop_payload(linted), git=git, state=tmp_path, runner=runner)

    exports = [call for git in gits for call in git.calls if call[0] == "archive_to"]
    assert len(exports) == 2  # the second Stop on the same HEAD tree reads the cache
    cache = tmp_path / STATE_DIR_NAME / "stop" / f"lint-baseline-{HEAD_TREE}.json"
    assert json.loads(cache.read_bytes())["check"] == [
        ["src/x.py", "F401", "`os` imported but unused", 12]
    ]


def test_baseline_export_skips_secret_globs(
    linted: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    seen: list[list[str]] = []
    runner = FakeStageRunner()

    def look(call: StageCall) -> None:  # the fs spy: what the export dir holds when ruff runs
        cwd = call.cwd
        if cwd is not None:
            root = Path(cwd)
            seen.append(
                sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
            )

    script_ruff(runner, worktree=[F401], spy=look)
    archive = {"src/x.py": b"import os\n", ".env": b"TOKEN=abc\n", "deploy/.env.prod": b"X=1\n"}
    git = changed_git(archives={"HEAD": archive})

    stop(linted, deps, stop_payload(linted), git=git, state=tmp_path, runner=runner)

    assert seen and all(files == ["src/x.py"] for files in seen)


@pytest.mark.parametrize(
    ("script", "note"),
    [
        ({"returncode": 2, "stderr": b"ruff failed: bad config"}, "lint skipped (crash)"),
        ({"timeout": True}, "lint skipped (timeout)"),
        (None, "lint skipped (toolchain_missing)"),
    ],
)
def test_ruff_that_cannot_run_is_not_verified_never_green(
    linted: PackRepo,
    deps: Callable[..., RuntimeDeps],
    tmp_path: Path,
    script: dict[str, Any] | None,
    note: str,
) -> None:
    runner = FakeStageRunner()
    if script is not None:
        runner.script("ruff", **script)

    report = stop(
        linted, deps, stop_payload(linted), git=changed_git(), state=tmp_path, runner=runner
    )

    assert report.trace.combined.decision is Decision.NONE
    assert f"NOT verified: {note}" in report.trace.combined.user_notes
    assert not any("verified locally" in n for n in report.trace.combined.user_notes)


# --- verify-claim -----------------------------------------------------------------------------


@pytest.fixture
def claimed(pack_repo: PackRepo) -> PackRepo:
    """The coordinator with pytest detected: ``tests`` is a verify command."""
    pack_repo.install_pack([HOOK_ID], detect=DetectInputs(facts={"dev_tools": {"pytest"}}))
    return pack_repo


VERIFY_LINE: Final = (
    '[verify-claim] You said "tests pass"; no passing pytest since your last edit. '
    "Run it and report the result."
)


def test_all_tests_pass_claim_with_empty_ledger_blocks(
    claimed: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    report = stop(claimed, deps, stop_payload(claimed), git=changed_git(), state=tmp_path)

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report) == [HEADER, VERIFY_LINE]


def test_claim_after_green_verify_run_passes(
    claimed: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    payload = stop_payload(claimed)
    seed_ledger(tmp_path, session_of(payload), py_edit("src/x.py"))
    ran = claimed.tool_payload(
        "Bash",
        {"command": "uv run pytest -q tests"},
        event=EventName.POST_TOOL_USE,
        session_id=session_of(payload),
    )
    claimed.simulate(ran, deps(), event=EventName.POST_TOOL_USE, state=tmp_path)  # tags it

    report = stop(claimed, deps, payload, git=changed_git(), state=tmp_path)
    after_edit = stop(claimed, deps, payload, git=changed_git("d" * 40), state=tmp_path)
    seed_ledger(tmp_path, session_of(payload), py_edit("src/x.py"))
    stale = stop(claimed, deps, payload, git=changed_git("e" * 40), state=tmp_path)

    assert report.trace.combined.decision is Decision.NONE
    assert after_edit.trace.combined.decision is Decision.NONE
    assert stale.trace.combined.decision is Decision.DENY  # edited again since the green run


def test_no_claim_no_verify_claim(
    claimed: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    payload = stop_payload(claimed, message=NO_CLAIM)

    report = stop(claimed, deps, payload, git=changed_git(), state=tmp_path)

    assert report.trace.combined.decision is Decision.NONE


# --- one combined reason ----------------------------------------------------------------------


def test_three_failing_stages_one_combined_reason(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.install_pack([HOOK_ID, DRIFT_ID], detect=DetectInputs(facts={"dev_tools": {"pytest"}}))
    repo.lock_outputs(RULE)
    payload = stop_payload(repo)
    _hand_edit(repo, tmp_path, session_of(payload))
    runner = FakeStageRunner()
    script_ruff(runner, worktree=[F401])

    report = stop(repo, deps, payload, git=changed_git(), state=tmp_path, runner=runner)

    assert [ran.selected.record.id for ran in report.trace.ran] == [HOOK_ID]
    assert report.trace.combined.decision is Decision.DENY
    lines = reason_lines(report)
    assert lines == [
        HEADER,
        DRIFT_LINE,
        '[lint] "src/x.py":12 F401 `os` imported but unused',
        VERIFY_LINE,
    ]
    assert len(lines) <= 40
