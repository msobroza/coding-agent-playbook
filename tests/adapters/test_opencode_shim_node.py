"""The rendered OpenCode V1 shim, run for real under node (specs/prK-lifecycle-hooks.md §C.3.2 to §C.3.6).

Each test renders the shim with a small ``REG``, pins a fake dispatcher (see
``opencode_shim_kit``) and drives the V1 server hooks the way OpenCode calls
them. It covers the exit-code contract (only 10 throws), fail-open on every
harness-level failure, the Claude-shaped payload and exact argv, deferred and
post-tool context, the ``wants()`` pre-filter, session context, the Stop
carry, one-shot notices and the V2 stub. POSIX-only; skipped without node.
"""

from __future__ import annotations

import os
import sys
import time
from typing import TYPE_CHECKING, Any, Literal

import pytest

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, EventName
from coding_agent_playbook.hook_runtime.harness.opencode import parse_opencode
from coding_agent_playbook.hook_runtime.harness.wire import DENY_EXIT, ParseContext, WireOutput
from coding_agent_playbook.templates.hook_shims.opencode_wire_port import DEFAULT_REASON
from tests.adapters.opencode_shim_kit import (
    RUNTIME_ARGV,
    SESSION,
    SETUP,
    DispatchCall,
    ShimRepo,
    after,
    before,
    idle,
    rendered,
    respond_step,
    transform,
)
from tests.node_kit import needs_node

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hook_registrations import OpenCodeRegEntry

pytestmark = [
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX fake dispatcher"),
    needs_node,
]

_REG: dict[str, OpenCodeRegEntry] = {
    "session_start": {"timeout_ms": 5000},
    "pre_tool_use": {"timeout_ms": 5000, "tools": ["apply_patch", "bash", "edit", "grep", "write"]},
    "post_tool_use": {"timeout_ms": 5000, "tools": ["edit", "write"]},
    "stop": {"timeout_ms": 5000},
}
_NONE = rendered("pre_tool_use")
_INACTIVE_NOTICE = (
    "playbook lifecycle hooks are NOT active this session ({why}); "
    "apply the AGENTS.md Guardrails section yourself."
)
_CARRY = "The previous turn ended with unresolved playbook gate findings:\n"
_PATCH = "*** Begin Patch\n*** Add File: src/new.py\n+x = 1\n*** End Patch\n"


def _warning(why: str) -> str:
    return f"[playbook] lifecycle hooks inactive: {why}; run 'playbook-hook doctor'"


def _systems(results: list[dict[str, Any]]) -> list[list[str]]:
    """``output.system`` after each ``system.transform`` step, in order."""
    return [r["output"]["system"] for r in results if "system" in (r.get("output") or {})]


def _outputs(results: list[dict[str, Any]]) -> list[object]:
    """``output.output`` after each ``tool.execute.after`` step, in order."""
    return [r["output"]["output"] for r in results if "output" in (r.get("output") or {})]


def _gone(pid: int, wait_s: float = 5.0) -> bool:
    """True once ``pid`` no longer exists (the killed child is reaped by its new parent)."""
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def shim(tmp_path: Path) -> ShimRepo:
    repo = ShimRepo.create(tmp_path, _REG)
    repo.pin()
    for event in _REG:
        repo.respond(event, _NONE)
    return repo


# --- the exit-code contract (K-7) ------------------------------------------------------


@pytest.mark.parametrize(
    ("wire", "reason"),
    [
        (
            rendered("pre_tool_use", Decision.DENY, reason="rm -rf / is blocked"),
            "rm -rf / is blocked",
        ),
        (WireOutput("", "", DENY_EXIT), DEFAULT_REASON),
    ],
    ids=["rendered_deny", "empty_stdout"],
)
def test_before_throws_on_dispatcher_deny_exit_10(
    shim: ShimRepo, wire: WireOutput, reason: str
) -> None:
    shim.respond("pre_tool_use", wire)

    run = shim.run([before("bash", {"command": "rm -rf /"})])

    assert wire.exit_code == DENY_EXIT
    assert run.results[0]["threw"] == reason
    assert (run.events, run.errors) == (["pre_tool_use"], [])


def test_before_proceeds_on_exit_0_none(shim: ShimRepo) -> None:
    run = shim.run([before("bash", {"command": "ls"})])

    assert run.results[0]["threw"] is None
    assert run.results[0]["output"] == {"args": {"command": "ls"}}
    assert (run.events, run.errors) == (["pre_tool_use"], [])


