"""stop-drift-and-orphan-gate: the ``drift`` Stop stage (specs/prK-hook-pack.md §E.1, §E.0.4).

The stage is driven directly through K2's ``Stage`` contract (``applies`` /
``run`` over a ``StopPlan``): the coordinator that plans it is K6's, so a
second Stop on the same fingerprint is K6's test. The fast path hashes every
lockfile entry and scans the adapters' sentinel dirs for orphans; the slow
path is a ``playbook sync --check`` child, scripted on ``FakeProc``, only
when canonical sources or detector inputs were touched. Until K6 the
dispatcher calls the hook's binding directly: it blocks once per finding,
then notes (the last tests, through ``playbook-hook simulate stop``).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.generated_output.sentinel import sentinel_line
from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, parse_guard_config
from coding_agent_playbook.hook_runtime.config.schema import GUARD_CONFIG_REL, LOCKFILE_REL
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.escape import EscapeHatches
from coding_agent_playbook.hook_runtime.event import CanonicalEvent, EventName, Harness
from coding_agent_playbook.hook_runtime.handlers._drift import (
    DriftFinding,
    drift_summary,
    sync_check_findings,
)
from coding_agent_playbook.hook_runtime.handlers.stop_drift_and_orphan_gate import (
    STAGE_NAME,
    DriftStage,
)
from coding_agent_playbook.hook_runtime.registry import HandlerContext
from coding_agent_playbook.hook_runtime.session import SessionState
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME, session_key
from coding_agent_playbook.hook_runtime.stop.stages import (
    STOP_STAGE_ORDER,
    StageCost,
    StopPlan,
    order_stages,
)
from tests.hook_runtime.fakes import FakeClock, FakeGit, FakeProc
from tests.hook_runtime.guard_repo import SESSION_ID
from tests.hook_runtime.handlers.pack_repo import (
    PackRepo,
    engine_hook,
    playbook_calls,
    playbook_child,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "stop-drift-and-orphan-gate"
RULE: Final = ".continue/rules/10-x.md"
COMMAND: Final = ".claude/commands/triage.md"
OPENCODE_COMMAND: Final = ".opencode/command/triage.md"
ADVICE: Final = "Run playbook validate && playbook sync before finishing."


def _generated(body: str = "# x\n") -> str:
    return f"{sentinel_line('html')}\n{body}"


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    """A synced fixture: a Continue rule and two prompt outputs, all pristine and locked."""
    for rel in (RULE, COMMAND, OPENCODE_COMMAND):
        pack_repo.write(rel, _generated())
    pack_repo.install_pack([HOOK_ID])
    pack_repo.lock_outputs(RULE, COMMAND, OPENCODE_COMMAND)
    return pack_repo


def _stage(
    repo: PackRepo,
    *,
    proc: FakeProc | None = None,
    clock: FakeClock | None = None,
    fast_path: Any = None,
) -> DriftStage:
    cfg = parse_guard_config((repo.root / GUARD_CONFIG_REL).read_bytes(), platform="linux")
    assert isinstance(cfg, GuardConfig)
    clock = clock or FakeClock()
    ctx = HandlerContext(
        hook=cfg.hooks[HOOK_ID],
        config={"stage": STAGE_NAME},
        cfg=cfg,
        git=FakeGit(),
        session=SessionState(repo.store(), SESSION_ID),
        ledger=None,
        proc=proc or FakeProc(),
        clock=clock,
        deadline=clock.monotonic() + 3.0,
        hatches=EscapeHatches(),
        platform="linux",
    )
    extra = {} if fast_path is None else {"fast_path": fast_path}
    return DriftStage(ctx=ctx, repo_root=str(repo.root), **extra)


def _plan(stage: DriftStage, *cats: str, tc: str = "edit") -> StopPlan:
    event = CanonicalEvent(
        name=EventName.STOP,
        harness=Harness.CLAUDE_CODE,
        session_id=SESSION_ID,
        cwd=stage.repo_root,
        project_dir=stage.repo_root,
    )
    line = {"v": 1, "ev": "post_tool_use", "tc": tc, "paths": ["x"], "cats": list(cats)}
    return StopPlan(event=event, stages=(stage,), ledger=(line,) if cats else ())


def _sync_check(*paths: str) -> bytes:
    entries = "".join(f"  {p}\n    Orphaned generated file; run 'playbook sync'.\n" for p in paths)
    return f"Drift detected:\n{entries}".encode()


# --- the fast path ----------------------------------------------------------------------


def test_hand_edited_continue_rule_gives_one_drift_line(repo: PackRepo) -> None:
    repo.write(RULE, _generated("# hand edit\n"))
    stage = _stage(repo)

    result = stage.run(_plan(stage, "generated"), stage.ctx.deadline)

    assert result.status == "red"
    [line] = result.lines
    assert line == f'Playbook drift: ".continue/rules/10-x.md" (hash mismatch). {ADVICE}'


def test_sentinel_command_missing_from_lockfile_is_orphan(repo: PackRepo) -> None:
    repo.write(".claude/commands/old.md", _generated())
    repo.write(".claude/commands/mine.md", "# a user command, no sentinel\n")
    stage = _stage(repo)

    result = stage.run(_plan(stage, "generated"), stage.ctx.deadline)

    assert result.lines == (f'Playbook drift: ".claude/commands/old.md" (orphan). {ADVICE}',)


def test_sentinel_claude_rules_file_missing_from_lockfile_is_orphan(repo: PackRepo) -> None:
    """The rules file is a composite singleton (SPEC §10.3.1); the rest of ``.claude/rules/``
    is the user's and is never scanned, sentinel or not."""
    repo.write(".claude/rules/coding-agent-playbook.md", _generated())
    repo.write(".claude/rules/team.md", _generated())
    stage = _stage(repo)

    result = stage.run(_plan(stage, "generated"), stage.ctx.deadline)

    assert result.lines == (
        f'Playbook drift: ".claude/rules/coding-agent-playbook.md" (orphan). {ADVICE}',
    )


