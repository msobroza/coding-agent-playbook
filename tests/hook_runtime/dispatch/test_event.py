"""The canonical event model (specs/prK-lifecycle-hooks.md §D.2.1).

The runtime may not import ``types`` or ``hooks`` (§D.1), so its
enumerations are re-declared in ``hook_runtime.dispatch.event``; these tests pin them to
the sync-side single sources so the two can never drift apart.
"""

from __future__ import annotations

import dataclasses
from importlib import metadata
from typing import get_args

import pytest

from coding_agent_playbook.artifacts import hook_schema
from coding_agent_playbook.hook_runtime.dispatch.event import (
    SESSION_ID_MAX_CHARS,
    STOP_MESSAGE_MAX_CHARS,
    TOOL_ERROR_MAX_CHARS,
    TOOL_OUTPUT_TAIL_CHARS,
    CanonicalEvent,
    ContentFragment,
    EventName,
    Harness,
    RepoInfo,
    ShellSource,
    StopInfo,
    ToolCall,
    ToolClass,
    ToolResponse,
    sanitize_session_id,
)
from coding_agent_playbook.hook_runtime.shell.parse import ShellConfig
from coding_agent_playbook.hooks.resolution.tables import (
    HOOK_CAPABLE_ADAPTERS,
    HOOK_EVENTS,
    TOOL_CLASS_NAMES,
)
from tests.engine_modules import engine_module
from tests.import_probe import new_modules_after

_NINE_EVENTS = [
    "session_start",
    "user_prompt_submit",
    "pre_tool_use",
    "post_tool_use",
    "post_tool_use_failure",
    "stop",
    "subagent_stop",
    "pre_compact",
    "session_end",
]


def _event(**overrides: object) -> CanonicalEvent:
    fields: dict[str, object] = {
        "name": EventName.PRE_TOOL_USE,
        "harness": Harness.CLAUDE_CODE,
        "session_id": "s-1",
        "cwd": "/repo",
        "project_dir": "/repo",
    }
    fields.update(overrides)
    return CanonicalEvent(**fields)  # type: ignore[arg-type]


# --- enumerations ---------------------------------------------------------------------


def test_event_name_values_are_the_nine_canonical_names() -> None:
    assert [member.value for member in EventName] == _NINE_EVENTS
    assert list(HOOK_EVENTS) == _NINE_EVENTS
    assert list(get_args(hook_schema.HookEvent)) == _NINE_EVENTS


def test_event_name_is_a_str_enum() -> None:
    assert EventName("stop") is EventName.STOP
    assert isinstance(EventName.STOP, str)
    assert f"{EventName.STOP}" == "stop"


def test_harness_values_equal_adapter_entry_point_names() -> None:
    adapters = {ep.name for ep in metadata.entry_points(group="coding_agent_playbook.adapters")}
    harnesses = {member.value for member in Harness}

    assert harnesses == {"claude_code", "opencode"}
    assert harnesses <= adapters
    assert harnesses == HOOK_CAPABLE_ADAPTERS


def test_tool_class_matches_types_tool_class() -> None:
    runtime = {member.value for member in ToolClass}

    assert set(get_args(hook_schema.ToolClass)) == runtime - {"other"}
    assert set(TOOL_CLASS_NAMES) == runtime - {"other"}


# --- dataclass shape -----------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [RepoInfo, StopInfo, ToolResponse, ContentFragment, ShellSource, ToolCall, CanonicalEvent],
    ids=lambda cls: cls.__name__,
)
def test_every_event_record_is_frozen_and_slotted(cls: type) -> None:
    params = cls.__dataclass_params__  # type: ignore[attr-defined]
    assert params.frozen is True
    assert "__slots__" in vars(cls)


def test_canonical_event_is_frozen_and_slotted() -> None:
    ev = _event()

    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.cwd = "/elsewhere"  # type: ignore[misc]
    assert not hasattr(ev, "__dict__")


def test_canonical_event_optional_fields_default_to_absent() -> None:
    ev = _event()

    assert (ev.repo, ev.tool, ev.prompt, ev.stop, ev.turn_id) == (None, None, None, None, None)
    assert (ev.unattended, ev.truncated, ev.raw_event_name) == (False, False, "")


def test_event_records_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        CanonicalEvent(EventName.STOP, Harness.OPENCODE, "s", "/r", "/r")  # type: ignore[call-arg]


# --- sanitization and caps ------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("abc-123_X.y", "abc-123_X.y"),
        ("a/b\\c d", "a_b_c_d"),
        ("café", "caf_"),
        ("..", "__"),
        (".", "_"),
        ("", ""),
        (None, ""),
        (42, ""),
        ("x" * 200, "x" * SESSION_ID_MAX_CHARS),
    ],
)
def test_session_id_sanitized_to_safe_charset_and_128_chars(raw: object, expected: str) -> None:
    assert sanitize_session_id(raw) == expected


