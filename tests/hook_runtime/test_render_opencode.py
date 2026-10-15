"""OpenCode V1 payload parsing and the ``playbook.hook.wire/1`` output (specs/prK-lifecycle-hooks.md §D.2.2, §D.3.5).

The shim (§C.3.2) sends a Claude-shaped payload carrying OpenCode's native
argument names plus the §C.3.3 snake_case aliases, and reads back exactly
``{"v", "decision", "reason", "context", "notice"}``; process exit 10 is the
deny signal, and only on ``pre_tool_use``.
"""

from __future__ import annotations

import itertools
import json
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_policy import TOOL_CLASS_NAMES
from coding_agent_playbook.hook_runtime.decision import CombinedResult, Decision
from coding_agent_playbook.hook_runtime.event import CanonicalEvent, EventName, ToolClass
from coding_agent_playbook.hook_runtime.harness import (
    DENY_EXIT,
    ContractFault,
    ForeignPayload,
    ParseContext,
    WireOutput,
)
from coding_agent_playbook.hook_runtime.harness.opencode import parse_opencode, render_opencode
from tests.hook_payloads import PROJECT_DIR, check_golden, fixture_repo_finder, hook_payload_cases

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.hook_payloads import HookPayloadCase

WIRE_KEYS = ["v", "decision", "reason", "context", "notice"]
#: The shim's ``TOOL`` map, verbatim from §C.3.2: native name -> Claude-shaped name.
SHIM_TOOL = {
    "bash": "Bash",
    "edit": "Edit",
    "write": "Write",
    "read": "Read",
    "glob": "Glob",
    "grep": "Grep",
    "webfetch": "WebFetch",
    "websearch": "WebSearch",
    "task": "Agent",
    "todowrite": "TodoWrite",
    "question": "AskUserQuestion",
    "skill": "Skill",
}
PATCH = (
    "*** Begin Patch\n"
    "*** Add File: src/new.py\n+def new():\n+    return 1\n"
    "*** Update File: src/old.py\n*** Move to: src/renamed.py\n@@\n-    return 0\n+    return 2\n"
    "*** Delete File: src/gone.py\n"
    "*** End Patch\n"
)


def _payload(tool: str = "Bash", tool_input: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "ses_1",
        "tool_use_id": "call_1",
        "tool_name": tool,
        "tool_input": {"command": "ls"} if tool_input is None else tool_input,
        "cwd": PROJECT_DIR,
    }


def _ctx(event: EventName = EventName.PRE_TOOL_USE, **fields: Any) -> ParseContext:
    values: dict[str, Any] = {
        "env": {},
        "project_dir": PROJECT_DIR,
        "find_repo": fixture_repo_finder,
        "platform": "linux",
    }
    values.update(fields)
    return ParseContext(argv_event=event, **values)


def _event(payload: dict[str, object], **ctx: Any) -> CanonicalEvent:
    outcome = parse_opencode(json.dumps(payload).encode(), _ctx(**ctx))
    assert isinstance(outcome, CanonicalEvent), outcome
    return outcome


def _wire(event: EventName, **fields: Any) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(render_opencode(event, CombinedResult(**fields)).stdout)
    return parsed


# --- goldens --------------------------------------------------------------------------


@pytest.mark.parametrize(("event", "case"), hook_payload_cases("opencode"))
def test_parse_render_golden(
    hook_payload: Callable[[str, str, str], HookPayloadCase], event: str, case: str
) -> None:
    golden = hook_payload("opencode", event, case)

    check_golden(golden, parse_opencode(golden.raw, golden.parse_context()), render_opencode)


# --- the wire -------------------------------------------------------------------------