def test_sentinel_skill_md_not_in_lockfile_is_not_orphan(repo: PackRepo) -> None:
    """Parity with the #25 leftover policy: ``.claude/skills`` is lockfile-only, never scanned."""
    repo.write(".claude/skills/old-skill/SKILL.md", _generated())
    stage = _stage(repo)

    result = stage.run(_plan(stage, "generated"), stage.ctx.deadline)

    assert result.status == "green"


@pytest.mark.parametrize("secret", [".claude/commands/.env", ".claude/commands/key.pem"])
def test_orphan_scan_never_reads_a_secret_or_linked_file(repo: PackRepo, secret: str) -> None:
    repo.write(secret, _generated())
    (repo.root / ".claude" / "commands" / "linked.md").symlink_to(repo.root / COMMAND)
    stage = _stage(repo)

    assert stage.run(_plan(stage, "generated"), stage.ctx.deadline).status == "green"


def test_drift_summary_lists_near_120_characters_then_counts_the_rest() -> None:
    findings = [DriftFinding(f".claude/commands/cmd-{i:02d}.md", "orphan") for i in range(9)]

    summary = drift_summary(findings)

    assert summary.startswith('Playbook drift: ".claude/commands/cmd-00.md" (orphan), ')
    assert summary.endswith(" and 6 more.")
    assert len(summary) <= 160  # one deny-reason line (OutputCaps.REASON)


def test_sync_check_findings_take_only_the_entry_lines() -> None:
    report = _sync_check(COMMAND) + b"  .gitignore\n    Managed block is missing or stale.\n"

    assert sync_check_findings(report) == [
        DriftFinding(COMMAND, "out of sync"),
        DriftFinding(".gitignore", "out of sync"),
    ]
    assert sync_check_findings(b"Drift detected:\n") == [
        DriftFinding("playbook sync --check", "drift")
    ]
    with pytest.raises(ValueError, match="without a drift report"):
        sync_check_findings(b"error: no .coding-agent-playbook.toml\n")


_CANNOT_VERIFY = (
    b"Cannot verify .claude: it is not a directory, but sync writes generated files inside it.\n"
    b"Move or rename it (sync never deletes it), then re-run 'playbook sync --check'.\n"
)


def test_sync_check_findings_read_a_check_that_cannot_verify() -> None:
    """Regression: a ``--check`` stopped by something in the way prints ``Cannot verify
    <path>: …`` and no drift header; the parser raised, so the stage read as a crash."""
    settings = b"Cannot verify .claude/settings.json: Expecting value at 1:1.\nFix the file.\n"

    assert sync_check_findings(_CANNOT_VERIFY) == [DriftFinding(".claude", "cannot verify")]
    assert sync_check_findings(settings) == [DriftFinding(".claude/settings.json", "cannot verify")]


def test_a_check_that_cannot_verify_is_red_not_skipped(repo: PackRepo) -> None:
    proc = FakeProc()
    proc.script(playbook_child("sync"), stdout=_CANNOT_VERIFY, returncode=1)
    stage = _stage(repo, proc=proc)

    result = stage.run(_plan(stage, "canonical"), stage.ctx.deadline)

    assert result.status == "red"
    assert result.lines == (f'Playbook drift: ".claude" (cannot verify). {ADVICE}',)


# --- activation and the slow path --------------------------------------------------------


def test_no_ledger_activity_inactive_with_zero_file_reads(repo: PackRepo) -> None:
    calls: list[str] = []

    def spy(root: str, cfg: GuardConfig, *, platform: str) -> list[Any]:
        calls.append(root)
        return []

    stage = _stage(repo, fast_path=spy)

    assert not stage.applies(_plan(stage))
    assert not stage.applies(_plan(stage, "canonical", tc="read"))  # a Read changes nothing
    assert not stage.applies(_plan(stage, "py"))
    assert stage.applies(_plan(stage, "generated", tc="shell"))  # Bash writes into output dirs
    assert calls == []


