"""``playbook-hook simulate`` runs the exact dispatch pipeline (specs/prK-lifecycle-hooks.md §D.9).

The golden table pins the wire output of every event x harness for one stub
handler that returns the strongest decision the event allows: the bytes a
real harness would read, produced by ``run_event`` itself.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime.cli import main as cli_main
from coding_agent_playbook.hook_runtime.diagnostics.canary import (
    Canary,
    canary_session_id,
    run_canaries,
)
from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateArgs, main, run
from coding_agent_playbook.hook_runtime.dispatch.decision import (
    EVENT_DECISIONS,
    Decision,
    HandlerResult,
)
from coding_agent_playbook.hook_runtime.dispatch.event import EventName, Harness
from coding_agent_playbook.hook_runtime.state.store import session_key
from tests.hook_payloads import load_hook_payload
from tests.hook_runtime.fakes import FakeHandlerResolver
from tests.hook_runtime.guard_repo import GuardRepo, canonical, hook_record

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext

_TOOL_EVENTS = {EventName.PRE_TOOL_USE, EventName.POST_TOOL_USE, EventName.POST_TOOL_USE_FAILURE}


def stub(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult:
    """The strongest decision ``ev`` allows: deny, else context, else a note."""
    allowed = EVENT_DECISIONS[ev.name]
    if Decision.DENY in allowed:
        return HandlerResult(decision=Decision.DENY, hook_id=ctx.hook.id, reason="stub deny")
    if Decision.CONTEXT in allowed:
        return HandlerResult(decision=Decision.CONTEXT, hook_id=ctx.hook.id, context=("stub ctx",))
    return HandlerResult(decision=Decision.NONE, hook_id=ctx.hook.id, user_note="stub note")


def _claude(event: str, **specific: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": event, **specific}}


_BLOCK = {"decision": "block", "reason": "stub deny"}
_NOTE = {"systemMessage": "stub note"}
#: event -> (Claude stdout, Claude process exit, OpenCode decision, OpenCode process exit)
GOLDEN: dict[EventName, tuple[dict[str, Any], int, str, int]] = {
    EventName.SESSION_START: (
        _claude("SessionStart", additionalContext="stub ctx"),
        0,
        "context",
        0,
    ),
    EventName.USER_PROMPT_SUBMIT: (_BLOCK, 0, "deny", 0),
    EventName.PRE_TOOL_USE: (
        _claude("PreToolUse", permissionDecision="deny", permissionDecisionReason="stub deny"),
        10,
        "deny",
        10,
    ),
    EventName.POST_TOOL_USE: (
        _claude("PostToolUse", additionalContext="stub ctx"),
        0,
        "context",
        0,
    ),
    EventName.POST_TOOL_USE_FAILURE: (
        _claude("PostToolUseFailure", additionalContext="stub ctx"),
        0,
        "context",
        0,
    ),
    EventName.STOP: (_BLOCK, 0, "deny", 0),
    EventName.SUBAGENT_STOP: (_BLOCK, 0, "deny", 0),
    EventName.PRE_COMPACT: (_NOTE, 0, "none", 0),
    EventName.SESSION_END: (_NOTE, 0, "none", 0),
}


@pytest.fixture
def repo(tmp_path: Path) -> GuardRepo:
    repo = GuardRepo.create(tmp_path)
    repo.install(hook_record("stub-hook", events=[e.value for e in EventName], on_error="ask"))
    return repo


@pytest.fixture
def deps(runtime_deps: Callable[..., RuntimeDeps]) -> RuntimeDeps:
    return runtime_deps(resolve_handler=FakeHandlerResolver({"stub-hook": stub}))


def _payload(repo: GuardRepo, event: EventName) -> bytes:
    return repo.payload(event, tool="Bash" if event in _TOOL_EVENTS else None)


@pytest.mark.parametrize("harness", list(Harness))
@pytest.mark.parametrize("event", list(EventName))
def test_simulate_reproduces_golden_wire_output(
    repo: GuardRepo, deps: RuntimeDeps, event: EventName, harness: Harness
) -> None:
    claude_body, claude_exit, opencode_decision, opencode_exit = GOLDEN[event]

    wire = run(
        SimulateArgs(event=event, harness=harness, repo=str(repo.root)),
        _payload(repo, event),
        deps=deps,
    ).trace.wire

    if harness is Harness.CLAUDE_CODE:
        assert (json.loads(wire.stdout), wire.exit_code) == (claude_body, claude_exit)
        assert wire.stderr == ("stub deny\n" if claude_exit else "")
        return
    body = json.loads(wire.stdout)
    assert (body["v"], body["decision"], wire.exit_code) == (1, opencode_decision, opencode_exit)
    assert body["reason"] == ("stub deny" if opencode_decision == "deny" else "")
    assert body["context"] == (["stub ctx"] if opencode_decision == "context" else [])
    assert body["notice"] == ("stub note" if opencode_decision == "none" else "")


def test_simulate_uses_ephemeral_state_and_sets_claude_project_dir(
    repo: GuardRepo, deps: RuntimeDeps
) -> None:
    payload = _payload(repo, EventName.PRE_TOOL_USE)

    report = run(
        SimulateArgs(event=EventName.PRE_TOOL_USE, repo=str(repo.root)), payload, deps=deps
    )
    elsewhere = run(
        SimulateArgs(
            event=EventName.PRE_TOOL_USE,
            repo=str(repo.root),
            env=(("CLAUDE_PROJECT_DIR", str(repo.root.parent)),),
        ),
        payload,
        deps=deps,
    )

    assert report.trace.wire.exit_code == 10  # not inert: CLAUDE_PROJECT_DIR was set to --repo
    assert not repo.state_root.exists()  # the real state root and decision log were never touched
    assert elsewhere.trace.written is False  # overridden to a dir outside git: inert


def test_simulate_state_dir_keeps_the_decision_log(
    tmp_path: Path, repo: GuardRepo, deps: RuntimeDeps
) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)

    run(
        SimulateArgs(event=EventName.PRE_TOOL_USE, repo=str(repo.root), state=str(state)),
        _payload(repo, EventName.PRE_TOOL_USE),
        deps=deps,
    )

    assert list((state / "playbook-hooks").glob("decisions-*.jsonl"))


def test_json_format_reports_harness_exit_code_2_for_pre_tool_use_deny(
    repo: GuardRepo, deps: RuntimeDeps
) -> None:
    out = io.StringIO()
    stdin = io.BytesIO(_payload(repo, EventName.PRE_TOOL_USE))

    code = main(
        ["pre_tool_use", "--repo", str(repo.root), "--format", "json"],
        deps=deps,
        stdin=stdin,
        stdout=out,
    )

    report = json.loads(out.getvalue())
    assert code == 0
    assert report["exit_code"] == 2
    assert report["combined"]["decision"] == "deny"
    assert [(d["hook_id"], d["decision"], d["effective"]) for d in report["decisions"]] == [
        ("stub-hook", "deny", "deny")
    ]
    assert set(report) == {"exit_code", "stdout", "stderr", "decisions", "combined", "latency_ms"}


def test_unattended_and_env_overrides_reach_the_pipeline(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo = GuardRepo.create(tmp_path)
    repo.install(hook_record("asker"))
    asks = FakeHandlerResolver(
        {
            "asker": lambda ev, ctx: HandlerResult(
                decision=Decision.ASK, hook_id="asker", reason="ok?"
            )
        }
    )
    deps = runtime_deps(resolve_handler=asks)
    payload = _payload(repo, EventName.PRE_TOOL_USE)
    args = SimulateArgs(event=EventName.PRE_TOOL_USE, repo=str(repo.root))

    attended = run(args, payload, deps=deps).trace.wire
    unattended = run(
        SimulateArgs(event=args.event, repo=args.repo, unattended=True), payload, deps=deps
    )
    hooks_off = run(
        SimulateArgs(event=args.event, repo=args.repo, env=(("PLAYBOOK_HOOKS", "off"),)),
        payload,
        deps=deps,
    )

    assert (attended.exit_code, unattended.trace.wire.exit_code) == (0, 10)
    assert hooks_off.trace.wire.stdout == ""


def test_config_flag_runs_a_given_config_without_the_digest(
    tmp_path: Path, repo: GuardRepo, deps: RuntimeDeps
) -> None:
    repo.write_lock("0" * 64)  # the repo's own config no longer verifies
    config = tmp_path / "candidate.json"
    config.write_bytes(
        canonical({"schema_version": 1, "hooks": {"stub-hook": hook_record("stub-hook")}})
    )

    report = run(
        SimulateArgs(event=EventName.PRE_TOOL_USE, repo=str(repo.root), config=str(config)),
        _payload(repo, EventName.PRE_TOOL_USE),
        deps=deps,
    )

    assert report.trace.wire.exit_code == 10


@pytest.mark.parametrize(
    "argv",
    [["not_an_event"], ["stop", "--env", "NOVALUE"], ["stop", "--config", "/no/such/file.json"]],
)
def test_usage_errors_exit_2(
    argv: list[str], deps: RuntimeDeps, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv, deps=deps, stdin=io.BytesIO(b"{}"), stdout=io.StringIO()) == 2
    assert "error" in capsys.readouterr().err


def test_text_format_and_the_cli_route(
    repo: GuardRepo, deps: RuntimeDeps, capsys: pytest.CaptureFixture[str]
) -> None:
    stdin = io.BytesIO(_payload(repo, EventName.STOP))

    code = cli_main(["simulate", "stop", "--repo", str(repo.root)], deps=deps, stdin=stdin)

    out = capsys.readouterr().out
    assert code == 0
    assert 'stdout: {"decision":"block","reason":"stub deny"}' in out
    assert "exit_code=0 decision=deny" in out


def test_async_flag_runs_only_async_routed_handlers_and_writes_nothing(
    repo: GuardRepo, deps: RuntimeDeps
) -> None:
    """``--async`` (OQ-19): the stub is synchronously routed, so the async dispatch skips it."""
    out = io.StringIO()
    stdin = io.BytesIO(_payload(repo, EventName.POST_TOOL_USE))

    code = main(
        ["post_tool_use", "--async", "--repo", str(repo.root), "--format", "json"],
        deps=deps,
        stdin=stdin,
        stdout=out,
    )
    faulted = run(
        SimulateArgs(event=EventName.STOP, repo=str(repo.root), asynchronous=True),
        _payload(repo, EventName.STOP),
        deps=deps,
    )

    report = json.loads(out.getvalue())
    assert (code, report["stdout"], report["decisions"]) == (0, "", [])
    assert faulted.trace.ran == ()  # a contract fault: no hook runs on a wrong --async
    assert faulted.trace.wire.stdout == ""  # and Stop renders nothing for a fault


# --- canaries ------------------------------------------------------------------------------


def test_canaries_run_the_pipeline_and_leave_no_session(repo: GuardRepo, deps: RuntimeDeps) -> None:
    canaries = [
        Canary(
            name="rm-root",
            event=EventName.PRE_TOOL_USE,
            expect=Decision.DENY,
            fields={"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
        ),
        Canary(name="start", event=EventName.SESSION_START, expect=Decision.NONE),
    ]

    results = run_canaries(canaries, repo_root=str(repo.root), deps=deps)

    assert [(r.name, r.ok, r.decision) for r in results] == [
        ("rm-root", True, Decision.DENY),
        ("start", False, Decision.CONTEXT),
    ]
    assert not (repo.state_root / "sessions" / session_key(canary_session_id())).exists()
    assert {line["canary"] for line in repo.decisions()} == {True}
    assert {line["decision"] for line in repo.decisions()} == {"canary"}


def test_canary_session_id_names_the_process() -> None:
    assert canary_session_id(7) == "playbook-doctor-7"


#: The committed guard_config the CI ``simulate`` smoke step runs (.github/workflows/ci.yml):
#: the engine repo has no config of its own, so the step passes this one with ``--config``.
# N20 moved this file one directory level deeper, into tests/hook_runtime/diagnostics/,
# so parents[2] (was parents[1]) is still tests/.
SMOKE_CONFIG: Final = (
    Path(__file__).resolve().parents[2] / "fixtures" / "hook_guard_config" / "destructive.json"
)


def smoke_guard_config_bytes() -> bytes:
    """``render_guard_config`` for the shipped destructive-command-guard, canonical bytes."""
    from coding_agent_playbook.config.tables.hooks import GuardrailsConfig, HooksConfig
    from coding_agent_playbook.guard_config import (
        GuardConfigInputs,
        render_guard_config,
        serialize_guard_config,
    )
    from tests.hook_runtime.handlers.pack_repo import ENGINE_VERSION, resolve_engine_hooks

    hooks = resolve_engine_hooks(["destructive-command-guard"], Path("/playbook-fixture/proj"))
    inputs = GuardConfigInputs(hooks, HooksConfig(enabled=True), GuardrailsConfig(), ENGINE_VERSION)
    return serialize_guard_config(render_guard_config(inputs))


@pytest.mark.catalog
def test_smoke_fixture_is_the_rendered_default_destructive_guard() -> None:
    """Regenerate with ``SMOKE_CONFIG.write_bytes(smoke_guard_config_bytes())`` after a change."""
    assert SMOKE_CONFIG.read_bytes() == smoke_guard_config_bytes()


def test_bash_rm_root_fixture_reports_exit_code_2(
    repo: GuardRepo, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    """Pins the CI smoke step hermetically: the real guard denies ``rm -rf /`` (exit 2)."""
    golden = load_hook_payload("claude_code", "pre_tool_use", "bash_rm_root")
    out = io.StringIO()
    argv = ["pre_tool_use", "--format", "json", "--config", str(SMOKE_CONFIG)]

    code = main(
        [*argv, "--repo", str(repo.root)],
        deps=runtime_deps(),
        stdin=io.BytesIO(golden.raw),
        stdout=out,
    )

    report = json.loads(out.getvalue())
    assert (code, report["exit_code"]) == (0, 2)
    assert report["combined"]["reason"] == golden.expected["result"]["reason"]
    assert [d["rule_id"] for d in report["decisions"]] == ["rm_root"]
