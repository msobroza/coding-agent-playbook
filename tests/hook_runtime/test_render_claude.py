"""Claude Code payload parsing and wire rendering (specs/prK-lifecycle-hooks.md §D.2.2, §D.3.5).

The parser turns a Claude-shaped stdin payload into a ``CanonicalEvent``, or
reports it as foreign (inert, §C.5.2) or as a ``ContractFault`` (§D.4). The
renderer is the only producer of Claude output, from a closed key allowlist;
golden payloads under ``tests/fixtures/hook_payloads`` pin both directions.
"""

from __future__ import annotations

import itertools
import json
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_policy import HOOK_EVENTS, TOOL_CLASS_NAMES
from coding_agent_playbook.hook_runtime.caps import OutputCaps
from coding_agent_playbook.hook_runtime.decision import EVENT_DECISIONS, CombinedResult, Decision
from coding_agent_playbook.hook_runtime.event import CanonicalEvent, EventName, ToolClass
from coding_agent_playbook.hook_runtime.harness import (
    CLAUDE_EVENT_NAMES,
    DENY_EXIT,
    ContractFault,
    ForeignPayload,
    ParseContext,
    WireOutput,
)
from coding_agent_playbook.hook_runtime.harness.claude import parse_claude, render_claude
from tests.engine_modules import engine_module
from tests.hook_payloads import (
    PROJECT_DIR,
    check_golden,
    fixture_repo_finder,
    hook_payload_cases,
)
from tests.import_probe import new_modules_after

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.hook_payloads import HookPayloadCase

ENV = {"CLAUDE_PROJECT_DIR": PROJECT_DIR}
ALLOWED_KEYS = {
    "hookSpecificOutput",
    "hookEventName",
    "permissionDecision",
    "permissionDecisionReason",
    "additionalContext",
    "decision",
    "reason",
    "systemMessage",
}
FORBIDDEN_KEYS = {
    "allow",
    "defer",
    "updatedInput",
    "updatedToolOutput",
    "continue",
    "suppressOriginalPrompt",
    "initialUserMessage",
    "watchPaths",
    "reloadSkills",
    "sessionTitle",
}


def _payload(event: str = "PreToolUse", **fields: object) -> dict[str, object]:
    base: dict[str, object] = {
        "session_id": "s-1",
        "cwd": PROJECT_DIR,
        "hook_event_name": event,
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
    }
    base.update(fields)
    return {key: value for key, value in base.items() if value is not None}


def _ctx(event: EventName = EventName.PRE_TOOL_USE, **fields: Any) -> ParseContext:
    values: dict[str, Any] = {"env": ENV, "find_repo": fixture_repo_finder, "platform": "linux"}
    values.update(fields)
    return ParseContext(argv_event=event, **values)


def _parse(payload: dict[str, object], **ctx: Any) -> object:
    return parse_claude(json.dumps(payload).encode(), _ctx(**ctx))


def _event(payload: dict[str, object], **ctx: Any) -> CanonicalEvent:
    outcome = _parse(payload, **ctx)
    assert isinstance(outcome, CanonicalEvent), outcome
    return outcome


def _json(wire: WireOutput) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(wire.stdout)
    return parsed


# --- goldens --------------------------------------------------------------------------


@pytest.mark.parametrize(("event", "case"), hook_payload_cases("claude_code"))
def test_parse_render_golden(
    hook_payload: Callable[[str, str, str], HookPayloadCase], event: str, case: str
) -> None:
    golden = hook_payload("claude_code", event, case)

    check_golden(golden, parse_claude(golden.raw, golden.parse_context()), render_claude)


@pytest.mark.parametrize(("event", "case"), hook_payload_cases("foreign"))
def test_foreign_fixture_set_is_inert(
    hook_payload: Callable[[str, str, str], HookPayloadCase], event: str, case: str
) -> None:
    golden = hook_payload("foreign", event, case)

    check_golden(golden, parse_claude(golden.raw, golden.parse_context()), render_claude)


def test_the_ci_smoke_payload_exists(hook_payload: Callable[..., HookPayloadCase]) -> None:
    # §D.9's CI step pipes exactly this file into `playbook-hook simulate`.
    assert hook_payload("claude_code", "pre_tool_use", "bash_rm_root").expected["wire"][
        "exit_code"
    ] == (DENY_EXIT)