def test_raw_exit_2_fails_open_and_warns_once(shim: ShimRepo) -> None:
    shim.respond("pre_tool_use", WireOutput('{"decision":"deny","reason":"x"}', "", 2))

    run = shim.run([before("bash", {"command": "ls"}), before("edit", {"filePath": "a"})])

    assert [r["threw"] for r in run.results] == [None, None]
    assert run.events == ["pre_tool_use", "pre_tool_use"]
    assert run.errors == [_warning("dispatcher exited 2")]


@pytest.mark.parametrize(
    ("pin", "why"),
    [
        (None, "no interpreter pin (run 'playbook sync')"),
        ("python3", "no interpreter pin (run 'playbook sync')"),
        ("/nonexistent/python", "spawn failed (ENOENT)"),
    ],
    ids=["absent", "relative", "unspawnable"],
)
def test_missing_pin_fails_open_and_injects_inactive_system_notice(
    tmp_path: Path, pin: str | None, why: str
) -> None:
    shim = ShimRepo.create(tmp_path, _REG)
    if pin is not None:
        shim.pin(pin)

    run = shim.run([before("bash", {"command": "ls"}), transform(), transform()])

    assert run.results[0]["threw"] is None
    assert _systems(run.results) == [[_INACTIVE_NOTICE.format(why=why)]] * 2
    assert (run.calls, run.errors) == ([], [_warning(why)])


def test_timeout_kills_dispatcher_and_fails_open(tmp_path: Path) -> None:
    shim = ShimRepo.create(tmp_path, {"pre_tool_use": {"timeout_ms": 200, "tools": "*"}})
    shim.pin()
    shim.hang("pre_tool_use", 30)

    run = shim.run([before("bash", {"command": "sleep"})])

    assert run.results[0]["threw"] is None
    assert run.results[0]["ms"] < 5000
    assert run.errors == [_warning("pre_tool_use exceeded 200 ms")]
    assert _gone(run.calls[0].pid)


def test_malformed_hook_arguments_fail_open(shim: ShimRepo) -> None:
    run = shim.run([{"hook": "tool.execute.before", "input": None, "output": None}])

    assert run.results[0]["threw"] is None
    assert run.calls == []
    [warning] = run.errors
    assert warning.startswith("[playbook] lifecycle hooks inactive: shim error (")


# --- the payload and the argv (§C.3.3, §D.1) ----------------------------------------------


@pytest.mark.parametrize(
    ("tool", "args", "tool_name", "aliases"),
    [
        (
            "edit",
            {"filePath": "src/a.py", "oldString": "a", "newString": "b", "replaceAll": False},
            "Edit",
            {"file_path": "src/a.py", "old_string": "a", "new_string": "b", "replace_all": False},
        ),
        ("write", {"filePath": "src/a.py", "content": "x", "file_path": "kept"}, "Write", {}),
        ("grep", {"pattern": "TODO", "path": "src", "include": "*.py"}, "Grep", {"glob": "*.py"}),
        ("apply_patch", {"patchText": _PATCH}, "apply_patch", {"patch_text": _PATCH}),
        ("bash", {"command": "ls", "timeout": 1000, "workdir": "src"}, "Bash", {}),
    ],
    ids=["edit", "write_keeps_alias", "grep_path_not_aliased", "apply_patch", "bash"],
)
def test_payload_is_claude_shaped_with_v1_aliases_and_exact_argv(
    shim: ShimRepo, tool: str, args: dict[str, Any], tool_name: str, aliases: dict[str, Any]
) -> None:
    [call] = shim.run([before(tool, args)]).calls

    root = str(shim.root)
    assert call.argv == [
        *RUNTIME_ARGV,
        "pre_tool_use",
        "--harness",
        "opencode",
        "--project-dir",
        root,
    ]
    assert call.payload == {
        "hook_event_name": "PreToolUse",
        "session_id": SESSION,
        "tool_use_id": "call_1",
        "tool_name": tool_name,
        "tool_input": {**args, **aliases},
        "cwd": root,
    }
    context = ParseContext(argv_event=EventName.PRE_TOOL_USE, env={}, project_dir=root)
    parsed = parse_opencode(call.stdin, context)  # the dispatcher reads what the shim sends
    assert isinstance(parsed, CanonicalEvent) and parsed.tool is not None
    assert parsed.tool.name == tool_name


