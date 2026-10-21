"""Hook calls the dispatcher ignores are logged, never answered (specs/prU-core-python-skills.md D79).

A foreign payload and an event outside git stay inert: exit 0, nothing on
stdout or stderr. Each one leaves one ``ignored`` decision line naming its
event, harness and reason, so ``playbook-hook doctor`` can show that the
guards were off. With a session id the line is written once per session per
event and reason; without one, once per UTC day per event and reason.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_runtime.diagnostics._doctor_ignored import ignored_call_checks
from coding_agent_playbook.hook_runtime.dispatch.event import EventName, Harness
from coding_agent_playbook.hook_runtime.dispatch.run import dispatch_event
from coding_agent_playbook.hook_runtime.harness.wire import WireOutput
from tests.hook_runtime.dispatch_kit import PRE
from tests.hook_runtime.fakes import FakeClock
from tests.hook_runtime.guard_repo import SESSION_ID, hook_record, streams

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from tests.hook_runtime.guard_repo import GuardRepo

_INERT = WireOutput()
_DAY_S = 86_400


def _silent(*deps: RuntimeDeps) -> bool:
    """Nothing reached the real out/err streams, not only the returned wire."""
    sinks = [stream for d in deps for stream in (d.out, d.err)]
    return all(isinstance(s, io.StringIO) and not s.getvalue() for s in sinks)


def _ignored(lines: list[dict[str, Any]]) -> list[tuple[str, str, str, str]]:
    return [
        (line["event"], line["harness"], line["rule_id"], line["session_id"])
        for line in lines
        if line["decision"] == "ignored"
    ]


@pytest.fixture(autouse=True)
def _cwd_in_repo(repo: GuardRepo, monkeypatch: pytest.MonkeyPatch) -> None:
    """The cwd is a root guess of last resort: never let it be the developer's checkout."""
    repo.install(hook_record("guard-a"))
    monkeypatch.chdir(repo.root)


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"cursor_version": "1.7"}, "foreign_marker:cursor_version"),
        ({"conversation_id": "c"}, "foreign_marker:conversation_id"),
        ({"timestamp": "2026-10-21T00:00:00Z"}, "timestamp"),
        ({"hook_event_name": "beforeShellExecution"}, "event_mismatch"),
    ],
)
def test_claude_foreign_payload_is_logged_once_per_session_and_stays_inert(
    repo: GuardRepo, make_deps: Callable[..., RuntimeDeps], fields: dict[str, str], reason: str
) -> None:
    payload = repo.payload(PRE, tool="Bash", **fields)

    deps = [make_deps(), make_deps()]

    first, second = (dispatch_event(PRE, Harness.CLAUDE_CODE, payload, d) for d in deps)

    assert (first.wire, second.wire, first.written) == (_INERT, _INERT, False)
    assert _silent(*deps)
    assert _ignored(repo.decisions()) == [("pre_tool_use", "claude_code", reason, SESSION_ID)]