# --- rendering ------------------------------------------------------------------------


def test_pre_tool_use_deny_is_exit_10_json_and_stderr_reason() -> None:
    wire = render_claude(
        EventName.PRE_TOOL_USE, CombinedResult(decision=Decision.DENY, reason="no")
    )

    assert wire == WireOutput(
        stdout='{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
        '"permissionDecision":"deny","permissionDecisionReason":"no"}}\n',
        stderr="no\n",
        exit_code=DENY_EXIT,
    )
    assert wire.harness_exit_code == 2


def test_pre_tool_use_ask_is_exit_0_without_stderr() -> None:
    wire = render_claude(
        EventName.PRE_TOOL_USE, CombinedResult(decision=Decision.ASK, reason="ok?")
    )

    assert _json(wire)["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert (wire.stderr, wire.exit_code, wire.harness_exit_code) == ("", 0, 0)


@pytest.mark.parametrize(
    "event",
    [
        EventName.PRE_TOOL_USE,
        EventName.POST_TOOL_USE,
        EventName.POST_TOOL_USE_FAILURE,
        EventName.SESSION_START,
        EventName.USER_PROMPT_SUBMIT,
    ],
)
def test_context_renders_additional_context_under_the_claude_event_name(event: EventName) -> None:
    combined = CombinedResult(decision=Decision.CONTEXT, context=("a", "b"))

    assert _json(render_claude(event, combined)) == {
        "hookSpecificOutput": {
            "hookEventName": CLAUDE_EVENT_NAMES[event],
            "additionalContext": "a\nb",
        }
    }


@pytest.mark.parametrize("event", [EventName.STOP, EventName.SUBAGENT_STOP])
def test_stop_context_only_renders_system_message_never_additional_context(
    event: EventName,
) -> None:
    combined = CombinedResult(decision=Decision.CONTEXT, context=("warn",), user_notes=("note",))
    wire = render_claude(event, combined)

    assert _json(wire) == {"systemMessage": "warn\nnote"}
    assert "additionalContext" not in wire.stdout
    assert wire.exit_code == 0


@pytest.mark.parametrize("event", [EventName.STOP, EventName.SUBAGENT_STOP])
def test_stop_deny_is_decision_block_exit_0(event: EventName) -> None:
    wire = render_claude(event, CombinedResult(decision=Decision.DENY, reason="RED"))

    assert _json(wire) == {"decision": "block", "reason": "RED"}
    assert (wire.stderr, wire.exit_code) == ("", 0)


@pytest.mark.parametrize("decision", [Decision.DENY, Decision.ASK])
def test_user_prompt_submit_deny_is_decision_block(decision: Decision) -> None:
    wire = render_claude(
        EventName.USER_PROMPT_SUBMIT, CombinedResult(decision=decision, reason="r")
    )

    assert _json(wire) == {"decision": "block", "reason": "r"}
    assert wire.exit_code == 0


def test_none_without_notes_writes_nothing_and_notes_become_a_system_message() -> None:
    assert render_claude(EventName.PRE_TOOL_USE, CombinedResult()) == WireOutput()
    notes = CombinedResult(user_notes=("one", "two"))

    assert _json(render_claude(EventName.SESSION_END, notes)) == {"systemMessage": "one\ntwo"}


def test_an_empty_deny_reason_still_says_why() -> None:
    wire = render_claude(EventName.PRE_TOOL_USE, CombinedResult(decision=Decision.DENY))

    assert _json(wire)["hookSpecificOutput"]["permissionDecisionReason"]
    assert wire.stderr.strip()


def test_every_output_field_is_capped() -> None:
    long = "x" * 9_000
    combined = CombinedResult(
        decision=Decision.DENY, reason=long, context=(long,), user_notes=(long,)
    )
    for event in EventName:
        body = render_claude(event, combined).stdout
        for value in _strings(json.loads(body) if body else {}):
            assert len(value) <= OutputCaps.FIELD_CHARS


def test_closed_key_allowlist_over_generated_results() -> None:
    texts = ("", "line\nline2")
    for event, decision, reason, context, notes in itertools.product(
        EventName, Decision, texts, ((), ("c",)), ((), ("n",))
    ):
        combined = CombinedResult(
            decision=decision, reason=reason, context=context, user_notes=notes
        )
        wire = render_claude(event, combined)
        body = json.loads(wire.stdout) if wire.stdout else {}
        keys = set(_keys(body))

        assert keys <= ALLOWED_KEYS, (event, decision, keys)
        assert not keys & FORBIDDEN_KEYS
        assert body.get("hookSpecificOutput", {}).get("permissionDecision") in {None, "deny", "ask"}
        assert body.get("decision") in {None, "block"}
        assert wire.exit_code in {0, DENY_EXIT}
        assert (wire.exit_code == DENY_EXIT) == (
            event is EventName.PRE_TOOL_USE and decision is Decision.DENY
        )
        assert not wire.stderr or wire.exit_code == DENY_EXIT


def _keys(value: object) -> list[str]:
    if isinstance(value, dict):
        return [*value, *itertools.chain.from_iterable(_keys(v) for v in value.values())]
    return []


def _strings(value: object) -> list[str]:
    if isinstance(value, dict):
        return list(itertools.chain.from_iterable(_strings(v) for v in value.values()))
    return [value] if isinstance(value, str) else []


# --- foreign payloads and contract faults ---------------------------------------------


@pytest.mark.parametrize(
    ("payload", "env", "marker"),
    [
        (_payload("PostToolUse"), ENV, "event_mismatch"),
        (_payload(session_id=None), ENV, "missing_session_id"),
        (_payload(session_id=""), ENV, "missing_session_id"),
        (_payload(cursor_version="3.24.9"), ENV, "foreign_marker:cursor_version"),
        (_payload(conversation_id="c-1"), ENV, "foreign_marker:conversation_id"),
        (_payload(timestamp="2026-10-14T10:30:00Z"), ENV, "timestamp"),
        (_payload(), {}, "claude_project_dir_unset"),
        (_payload(), {"CLAUDE_PROJECT_DIR": ""}, "claude_project_dir_unset"),
    ],
)
def test_foreign_payload_is_inert(
    payload: dict[str, object], env: dict[str, str], marker: str
) -> None:
    outcome = _parse(payload, env=env)

    assert outcome == ForeignPayload(
        event=EventName.PRE_TOOL_USE, marker=marker, session_id=_sid(payload)
    )


def _sid(payload: dict[str, object]) -> str:
    raw = payload.get("session_id")
    return raw if isinstance(raw, str) else ""


def test_leading_bom_is_stripped() -> None:
    raw = b"\xef\xbb\xbf" + json.dumps(_payload()).encode()

    assert isinstance(parse_claude(raw, _ctx()), CanonicalEvent)


@pytest.mark.parametrize("raw", [b'{"session_id": "s', b"\xff\xfe{}", b"", b"   "])
def test_malformed_json_after_foreign_check_is_contract_fault(raw: bytes) -> None:
    outcome = parse_claude(raw, _ctx())

    assert isinstance(outcome, ContractFault)
    assert "not valid JSON" in outcome.problem
    assert isinstance(parse_claude(raw, _ctx(env={})), ForeignPayload)


@pytest.mark.parametrize("raw", [b"[]", b'"PreToolUse"', b"42"])
def test_a_non_object_payload_is_contract_fault(raw: bytes) -> None:
    outcome = parse_claude(raw, _ctx())

    assert isinstance(outcome, ContractFault)
    assert "JSON object" in outcome.problem


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        ({"tool_name": None}, "tool_name"),
        ({"tool_name": 7}, "tool_name"),
        ({"tool_input": None}, "tool_input"),
        ({"tool_input": ["ls"]}, "tool_input"),
        ({"tool_input": {}}, "tool_input.command"),
        ({"tool_name": "Edit", "tool_input": {"path": "a.py"}}, "tool_input.file_path"),
    ],
)
def test_missing_required_tool_fields_are_contract_faults(
    fields: dict[str, object], problem: str
) -> None:
    outcome = _parse(_payload("PreToolUse", **fields))

    assert isinstance(outcome, ContractFault)
    assert problem in outcome.problem
    assert outcome.session_id == "s-1"