def test_shim_never_mutates_output_args(shim: ShimRepo) -> None:
    args = {"filePath": "a.py", "oldString": "x", "newString": "y", "nested": {"k": [1]}}

    run = shim.run([before("edit", args), after("edit", "done", args=args)])

    assert run.results[0]["output"]["args"] == args
    assert run.results[1]["input"]["args"] == args
    assert run.events == ["pre_tool_use", "post_tool_use"]


# --- context: deferred, post-tool, session, carry, notices (§C.3.4, §C.3.6) ---------------


def test_deferred_context_appended_to_same_call_result(shim: ShimRepo) -> None:
    shim.respond("pre_tool_use", rendered("pre_tool_use", Decision.CONTEXT, context=("check it",)))

    run = shim.run(
        [
            before("bash", {"command": "ls"}, call="call_1"),
            after("bash", "other", call="call_2"),
            after("bash", "ran", call="call_1"),
            after("bash", "again", call="call_1"),
        ]
    )

    assert _outputs(run.results) == ["other", "ran\n\n[playbook] check it", "again"]
    assert run.events == ["pre_tool_use"]  # bash is not registered for post_tool_use


def test_post_tool_use_context_appended_and_non_string_output_untouched(shim: ShimRepo) -> None:
    shim.respond("pre_tool_use", rendered("pre_tool_use", Decision.CONTEXT, context=("pre",)))
    shim.respond("post_tool_use", rendered("post_tool_use", Decision.CONTEXT, context=("lint",)))
    mcp_shaped = {"content": [{"type": "text", "text": "x"}]}
    long_output = "x" * 70_000

    run = shim.run(
        [
            before("edit", {"filePath": "a.py"}),
            after("edit", "edited", args={"filePath": "a.py"}),
            after("edit", mcp_shaped, call="call_2"),
            after("write", long_output, call="call_3"),
        ]
    )

    assert _outputs(run.results) == [
        "edited\n\n[playbook] pre\nlint",
        mcp_shaped,
        long_output + "\n\n[playbook] lint",
    ]
    assert run.events == ["pre_tool_use", "post_tool_use", "post_tool_use"]
    post, long_post = run.calls[1].payload, run.calls[2].payload
    assert post["hook_event_name"] == "PostToolUse" and post["tool_name"] == "Edit"
    assert post["tool_input"] == {"filePath": "a.py", "file_path": "a.py"}
    assert post["tool_response"] == {"output": "edited", "title": "t"}
    assert len(long_post["tool_response"]["output"]) == 65_536


@pytest.mark.parametrize(
    ("tools", "forwarded"),
    [(["bash"], ["bash"]), ("*", ["read", "github_create_issue", "bash"])],
    ids=["listed", "star"],
)
def test_wants_prefilter_skips_unregistered_tools(
    tmp_path: Path, tools: list[str] | Literal["*"], forwarded: list[str]
) -> None:
    shim = ShimRepo.create(tmp_path, {"pre_tool_use": {"timeout_ms": 5000, "tools": tools}})
    shim.pin()
    shim.respond("pre_tool_use", _NONE)

    run = shim.run(
        [
            before("read", {"filePath": "a"}),
            before("github_create_issue", {}),
            before("bash", {"command": "ls"}),
            after("edit", "done"),
            idle(),
        ]
    )

    names = {"read": "Read", "bash": "Bash", "github_create_issue": "github_create_issue"}
    assert [call.payload["tool_name"] for call in run.calls] == [names[t] for t in forwarded]
    assert set(run.events) == {"pre_tool_use"}  # no post_tool_use or stop key: never dispatched


def test_session_start_context_pushed_on_every_request(shim: ShimRepo) -> None:
    shim.respond("session_start", rendered("session_start", Decision.CONTEXT, context=("Brief",)))

    run = shim.run([transform(), transform(), transform("ses_2"), {"hook": "event", "input": {}}])

    assert _systems(run.results) == [["Brief"], ["Brief"], ["Brief"]]
    assert run.events == ["session_start", "session_start"]  # memoized per session
    assert run.calls[0].payload == {
        "hook_event_name": "SessionStart",
        "session_id": SESSION,
        "source": "startup",
        "cwd": str(shim.root),
    }