def test_wire_v1_shape_and_fields() -> None:
    wire = render_opencode(
        EventName.PRE_TOOL_USE,
        CombinedResult(decision=Decision.CONTEXT, context=("a", "b"), user_notes=("n",)),
    )
    body = json.loads(wire.stdout)

    assert list(body) == WIRE_KEYS
    assert body == {
        "v": 1,
        "decision": "context",
        "reason": "",
        "context": ["a", "b"],
        "notice": "n",
    }
    assert wire.stdout.endswith("\n")
    assert (wire.stderr, wire.exit_code) == ("", 0)


def test_none_still_writes_a_complete_wire_object() -> None:
    assert _wire(EventName.POST_TOOL_USE) == {
        "v": 1,
        "decision": "none",
        "reason": "",
        "context": [],
        "notice": "",
    }


def test_exit_10_only_for_pre_tool_use_deny() -> None:
    for event, decision in itertools.product(EventName, Decision):
        wire = render_opencode(event, CombinedResult(decision=decision, reason="r", context=("c",)))
        body = json.loads(wire.stdout)

        assert list(body) == WIRE_KEYS
        expect_deny = event is EventName.PRE_TOOL_USE and decision in (Decision.DENY, Decision.ASK)
        assert (wire.exit_code == DENY_EXIT) == expect_deny, (event, decision)
        assert wire.exit_code in {0, DENY_EXIT}


def test_ask_never_reaches_the_wire() -> None:
    for event in EventName:
        body = _wire(event, decision=Decision.ASK, reason="sure?")

        assert body["decision"] in {"deny", "context", "none"}
        assert "ask" not in json.dumps(body)


def test_stop_result_returned_on_stdout_exit_0() -> None:
    wire = render_opencode(EventName.STOP, CombinedResult(decision=Decision.DENY, reason="RED"))

    assert json.loads(wire.stdout)["decision"] == "deny"
    assert json.loads(wire.stdout)["reason"] == "RED"
    assert wire.exit_code == 0


def test_notice_carries_user_notes() -> None:
    body = _wire(EventName.SESSION_START, user_notes=("deferred one", "deferred two"))

    assert body["notice"] == "deferred one\ndeferred two"
    assert body["decision"] == "none"


def test_wire_fields_are_capped() -> None:
    body = _wire(
        EventName.PRE_TOOL_USE,
        decision=Decision.CONTEXT,
        context=("x" * 3_000, "y" * 3_000, "dropped"),
        user_notes=("z" * 9_000,),
    )

    assert len("\n".join(body["context"])) == 4_000
    assert body["context"][1].endswith("…")
    assert len(body["context"]) == 2
    assert len(body["notice"]) <= 4_000


def test_context_is_dropped_under_a_deny_and_reason_under_context() -> None:
    deny = _wire(EventName.PRE_TOOL_USE, decision=Decision.DENY, reason="r", context=("c",))
    context = _wire(EventName.PRE_TOOL_USE, decision=Decision.CONTEXT, reason="r", context=("c",))

    assert (deny["context"], context["reason"]) == ([], "")


# --- parsing --------------------------------------------------------------------------


def test_apply_patch_envelope_paths_content_and_edit_write_classes() -> None:
    ev = _event(_payload("apply_patch", {"patchText": PATCH, "patch_text": PATCH}))
    tool = ev.tool

    assert tool is not None
    assert (tool.name, tool.native_name) == ("apply_patch", "apply_patch")
    assert tool.tool_class is ToolClass.EDIT
    assert tool.tool_classes == {ToolClass.EDIT, ToolClass.WRITE}
    expected = ["src/new.py", "src/old.py", "src/renamed.py", "src/gone.py"]
    assert [p.repo_rel for p in tool.paths] == expected
    assert [p.repo_rel for p in tool.write_paths] == expected
    assert [(c.path, c.field, c.text) for c in tool.content] == [
        ("src/new.py", "patch", "def new():\n    return 1"),
        ("src/renamed.py", "patch", "    return 2"),
    ]


def test_apply_patch_without_its_text_is_a_contract_fault() -> None:
    outcome = parse_opencode(json.dumps(_payload("apply_patch", {})).encode(), _ctx())

    assert isinstance(outcome, ContractFault)
    assert "patch_text" in outcome.problem