def test_a_truncated_stdin_that_still_parses_is_flagged() -> None:
    assert _event(_payload(), truncated=True).truncated is True


def test_a_truncated_stdin_that_no_longer_parses_says_so() -> None:
    outcome = parse_claude(b'{"session_id": "s', _ctx(truncated=True))

    assert isinstance(outcome, ContractFault)
    assert "16 MiB" in outcome.problem


def test_oversized_stop_message_and_tool_error_are_capped() -> None:
    stop = _event(
        _payload("Stop", last_assistant_message="m" * 9_000 + "END"), event=EventName.STOP
    )
    failure = _event(
        _payload("PostToolUseFailure", error="Exit code 3\n" + "e" * 5_000),
        event=EventName.POST_TOOL_USE_FAILURE,
    )

    assert stop.stop is not None
    assert stop.stop.last_assistant_message.endswith("END")
    assert len(stop.stop.last_assistant_message) == 8_000
    assert failure.tool is not None
    assert failure.tool.response is not None
    assert failure.tool.response.exit_code == 3
    assert len(failure.tool.response.error or "") == 2_000


# --- normalization details ------------------------------------------------------------


def test_claude_event_names_match_hook_policy() -> None:
    assert {e.value: name for e, name in CLAUDE_EVENT_NAMES.items()} == {
        event: spec.claude_name for event, spec in HOOK_EVENTS.items()
    }


