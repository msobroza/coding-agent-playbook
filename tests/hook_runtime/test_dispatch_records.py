"""What a dispatch records, and the payloads it leaves alone (specs/prK-lifecycle-hooks.md §D.2.2, §D.6).

The decision log stores ids only; the asked set turns a later post-tool event
into an ``override`` line; deferred notes reach the next user-visible channel;
the ledger records touched paths. Foreign payloads, events outside git and
unusable payloads never block anything they should not.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch import dispatch_event, read_stdin, run_event
from coding_agent_playbook.hook_runtime.event import EventName, Harness
from coding_agent_playbook.hook_runtime.harness import DENY_EXIT, STDIN_CAP_BYTES
from coding_agent_playbook.hook_runtime.state.session import SessionState
from tests.hook_runtime.dispatch_kit import POST, PRE, body, boom, dispatch, verdict
from tests.hook_runtime.guard_repo import SESSION_ID, hook_record

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from tests.hook_runtime.fakes import FakeHandlerResolver
    from tests.hook_runtime.guard_repo import GuardRepo


# --- logging, the asked set, deferred notes -------------------------------------------


def test_decision_line_never_contains_command_text_or_path(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-a"))
    resolver.handlers["guard-a"] = verdict(Decision.DENY, "mysql -pS3cret leaks a password")
    command = "mysql -pS3cret -h db.internal < /srv/secret/dump.sql"

    dispatch(make_deps(), repo, tool_input={"command": command})

    text = "".join(p.read_text() for p in repo.state_root.glob("decisions-*.jsonl"))
    assert "S3cret" not in text
    assert "/srv/secret" not in text
    assert "db.internal" not in text
    (line,) = repo.decisions()
    assert (line["hook_id"], line["rule_id"], line["decision"]) == ("guard-a", "r1", "deny")
    assert (line["tool_name"], line["tool_class"], line["session_id"]) == (
        "Bash",
        "shell",
        SESSION_ID,
    )


def test_escape_marker_is_an_escape_line_of_ids_only(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    """A result's ``escape`` marker (pii-prompt-guard's override token) is logged, never its text."""
    repo.install(hook_record("guard-a"))
    resolver.handlers["guard-a"] = verdict(Decision.NONE, escape="override_token")

    wire = dispatch(make_deps(), repo)

    assert wire.stdout == ""
    (line,) = repo.decisions()
    assert (line["decision"], line["effective"], line["rule_id"], line["escape"]) == (
        "escape",
        "none",
        "r1",
        "override_token",
    )


def test_quality_context_is_not_a_logged_guard_decision(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("lint-q", events=["post_tool_use"], on_error="open"))
    resolver.handlers["lint-q"] = verdict(Decision.CONTEXT, context=("F401 unused import",))

    wire = dispatch(make_deps(), repo, POST, tool="Edit")

    assert "F401 unused import" in wire.stdout
    assert repo.decisions() == []


def test_post_event_for_asked_tool_use_id_logs_override(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(
        hook_record("guard-a", events=["pre_tool_use", "post_tool_use"], decisions=["ask", "none"])
    )
    asks = verdict(Decision.ASK, "push to main?")
    resolver.handlers["guard-a"] = lambda ev, ctx: asks(ev, ctx) if ev.name is PRE else None

    dispatch(make_deps(), repo, PRE)
    dispatch(make_deps(), repo, POST)

    assert [(line["decision"], line["hook_id"]) for line in repo.decisions()] == [
        ("ask", "guard-a"),
        ("override", "guard-a"),
    ]
    assert SessionState(repo.store(), SESSION_ID).was_asked("toolu_1")


def test_deferred_notes_drained_claude_on_prompt_or_start_opencode_every_dispatch(
    repo: GuardRepo, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install()
    SessionState(repo.store(), SESSION_ID).push_note("ruff-feedback skipped: internal error")

    on_stop = dispatch(make_deps(), repo, EventName.STOP, tool=None)
    on_prompt = dispatch(make_deps(), repo, EventName.USER_PROMPT_SUBMIT, tool=None, prompt="hi")
    SessionState(repo.store(), SESSION_ID).push_note("second note")
    on_opencode = dispatch(make_deps(), repo, EventName.STOP, tool=None, harness=Harness.OPENCODE)

    assert on_stop.stdout == ""
    assert body(on_prompt) == {"systemMessage": "ruff-feedback skipped: internal error"}
    assert json.loads(on_opencode.stdout)["notice"] == "second note"


def test_notes_on_session_end_are_deferred_to_the_next_prompt(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("log-q", events=["session_end"], on_error="open", decisions=["none"]))
    resolver.handlers["log-q"] = boom

    dispatch(make_deps(), repo, EventName.SESSION_END, tool=None)
    on_prompt = dispatch(make_deps(), repo, EventName.USER_PROMPT_SUBMIT, tool=None, prompt="hi")

    assert "log-q skipped: internal error" in body(on_prompt)["systemMessage"]


def test_post_tool_use_records_the_ledger(
    repo: GuardRepo, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(path_classes={"py": ["*.py"]})

    dispatch(make_deps(), repo, POST, tool="Edit")
    dispatch(make_deps(), repo, POST, tool_input={"command": "echo x > build/out.txt"})

    ledger = next(repo.state_root.glob("sessions/*/ledger.jsonl")).read_text().splitlines()
    first, second = (json.loads(line) for line in ledger)
    assert (first["paths"], first["cats"]) == (["src/app.py"], ["py"])
    assert second["writes"] == ["build/out.txt"]


def test_no_proc_run_on_pre_tool_use_edit_or_non_git_bash(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-a", priority=1), hook_record("lint-q", on_error="open"))
    resolver.handlers["guard-a"] = verdict(Decision.NONE)
    resolver.handlers["lint-q"] = verdict(Decision.CONTEXT, context=("hint",))
    deps = make_deps()

    dispatch(deps, repo, tool="Edit")
    dispatch(deps, repo, tool="Bash")

    assert deps.proc.calls == []  # type: ignore[attr-defined]


# --- inert and faulty payloads ----------------------------------------------------------


def test_contract_fault_on_pre_tool_use_asks_and_elsewhere_is_silent(
    repo: GuardRepo, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install()
    malformed = b'{"session_id": "s", "hook_event_name": "PreToolUse", "cwd": 1'

    pre = run_event(PRE, Harness.CLAUDE_CODE, malformed, make_deps())
    stop = run_event(EventName.STOP, Harness.CLAUDE_CODE, b"[]", make_deps())

    assert body(pre)["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert "Playbook could not read this tool call" in pre.stdout
    assert (stop.stdout, stop.exit_code) == ("", 0)


def test_argv_problem_is_a_contract_fault_never_exit_2(
    repo: GuardRepo, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install()
    payload = repo.payload(PRE, tool="Bash")

    wire = run_event(
        PRE, Harness.CLAUDE_CODE, payload, make_deps(CI="1"), argv_problem="unknown flag --x"
    )

    assert wire.exit_code == DENY_EXIT
    assert "unknown flag --x" in wire.stderr


@pytest.mark.parametrize("env_dir", [True, False])
def test_foreign_or_outside_git_payload_is_inert(
    tmp_path: Path, repo: GuardRepo, make_deps: Callable[..., RuntimeDeps], env_dir: bool
) -> None:
    repo.install(hook_record("guard-a"))
    deps = make_deps() if env_dir else make_deps(CLAUDE_PROJECT_DIR=str(tmp_path / "nowhere"))
    payload = repo.payload(PRE, tool="Bash", hook_event_name="beforeShellExecution")

    trace = dispatch_event(PRE, Harness.CLAUDE_CODE, payload, deps)

    assert (trace.wire.stdout, trace.wire.exit_code, trace.written) == ("", 0, False)


def test_event_outside_git_is_inert(
    tmp_path: Path, make_deps: Callable[..., RuntimeDeps], repo: GuardRepo
) -> None:
    elsewhere = tmp_path / "plain"
    elsewhere.mkdir()
    payload = json.dumps(
        {"session_id": "s", "cwd": str(elsewhere), "hook_event_name": "Stop"}
    ).encode()

    trace = dispatch_event(
        EventName.STOP, Harness.CLAUDE_CODE, payload, make_deps(), project_dir=str(elsewhere)
    )

    assert trace.written is False


def test_read_stdin_caps_and_drains() -> None:
    stream = io.BytesIO(b"x" * (STDIN_CAP_BYTES + 10))

    data, truncated = read_stdin(stream)

    assert (len(data), truncated, stream.read()) == (STDIN_CAP_BYTES, True, b"")
    assert read_stdin(b"x" * (STDIN_CAP_BYTES + 1))[1] is True