def test_session_idle_stop_result_carried_into_next_request(shim: ShimRepo) -> None:
    shim.respond("stop", rendered("stop", Decision.DENY, reason="ruff: 2 errors"))

    run = shim.run(
        [
            idle(kind="session.created"),
            idle(),
            transform(),
            transform(),
            respond_step("stop", rendered("stop", Decision.CONTEXT, context=("coverage fell",))),
            idle(),
            transform(),
            respond_step("stop", _NONE),
            idle(),
            transform(),
        ]
    )

    carried = _CARRY + "ruff: 2 errors"
    assert _systems(run.results) == [[carried], [carried], ["coverage fell"], []]
    assert run.events == ["stop", "session_start", "stop", "stop"]
    assert run.calls[0].payload == {
        "hook_event_name": "Stop",
        "session_id": SESSION,
        "stop_hook_active": False,
        "cwd": str(shim.root),
    }
    assert run.errors == []


def test_notices_pushed_once_per_request(shim: ShimRepo) -> None:
    shim.respond("pre_tool_use", rendered("pre_tool_use", user_notes=("pin is stale",)))
    calls = [before("bash", {"command": "ls"}, call=f"call_{n}") for n in range(6)]

    run = shim.run([*calls, transform(), transform(), transform("ses_2")])

    assert _systems(run.results) == [["pin is stale"] * 5, [], []]  # the last five, once


# --- finding the pin, the V2 stub ----------------------------------------------------------


@pytest.mark.parametrize("relative", [False, True], ids=["absolute", "relative"])
def test_linked_worktree_gitdir_file_resolves_pin(tmp_path: Path, relative: bool) -> None:
    shim = ShimRepo.create(tmp_path, _REG)
    (shim.root / ".git").rmdir()
    worktree_git = tmp_path / "main" / ".git" / "worktrees" / "linked"
    worktree_git.mkdir(parents=True)
    target = "../main/.git/worktrees/linked" if relative else str(worktree_git)
    (shim.root / ".git").write_text(f"gitdir: {target}\n", encoding="utf-8")
    shim.pin(git_dir=worktree_git)
    shim.respond("pre_tool_use", _NONE)

    run = shim.run([before("bash", {"command": "ls"})])

    assert (run.events, run.errors) == (["pre_tool_use"], [])


def test_v2_setup_stub_is_inert(shim: ShimRepo) -> None:
    run = shim.run([SETUP])

    assert run.results[0]["threw"] is None
    assert run.calls == []
    assert run.errors == [
        "[playbook] OpenCode V2 detected: lifecycle hooks inactive; AGENTS.md Guardrails are advisory"
    ]


# --- OQ-19: the fire-and-forget async audit dispatch -------------------------------------


def _await_calls(shim: ShimRepo, count: int, wait_s: float = 5.0) -> list[DispatchCall]:
    """The recorded dispatches once ``count`` exist with their stdin (a fired child is async)."""
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if sum(_recorded(d) for d in (shim.fake / "calls").iterdir()) >= count:
            return shim.calls()
        time.sleep(0.05)
    return shim.calls()


def _recorded(call_dir: Path) -> bool:
    stdin = call_dir / "stdin"
    return (call_dir / "argv").exists() and stdin.exists() and stdin.stat().st_size > 0


def test_async_audit_dispatch_fires_without_awaiting(tmp_path: Path) -> None:
    reg: dict[str, OpenCodeRegEntry] = {
        "session_start": {"timeout_ms": 5000},
        "post_tool_use": {"timeout_ms": 5000, "tools": [], "async": "*"},
    }
    shim = ShimRepo.create(tmp_path, reg)
    shim.pin()
    shim.hang("post_tool_use", 3)  # an awaited dispatch would hold the step for 3 s

    run = shim.run([after("read", "file text", args={"filePath": "a.md"})])

    (step,) = run.results
    assert step["threw"] is None and step["ms"] < 2000
    assert _outputs(run.results) == ["file text"]  # nothing awaited, nothing appended
    (call,) = _await_calls(shim, 1)
    root = str(shim.root)
    assert call.argv == [
        *RUNTIME_ARGV,
        "post_tool_use",
        "--harness",
        "opencode",
        "--project-dir",
        root,
        "--async",
    ]
    assert call.payload["tool_name"] == "Read"
    assert call.payload["tool_input"] == {"filePath": "a.md", "file_path": "a.md"}