@pytest.mark.parametrize(
    ("tool_class", "name"),
    [
        (cls, name)
        for cls, names in TOOL_CLASS_NAMES.items()
        for name in names["claude_code"]
        if "*" not in name
    ],
)
def test_claude_tool_names_classify_as_their_hook_policy_class(tool_class: str, name: str) -> None:
    tool_input = {"command": "ls", "file_path": "a.py", "notebook_path": "n.ipynb"}
    ev = _event(_payload(tool_name=name, tool_input=tool_input))

    assert ev.tool is not None
    assert ev.tool.tool_class is ToolClass(tool_class)
    assert ev.tool.native_name == name


def test_mcp_server_falls_back_to_the_tool_name() -> None:
    ev = _event(_payload(tool_name="mcp__linear__list_issues", tool_input={}))

    assert ev.tool is not None
    assert (ev.tool.tool_class, ev.tool.mcp_server) == (ToolClass.MCP, "linear")


@pytest.mark.parametrize(
    ("env", "mode", "expected"),
    [({}, None, False), ({"CI": "true"}, None, True), ({}, "dontAsk", True)],
)
def test_unattended_is_computed_at_parse_time(
    env: dict[str, str], mode: str | None, expected: bool
) -> None:
    ev = _event(_payload(permission_mode=mode), env={**ENV, **env})

    assert ev.unattended is expected


def test_project_dir_argument_wins_over_the_env() -> None:
    ev = _event(_payload(), project_dir="/playbook-fixture/other")

    assert ev.project_dir == "/playbook-fixture/other"
    assert ev.repo is not None
    assert ev.repo.worktree_root == "/playbook-fixture/other"


def test_relative_tool_paths_resolve_against_the_event_cwd() -> None:
    ev = _event(
        _payload(cwd=f"{PROJECT_DIR}/src", tool_name="Read", tool_input={"file_path": "a.py"})
    )

    assert ev.tool is not None
    assert [p.repo_rel for p in ev.tool.paths] == ["src/a.py"]
    assert ev.tool.write_paths == ()


def test_an_edit_event_parse_never_loads_the_shell_parser() -> None:
    payload = json.dumps(_payload(tool_name="Edit", tool_input={"file_path": "a.py"}))
    loaded = new_modules_after(
        "from coding_agent_playbook.hook_runtime.harness.claude import parse_claude, render_claude; "
        "from coding_agent_playbook.hook_runtime.harness import ParseContext; "
        "from coding_agent_playbook.hook_runtime.event import EventName; "
        f"parse_claude({payload!r}.encode(), ParseContext(argv_event=EventName.PRE_TOOL_USE, "
        f"env={ENV!r}))"
    )
    engine = {m for m in loaded if m.startswith("coding_agent_playbook.")}

    runtime = engine_module("coding_agent_playbook.hook_runtime")
    assert all(m.startswith(runtime) for m in engine), engine
    assert engine_module("coding_agent_playbook.hook_runtime.shell.parse") not in loaded
    assert not {"tomllib", "argparse", "importlib.metadata", "jinja2", "yaml", "shlex"} & set(
        loaded
    )


def test_every_event_supports_none() -> None:
    assert all(Decision.NONE in allowed for allowed in EVENT_DECISIONS.values())