def test_alias_table_and_glob_path_never_aliased_to_file_path() -> None:
    native_only = _event(_payload("Edit", {"filePath": "src/a.py", "newString": "x = 1"}))
    glob = _event(_payload("Glob", {"pattern": "**/*.py", "path": "src", "include": "*.py"}))

    assert native_only.tool is not None
    assert [p.repo_rel for p in native_only.tool.write_paths] == ["src/a.py"]
    assert [c.text for c in native_only.tool.content] == ["x = 1"]
    assert glob.tool is not None
    assert [p.repo_rel for p in glob.tool.paths] == ["src"]
    assert glob.tool.write_paths == ()
    path_only_edit = parse_opencode(json.dumps(_payload("Edit", {"path": "src"})).encode(), _ctx())
    assert isinstance(path_only_edit, ContractFault)


def test_bash_workdir_is_the_segment_cwd() -> None:
    ev = _event(_payload("Bash", {"command": "rm -rf build", "workdir": "pkg"}))

    assert ev.tool is not None
    assert ev.tool.command is not None
    assert ev.tool.command.segments[0].cwd == f"{PROJECT_DIR}/pkg"


@pytest.mark.parametrize(
    ("tool_class", "native"),
    [
        (cls, name)
        for cls, names in TOOL_CLASS_NAMES.items()
        for name in names["opencode"]
        if name != "apply_patch"
    ],
)
def test_mapped_tool_names_restore_their_native_name(tool_class: str, native: str) -> None:
    tool_input: dict[str, object] = {"command": "ls", "file_path": "a.py"}
    ev = _event(_payload(SHIM_TOOL[native], tool_input))

    assert ev.tool is not None
    assert (ev.tool.native_name, ev.tool.tool_class) == (native, ToolClass(tool_class))


def test_unmapped_tools_pass_through_as_other() -> None:
    ev = _event(_payload("TodoWrite", {"todos": []}))

    assert ev.tool is not None
    assert (ev.tool.native_name, ev.tool.tool_class) == ("todowrite", ToolClass.OTHER)


def test_opencode_is_always_unattended_and_has_no_turn_id() -> None:
    ev = _event(_payload())

    assert ev.unattended is True
    assert (ev.turn_id, ev.permission_mode, ev.transcript_path) == (None, None, None)


def test_post_tool_use_carries_the_tool_response() -> None:
    payload = {
        **_payload("Edit", {"filePath": "a.py"}),
        "hook_event_name": "PostToolUse",
        "tool_response": {"output": "ok", "title": "a.py"},
    }
    ev = _event(payload, event=EventName.POST_TOOL_USE)

    assert ev.tool is not None
    assert ev.tool.response is not None
    assert ev.tool.response.ok is True


def test_project_dir_falls_back_to_the_payload_cwd() -> None:
    ev = _event(_payload(), project_dir=None)

    assert ev.project_dir == PROJECT_DIR


def test_no_project_dir_and_no_cwd_is_a_contract_fault() -> None:
    payload = {key: value for key, value in _payload().items() if key != "cwd"}
    outcome = parse_opencode(json.dumps(payload).encode(), _ctx(project_dir=None))

    assert isinstance(outcome, ContractFault)
    assert "project dir" in outcome.problem
    assert outcome.session_id == "ses_1"


def test_event_mismatch_is_foreign_and_bad_json_a_fault() -> None:
    mismatch = {**_payload(), "hook_event_name": "Stop"}

    assert isinstance(parse_opencode(json.dumps(mismatch).encode(), _ctx()), ForeignPayload)
    assert isinstance(parse_opencode(b"{", _ctx()), ContractFault)
    assert isinstance(parse_opencode(b"[1]", _ctx()), ContractFault)


def test_rendering_an_empty_result_is_never_empty_output() -> None:
    assert render_opencode(EventName.STOP, CombinedResult()) != WireOutput()