def test_deleted_repo_local_prompt_reports_orphans_via_sync_check_child(repo: PackRepo) -> None:
    proc = FakeProc()
    proc.script(playbook_child("sync"), stdout=_sync_check(COMMAND, OPENCODE_COMMAND), returncode=1)
    stage = _stage(repo, proc=proc)

    result = stage.run(_plan(stage, "canonical"), stage.ctx.deadline)

    assert result.status == "red"
    assert result.lines == (
        f'Playbook drift: "{COMMAND}" (out of sync), "{OPENCODE_COMMAND}" (out of sync). {ADVICE}',
    )
    assert playbook_calls(proc) == [("sync", "--check", "--repo-root", str(repo.root))]
    assert proc.calls[0].timeout <= 3.0  # never past the stage deadline


def test_slow_path_only_when_canonical_or_detector_inputs_touched(repo: PackRepo) -> None:
    proc = FakeProc()
    proc.script(playbook_child("sync"), stdout=b"No drift detected.\n")

    generated = _stage(repo, proc=proc)
    assert generated.run(_plan(generated, "generated"), generated.ctx.deadline).status == "green"
    assert proc.calls == []
    detector = _stage(repo, proc=proc)
    assert detector.run(_plan(detector, "detector_input"), detector.ctx.deadline).verified
    assert len(proc.calls) == 1


# --- failure: skipped, never green -------------------------------------------------------


def test_error_or_timeout_skipped_never_green(repo: PackRepo) -> None:
    timeout = FakeProc()
    timeout.script(playbook_child("sync"), timeout=True)
    crashed = FakeProc()
    crashed.script(playbook_child("sync"), stdout=b"Traceback: boom\n", returncode=1)
    clock = FakeClock()

    timed_out = _stage(repo, proc=timeout)
    late = _stage(repo, clock=clock)
    clock.advance(10.0)  # no time left before the deadline: the child is never started
    errored = _stage(repo, proc=crashed)
    results = [
        timed_out.run(_plan(timed_out, "canonical"), timed_out.ctx.deadline),
        late.run(_plan(late, "canonical"), late.ctx.deadline),
        errored.run(_plan(errored, "canonical"), errored.ctx.deadline),
    ]
    (repo.root / LOCKFILE_REL).write_text("not = [toml", encoding="utf-8")
    broken = _stage(repo)
    results.append(broken.run(_plan(broken, "generated"), broken.ctx.deadline))

    assert [(r.status, r.skip_category) for r in results] == [
        ("skipped", "timeout"),
        ("skipped", "timeout"),
        ("skipped", "crash"),
        ("skipped", "crash"),
    ]
    assert not any(r.verified for r in results)


def test_stage_name_is_in_stop_stage_order(repo: PackRepo) -> None:
    stage = _stage(repo)
    handler = engine_hook(HOOK_ID).frontmatter.handler

    assert stage.name == STAGE_NAME == STOP_STAGE_ORDER[0]
    assert stage.cost is StageCost.DETERMINISTIC
    assert stage.needs_diff is False  # gitignored outputs never change the fingerprint
    assert order_stages([stage]) == (stage,)
    assert handler is not None and handler.config == {"stage": STAGE_NAME}


# --- until K6: the dispatcher calls the binding directly --------------------------------


def _ledger(repo: PackRepo, state: Path, *cats: str) -> None:
    path = state / STATE_DIR_NAME / "sessions" / session_key(SESSION_ID) / "ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"v": 1, "ev": "post_tool_use", "tc": "edit", "paths": [RULE], "cats": list(cats)}
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")


def test_standalone_stop_blocks_once_per_finding_then_notes(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.write(RULE, _generated("# hand edit\n"))
    state = tmp_path / "state"
    _ledger(repo, state, "generated")
    payload = repo.payload(EventName.STOP, stop_hook_active=False)

    first = repo.simulate(payload, deps(), event=EventName.STOP, state=state)
    second = repo.simulate(payload, deps(), event=EventName.STOP, state=state)

    assert first.trace.combined.decision is Decision.DENY
    assert first.trace.combined.reason.splitlines() == [
        'Playbook drift: ".continue/rules/10-x.md" (hash mismatch).',
        ADVICE,
    ]
    assert second.trace.combined.decision is Decision.NONE
    assert second.trace.combined.user_notes == (
        "Playbook drift is unchanged since the last block: NOT verified.",
    )


def test_standalone_stop_without_ledger_is_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo.write(RULE, _generated("# hand edit\n"))
    proc = FakeProc()

    report = repo.simulate(
        repo.payload(EventName.STOP, stop_hook_active=False), deps(proc=proc), event=EventName.STOP
    )

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.user_notes == ()
    assert proc.calls == []


def test_standalone_stop_that_cannot_verify_notes_not_verified(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    """A lockfile without ``rendered_at`` cannot be read: skipped (crash), said, never green."""
    pack_repo.install_pack([HOOK_ID])  # writes a lockfile with only the guard_config row
    state = tmp_path / "state"
    _ledger(pack_repo, state, "generated")
    payload = pack_repo.payload(EventName.STOP, stop_hook_active=False)

    report = pack_repo.simulate(payload, deps(), event=EventName.STOP, state=state)

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.user_notes == (
        "Playbook drift check skipped (crash): NOT verified.",
    )