def test_missing_session_id_is_logged_once_per_utc_day(
    repo: GuardRepo, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    payload = repo.payload(PRE, tool="Bash", session_id="")
    clock = FakeClock()

    def call() -> WireOutput:
        out, err = streams()
        deps = runtime_deps(env=repo.env(), clock=clock, out=out, err=err)
        wire = dispatch_event(PRE, Harness.CLAUDE_CODE, payload, deps).wire
        assert _silent(deps)
        return wire

    wires = [call(), call()]
    clock.advance(_DAY_S)
    wires.append(call())

    assert wires == [_INERT] * 3
    assert (
        _ignored(repo.decisions())
        == [("pre_tool_use", "claude_code", "missing_session_id", "")] * 2
    )


def test_doctor_reads_back_what_the_dispatcher_wrote(
    repo: GuardRepo, make_deps: Callable[..., RuntimeDeps]
) -> None:
    deps = make_deps()
    dispatch_event(PRE, Harness.CLAUDE_CODE, repo.payload(PRE, timestamp="t"), deps)

    checks = ignored_call_checks(repo.repo, deps, since_days=1)

    assert [(c.name, c.severity) for c in checks] == [("ignored:timestamp", "ok")]


@pytest.mark.parametrize("payload", [None, b"not json"])
def test_claude_project_dir_unset_is_logged_against_the_project_dir(
    repo: GuardRepo,
    runtime_deps: Callable[..., RuntimeDeps],
    payload: bytes | None,
) -> None:
    raw = repo.payload(PRE, tool="Bash") if payload is None else payload

    trace = dispatch_event(
        PRE, Harness.CLAUDE_CODE, raw, runtime_deps(), project_dir=str(repo.root)
    )

    assert trace.wire == _INERT
    session = SESSION_ID if payload is None else ""
    assert _ignored(repo.decisions()) == [
        ("pre_tool_use", "claude_code", "claude_project_dir_unset", session)
    ]


def test_opencode_event_mismatch_is_logged(
    repo: GuardRepo, make_deps: Callable[..., RuntimeDeps]
) -> None:
    payload = repo.payload(EventName.STOP, hook_event_name="session.idle")

    trace = dispatch_event(
        EventName.STOP, Harness.OPENCODE, payload, make_deps(), project_dir=str(repo.root)
    )

    assert trace.wire == _INERT
    assert _ignored(repo.decisions()) == [("stop", "opencode", "event_mismatch", SESSION_ID)]


def _plain_dir(tmp_path: Path) -> Path:
    elsewhere = tmp_path / "plain"
    elsewhere.mkdir()
    return elsewhere


def _user_log(state_home: Path) -> list[dict[str, Any]]:
    root = state_home / "coding-agent-playbook" / "playbook-hooks"
    return [
        json.loads(line)
        for path in sorted(root.glob("decisions-*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


@pytest.mark.parametrize("harness", [Harness.CLAUDE_CODE, Harness.OPENCODE])
def test_event_outside_git_is_logged_once_in_the_user_state_dir(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps], harness: Harness
) -> None:
    elsewhere = _plain_dir(tmp_path)
    state_home = tmp_path / "state"
    env = {"CLAUDE_PROJECT_DIR": str(elsewhere), "XDG_STATE_HOME": str(state_home)}
    payload = json.dumps(
        {"session_id": "s", "cwd": str(elsewhere), "hook_event_name": "Stop"}
    ).encode()

    traces = [
        dispatch_event(
            EventName.STOP, harness, payload, runtime_deps(env=env), project_dir=str(elsewhere)
        )
        for _ in "ab"
    ]

    assert [t.wire for t in traces] == [_INERT, _INERT]
    assert _ignored(_user_log(state_home)) == [("stop", harness.value, "not_a_repo", "s")]


def test_unwritable_user_state_dir_drops_the_line_and_stays_inert(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    elsewhere = _plain_dir(tmp_path)
    state_home = tmp_path / "state"
    state_home.write_text("a regular file, not a directory\n", encoding="utf-8")
    out, err = streams()
    deps = runtime_deps(
        env={"CLAUDE_PROJECT_DIR": str(elsewhere), "XDG_STATE_HOME": str(state_home)},
        out=out,
        err=err,
    )
    payload = json.dumps({"session_id": "s", "cwd": str(elsewhere)}).encode()

    trace = dispatch_event(
        EventName.STOP, Harness.CLAUDE_CODE, payload, deps, project_dir=str(elsewhere)
    )

    assert trace.wire == _INERT
    assert _silent(deps)
    assert state_home.is_file()


def test_async_dispatch_leaves_the_log_to_the_synchronous_one(
    repo: GuardRepo, make_deps: Callable[..., RuntimeDeps]
) -> None:
    post = EventName.POST_TOOL_USE
    payload = repo.payload(post, tool="Bash", timestamp="t")

    trace = dispatch_event(post, Harness.CLAUDE_CODE, payload, make_deps(), asynchronous=True)

    assert trace.wire == _INERT
    assert _ignored(repo.decisions()) == []
