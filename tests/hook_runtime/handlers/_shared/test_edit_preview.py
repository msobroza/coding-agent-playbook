"""``edit_preview.preview_after``: a file-tool call's result, simulated in memory (specs/prK-hook-pack.md §E.1).

control-plane-guard diffs a control-plane file before and after the edit, so
the "after" must follow the tool's own semantics: an Edit whose
``old_string`` is missing (or ambiguous without ``replace_all``) fails in
the tool, so there is no "after" (``None``: the guard asks). ``apply_patch``
and NotebookEdit are never simulated.
"""

from __future__ import annotations

from typing import Any

import pytest

from coding_agent_playbook.hook_runtime.dispatch.event import ToolCall, ToolClass
from coding_agent_playbook.hook_runtime.handlers._shared.edit_preview import preview_after


def _call(name: str, raw: dict[str, Any], *classes: ToolClass) -> ToolCall:
    primary = classes[0] if classes else ToolClass.EDIT
    return ToolCall(
        name=name,
        native_name=name,
        tool_class=primary,
        tool_classes=frozenset(classes or (primary,)),
        raw_input={"file_path": "/r/f", **raw},
    )


def _edit(old: str, new: str, **flags: Any) -> ToolCall:
    return _call("Edit", {"old_string": old, "new_string": new, **flags})


def test_edit_replace_once_and_replace_all() -> None:
    assert preview_after(_edit("a", "b"), "xa\n") == "xb\n"
    assert preview_after(_edit("a", "b", replace_all=True), "a a a") == "b b b"
    assert preview_after(_edit("a", "b"), "a a") is None  # ambiguous: the tool refuses


def test_multiedit_applies_in_order() -> None:
    edits = [
        {"old_string": '"a": 1', "new_string": '"a": 2'},
        {"old_string": '"a": 2', "new_string": '"a": 3'},
        {"old_string": "x", "new_string": "y", "replace_all": True},
    ]

    after = preview_after(_call("MultiEdit", {"edits": edits}), '{"a": 1, "x": "x"}')

    assert after == '{"a": 3, "y": "y"}'


def test_write_replaces_whole_content() -> None:
    write = _call("Write", {"content": '{"disableAllHooks": true}\n'}, ToolClass.WRITE)

    assert preview_after(write, '{"model": "opus"}\n') == '{"disableAllHooks": true}\n'
    assert preview_after(write, None) == '{"disableAllHooks": true}\n'


def test_missing_old_string_returns_none() -> None:
    assert preview_after(_edit("absent", "b"), "text") is None
    assert preview_after(_call("Edit", {"new_string": "b"}), "text") is None
    bad = _call("MultiEdit", {"edits": [{"old_string": "t", "new_string": "T"}, "oops"]})
    assert preview_after(bad, "text") is None
    assert preview_after(_edit("a", "b"), None) is None  # nothing to edit


def test_edit_with_empty_old_string_creates_a_missing_file() -> None:
    assert preview_after(_edit("", '{"a": 1}'), None) == '{"a": 1}'
    assert preview_after(_edit("", "x"), "existing") is None


def test_opencode_native_spellings_are_read() -> None:
    call = _call("Edit", {"oldString": "a", "newString": "b", "replaceAll": True})

    assert preview_after(call, "a-a") == "b-b"


@pytest.mark.parametrize(
    "call",
    [
        _call("apply_patch", {"patch_text": "*** Begin Patch"}, ToolClass.EDIT, ToolClass.WRITE),
        _call("NotebookEdit", {"new_source": "x"}, ToolClass.NOTEBOOK_EDIT),
        _call("Bash", {"command": "ls"}, ToolClass.SHELL),
    ],
    ids=["apply_patch", "notebook_edit", "bash"],
)
def test_apply_patch_and_notebook_edit_return_none(call: ToolCall) -> None:
    assert preview_after(call, "text") is None