def test_canonical_event_sanitizes_its_session_id_on_construction() -> None:
    assert _event(session_id="../../etc").session_id == ".._.._etc"
    assert _event(session_id="..").session_id == "__"


def test_stop_message_keeps_only_the_last_8000_chars() -> None:
    message = "a" * 10 + "b" * STOP_MESSAGE_MAX_CHARS

    info = StopInfo(stop_hook_active=True, last_assistant_message=message)

    assert info.last_assistant_message == "b" * STOP_MESSAGE_MAX_CHARS
    assert info.agent_transcript_path is None


def test_tool_response_error_is_capped_to_2000_chars() -> None:
    response = ToolResponse(ok=False, exit_code=2, error="e" * (TOOL_ERROR_MAX_CHARS + 50))

    assert response.error == "e" * TOOL_ERROR_MAX_CHARS
    assert ToolResponse(ok=True).error is None


def test_tool_response_output_keeps_its_last_8_kib() -> None:
    """The tail: a later segment's ``command not found`` lands there (§E.3 toolchain hint)."""
    response = ToolResponse(ok=True, output="o" * TOOL_OUTPUT_TAIL_CHARS + "tail")

    assert response.output is not None and response.output.endswith("tail")
    assert len(response.output) == TOOL_OUTPUT_TAIL_CHARS
    assert ToolResponse(ok=True).output is None


# --- ToolCall -------------------------------------------------------------------------


def test_tool_classes_default_to_the_primary_class() -> None:
    call = ToolCall(name="Edit", native_name="Edit", tool_class=ToolClass.EDIT)

    assert call.tool_classes == frozenset({ToolClass.EDIT})


def test_apply_patch_carries_both_edit_and_write_classes() -> None:
    call = ToolCall(
        name="apply_patch",
        native_name="apply_patch",
        tool_class=ToolClass.EDIT,
        tool_classes=frozenset({ToolClass.EDIT, ToolClass.WRITE}),
        content=(ContentFragment(path="a.py", field="patch", text="+x = 1"),),
    )

    assert call.tool_classes == {ToolClass.EDIT, ToolClass.WRITE}
    assert call.content[0].text == "+x = 1"


def test_primary_class_outside_tool_classes_is_rejected_with_the_values() -> None:
    with pytest.raises(ValueError, match=r"'read'.*'edit'"):
        ToolCall(
            name="Read",
            native_name="Read",
            tool_class=ToolClass.READ,
            tool_classes=frozenset({ToolClass.EDIT}),
        )


def test_raw_input_is_a_read_only_copy() -> None:
    source: dict[str, object] = {"file_path": "a.py"}
    call = ToolCall(name="Read", native_name="Read", tool_class=ToolClass.READ, raw_input=source)
    source["file_path"] = "changed.py"

    assert call.raw_input["file_path"] == "a.py"
    with pytest.raises(TypeError):
        call.raw_input["file_path"] = "b.py"  # type: ignore[index]


# --- the lazy shell parse -------------------------------------------------------------


def _bash(text: str, **source: object) -> ToolCall:
    return ToolCall(
        name="Bash",
        native_name="Bash",
        tool_class=ToolClass.SHELL,
        shell=ShellSource(text=text, **source),  # type: ignore[arg-type]
    )


def test_tool_call_shell_parse_is_lazy_and_memoized() -> None:
    call = _bash("cd sub && rm -rf x", cwd="/r")

    first = call.command

    assert first is not None
    assert first is call.command
    assert [(s.argv, s.cwd) for s in first.segments] == [
        (("cd", "sub"), "/r"),
        (("rm", "-rf", "x"), "/r/sub"),
    ]


def test_building_a_shell_call_imports_no_shell_parser() -> None:
    loaded = new_modules_after(
        "from coding_agent_playbook.hook_runtime.dispatch.event import "
        "ShellSource, ToolCall, ToolClass; "
        "ToolCall(name='Bash', native_name='Bash', tool_class=ToolClass.SHELL, "
        "shell=ShellSource(text='rm -rf x'))"
    )

    assert engine_module("coding_agent_playbook.hook_runtime.shell.parse") not in loaded
    assert "shlex" not in loaded


def test_a_non_shell_call_has_no_command() -> None:
    call = ToolCall(name="Read", native_name="Read", tool_class=ToolClass.READ)

    assert call.command is None
    assert call.with_shell_config(ShellConfig(wrapper_prefixes=("proxy",))) is call


def test_with_shell_config_reparses_with_the_new_config() -> None:
    call = _bash("proxy git status")
    configured = call.with_shell_config(ShellConfig(wrapper_prefixes=("proxy",)))

    assert call.command is not None
    assert configured.command is not None
    assert call.command.segments[0].argv[0] == "proxy"
    assert configured.command.segments[0].argv == ("git", "status")


def test_a_powershell_source_is_never_shlex_parsed() -> None:
    command = _bash("Remove-Item -Recurse x", kind="powershell").command

    assert command is not None
    assert (command.kind, command.segments) == ("powershell", ())
