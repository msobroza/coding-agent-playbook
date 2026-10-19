"""The managed ``.claude/settings.json`` merge (specs/prK-lifecycle-hooks.md §C.2.4-§C.2.8).

``merge_managed_entries`` is pure (text in, ``MergeResult`` out); file I/O goes
through ``write_settings`` and an injected ``SettingsIO``, so the race re-read
is driven by :class:`FakeSettingsIO`.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.adapters.claude_code.settings._json_spans import (
    JsonSpanIndex,
    apply_splices,
    line_col,
)
from coding_agent_playbook.adapters.claude_code.settings.managed_merge import (
    CLAUDE_SETTINGS_PATH,
    MANAGED_STRING_POINTERS,
    DesiredGroup,
    MergeResult,
    SettingsMergeError,
    merge_managed_entries,
    scoped_lock_entry,
    write_settings,
)
from coding_agent_playbook.lockfile.canonical_json import canonical_json
from coding_agent_playbook.lockfile.model import LockEntry, compute_hash
from tests.import_probe import new_modules_after

if TYPE_CHECKING:
    from collections.abc import Mapping

PATH = CLAUDE_SETTINGS_PATH
LAUNCH = (
    'sh "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}'
    '/.claude/hooks/playbook/launch.sh"'
)


def _group(event: str, timeout: int, matcher: str | None = None) -> dict[str, Any]:
    handler = {
        "type": "command",
        "command": f"{LAUNCH} dispatch {event} --harness claude_code",
        "timeout": timeout,
    }
    return {**({"matcher": matcher} if matcher else {}), "hooks": [handler]}


OURS = _group("stop", 5)  # what this sync wants
OLD = _group("stop", 9)  # what the previous sync rendered (recorded in the prior lock)
EDITED = _group("stop", 1)  # a hand-edited managed group (launcher token, unknown hash)
USER = {"hooks": [{"type": "command", "command": "echo user"}]}
MIXED = {"hooks": [OURS["hooks"][0], USER["hooks"][0]]}
PRE = _group("pre_tool_use", 32, matcher="Bash|Edit")


def _prior(*elements: object, event: str = "Stop") -> list[LockEntry]:
    artifact = "registration:" + re.sub(r"(?<!^)([A-Z])", r"_\1", event).lower()
    return [scoped_lock_entry(PATH, f"/hooks/{event}", e, artifact_id=artifact) for e in elements]


def _want(*groups: dict[str, Any], event: str = "Stop") -> dict[str, list[DesiredGroup]]:
    artifact = "registration:" + re.sub(r"(?<!^)([A-Z])", r"_\1", event).lower()
    return {event: [DesiredGroup(artifact, g) for g in groups]}


def _doc(*elements: object, event: str = "Stop", top: Mapping[str, object] | None = None) -> str:
    return json.dumps({**(top or {}), "hooks": {event: list(elements)}}, indent=2) + "\n"


def _parsed(result: MergeResult) -> dict[str, Any]:
    assert result.text is not None
    loaded: dict[str, Any] = json.loads(result.text.removeprefix("\ufeff"))
    return loaded


@dataclass
class FakeSettingsIO:
    """Serves ``reads`` in order (the last one repeats) and records every write."""

    reads: list[bytes | None]
    writes: list[tuple[Path, bytes]] = field(default_factory=list)
    read_count: int = 0

    def read_bytes(self, path: Path) -> bytes | None:
        self.read_count += 1
        return self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]

    def write_bytes(self, path: Path, data: bytes) -> None:
        self.writes.append((path, data))


# --- the §C.2.4 decision table ------------------------------------------------------


@dataclass(frozen=True)
class _Row:
    before: list[dict[str, Any]]
    prior: list[dict[str, Any]]
    want: dict[str, Any] | None
    after: list[dict[str, Any]] | None
    warning: str | None = None
    note: str | None = None


_DECISIONS = {
    "want_equals_owned_noop": _Row([USER, OURS], [OURS], OURS, [USER, OURS]),
    "want_equals_suspect_noop": _Row([OURS, USER], [], OURS, [OURS, USER]),
    "extra_copies_deleted_with_warning": _Row(
        [OURS, USER, OURS], [OURS], OURS, [OURS, USER], warning="duplicate"
    ),
    "differs_replaces_first_deletes_rest": _Row([USER, OLD, EDITED], [OLD], OURS, [USER, OURS]),
    "suspect_differs_restored_with_warning": _Row(
        [EDITED, USER], [OLD], OURS, [OURS, USER], warning="edited by hand; restored"
    ),
    "absent_appended_and_reported_readded": _Row(
        [USER], [OURS], OURS, [USER, OURS], note="re-added"
    ),
    "want_absent_deletes_owned_and_suspect": _Row([OLD, USER, EDITED], [OLD], None, [USER]),
}


@pytest.mark.parametrize("row", list(_DECISIONS.values()), ids=list(_DECISIONS))
def test_decision_table(row: _Row) -> None:
    text = _doc(*row.before, top={"model": "opus"})
    desired = _want(row.want) if row.want is not None else {}
    result = merge_managed_entries(text, desired, _prior(*row.prior))

    assert _parsed(result)["hooks"].get("Stop") == row.after
    assert result.changed is (row.after != row.before)
    assert result.text == text or result.changed
    assert _single_match(result.warnings, row.warning)
    assert _single_match(result.notes, row.note)


def _single_match(lines: tuple[str, ...], fragment: str | None) -> bool:
    """No line when ``fragment`` is None, else exactly one line, containing it."""
    if fragment is None:
        return lines == ()
    return len(lines) == 1 and fragment in lines[0] and lines[0].startswith(f"{PATH} hooks.Stop")


def test_decision_table_mixed_group_errors_naming_hooks_e_i() -> None:
    text = _doc(USER, MIXED)
    with pytest.raises(SettingsMergeError) as caught:
        merge_managed_entries(text, _want(OURS), _prior(OURS))
    offset = JsonSpanIndex.build(text).locate(("hooks", "Stop", 1))
    assert offset is not None
    assert (caught.value.line, caught.value.col) == line_col(text, offset.start)
    assert "hooks.Stop[1]" in caught.value.message
    assert "move your handler to its own matcher group" in caught.value.message


def test_restore_is_silent_when_the_prior_lock_has_no_entry_for_the_event() -> None:
    """With a gitignored lockfile, a teammate's older render is not a hand edit."""
    result = merge_managed_entries(_doc(EDITED, USER), _want(OURS), [])
    assert _parsed(result)["hooks"]["Stop"] == [OURS, USER]
    assert result.warnings == ()


def test_suspect_needs_every_handler_to_be_the_launcher() -> None:
    no_handlers = {"matcher": "", "hooks": []}
    result = merge_managed_entries(_doc(no_handlers), _want(OURS), [])
    assert _parsed(result)["hooks"]["Stop"] == [no_handlers, OURS]


def test_counts_feed_the_summary_line() -> None:
    text = _doc(OLD, EDITED, USER)
    result = merge_managed_entries(text, _want(OURS), _prior(OLD))
    assert (result.updated, result.removed) == (1, 1)


def test_new_event_keys_are_appended_in_desired_order() -> None:
    text = json.dumps({"hooks": {"SessionStart": [USER]}}, indent=2)
    desired = {**_want(PRE, event="PreToolUse"), **_want(OURS)}
    result = merge_managed_entries(text, desired, [])
    assert list(_parsed(result)["hooks"]) == ["SessionStart", "PreToolUse", "Stop"]


def test_empty_event_array_and_empty_hooks_object_removed() -> None:
    text = _doc(OURS, top={"model": "opus"})
    assert merge_managed_entries(text, {}, _prior(OURS)).text == '{\n  "model": "opus"\n}\n'

    both = json.dumps({"hooks": {"PreToolUse": [USER], "Stop": [OURS]}}, indent=2)
    assert _parsed(merge_managed_entries(both, {}, _prior(OURS))) == {
        "hooks": {"PreToolUse": [USER]}
    }


def test_removing_the_last_managed_element_keeps_the_file() -> None:
    result = merge_managed_entries(_doc(OURS), {}, _prior(OURS))
    assert (result.text, result.changed) == ("{}\n", True)


# --- byte stability -------------------------------------------------------------------

_USER_KEYS = {"permissions": {"deny": ["Read(./.env)"]}, "env": {"GREETING": "héllo ☃"}}
_REORDERED = {"hooks": [dict(reversed(list(OURS["hooks"][0].items())))]}


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(json.dumps({**_USER_KEYS, "hooks": {"Stop": [OURS]}}, indent=4), id="indent4"),
        pytest.param(json.dumps({**_USER_KEYS, "hooks": {"Stop": [OURS]}}, indent="\t"), id="tabs"),
        pytest.param(_doc(OURS, top=_USER_KEYS).replace("\n", "\r\n"), id="crlf"),
        pytest.param("\ufeff" + _doc(OURS, top=_USER_KEYS), id="bom"),
        pytest.param(
            json.dumps({**_USER_KEYS, "hooks": {"Stop": [OURS]}}, indent=2, ensure_ascii=True),
            id="unicode_escapes",
        ),
        pytest.param(
            json.dumps({"zeta": 1, "alpha": {"b": 2, "a": 1}, "hooks": {"Stop": [OURS]}}),
            id="user_key_order",
        ),
        pytest.param(_doc(_REORDERED, top=_USER_KEYS), id="managed_group_key_order"),
    ],
)
def test_noop_leaves_bytes_identical(text: str) -> None:
    result = merge_managed_entries(text, _want(OURS), _prior(OURS))
    assert (result.text, result.changed) == (text, False)

    io = FakeSettingsIO([text.encode("utf-8")])
    write_settings(Path("s.json"), Path("s.json"), _merge_fn(_want(OURS), _prior(OURS)), io=io)
    assert io.writes == []


def test_splice_keeps_every_byte_outside_edited_spans() -> None:
    managed = json.dumps(OLD)
    text = (
        '\ufeff{\r\n    "env": {"A": "\\u00e9\\n"},   \r\n    "hooks": {\r\n'
        '        "Stop": [\r\n            {"hooks": [{"type": "command", "command": "echo user"}]},\r\n'
        f"            {managed},\r\n"
        '            {"matcher": "",   "hooks": []}\r\n        ]\r\n    },\r\n'
        '    "z": [1,2 ,3]\r\n}'
    )
    start = text.index(managed)
    result = merge_managed_entries(text, _want(OURS), _prior(OLD))

    assert result.text is not None
    assert result.text.startswith(text[:start])
    assert result.text.endswith(text[start + len(managed) :])
    assert _parsed(result)["hooks"]["Stop"][1] == OURS


# --- strict parse and shape errors ----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "line", "col"),
    [
        pytest.param('{\n  "a": 1,\n  "a": 2\n}', 3, 3, id="duplicate_key"),
        pytest.param('{\n  "a": NaN\n}', 2, 8, id="nan"),
        pytest.param('{"a": [1,\n  Infinity]}', 2, 3, id="infinity"),
        pytest.param('{\n  // note\n  "a": 1\n}', 2, 3, id="line_comment"),
        # CPython 3.12 and 3.13 report a trailing comma at different columns.
        pytest.param('{\n  "a": 1,\n  "b": 2,\n}', None, None, id="trailing_comma"),
    ],
)
def test_strict_parse_rejects(text: str, line: int | None, col: int | None) -> None:
    with pytest.raises(SettingsMergeError) as caught:
        merge_managed_entries(text, _want(OURS), [])
    error = caught.value
    if line is not None:
        assert (error.line, error.col) == (line, col)
    assert str(error) == f"{PATH}:{error.line}:{error.col}: {error.message}"
    assert error.path == PATH

    io = FakeSettingsIO([text.encode("utf-8")])
    with pytest.raises(SettingsMergeError):
        write_settings(Path("s.json"), Path("s.json"), _merge_fn(_want(OURS), []), io=io)
    assert io.writes == []


@pytest.mark.parametrize(
    ("text", "position", "fragments"),
    [
        pytest.param(
            "[1, 2]", (1, 1), ("top level", "object", "array [1, 2]"), id="top_level_array"
        ),
        pytest.param(
            '{"hooks": ["x"]}',
            (1, 11),
            ("hooks must be an object", 'array ["x"]'),
            id="hooks_not_object",
        ),
        pytest.param(
            '{"hooks": {\n  "Stop": {"a": 1}}}',
            (2, 11),
            ("hooks.Stop must be an array", 'object {"a": 1}'),
            id="event_not_array",
        ),
        pytest.param(
            '{"hooks": {"Stop": [{}, "echo"]}}',
            (1, 25),
            ("hooks.Stop[1] must be a matcher-group object", 'string "echo"'),
            id="element_not_object",
        ),
    ],
)
def test_shape_error_names_value_and_expected_shape(
    text: str, position: tuple[int, int], fragments: tuple[str, ...]
) -> None:
    with pytest.raises(SettingsMergeError) as caught:
        merge_managed_entries(text, {}, [])
    assert (caught.value.line, caught.value.col) == position
    for fragment in fragments:
        assert fragment in caught.value.message


def test_managed_string_parent_of_wrong_shape_is_an_error() -> None:
    with pytest.raises(SettingsMergeError, match=r"permissions must be an object.*string \"x\""):
        merge_managed_entries('{"permissions": "x"}', {}, [], strings={"/permissions/deny": ["a"]})


def test_unmanaged_pointer_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"'/env/PATH'.*expected one of"):
        merge_managed_entries("{}", {}, [], strings={"/env/PATH": ["x"]})


# --- absent, empty and corrupted documents ---------------------------------------------


def test_absent_file_creates_two_space_lf_document() -> None:
    result = merge_managed_entries(None, _want(OURS), [])
    expected = json.dumps({"hooks": {"Stop": [OURS]}}, indent=2, ensure_ascii=False) + "\n"
    assert (result.text, result.changed) == (expected, True)

    nothing = merge_managed_entries(None, {}, [])
    assert (nothing.text, nothing.changed, nothing.entries) == (None, False, ())


def test_whitespace_only_treated_as_empty_object_with_warning() -> None:
    result = merge_managed_entries(" \n\t\n", _want(OURS), [])
    assert _parsed(result) == {"hooks": {"Stop": [OURS]}}
    assert result.text == json.dumps(_parsed(result), indent=2) + "\n"
    assert any("only whitespace" in w for w in result.warnings)

    untouched = merge_managed_entries(" \n", {}, [])
    assert (untouched.text, untouched.changed) == (" \n", False)
    assert any("only whitespace" in w for w in untouched.warnings)


@pytest.mark.parametrize(
    "corrupt",
    [
        pytest.param(
            lambda text: text.replace('"timeout": 5', '"timeout": 6'), id="meaning_changed"
        ),
        pytest.param(lambda text: text.replace('"timeout": 5', '"timeout": 5,'), id="invalid_json"),
    ],
)
def test_self_check_rejects_corrupted_splice(corrupt: Any) -> None:
    def splicer(text: str, splices: Any) -> str:
        result: str = corrupt(apply_splices(text, splices))
        return result

    with pytest.raises(SettingsMergeError, match="self-check"):
        merge_managed_entries(_doc(USER), _want(OURS), [], splicer=splicer)


# --- the race re-read and the byte write ----------------------------------------------


def _merge_fn(desired: Any, prior: list[LockEntry]) -> Any:
    return lambda text: merge_managed_entries(text, desired, prior)


def test_race_reread_redoes_once_then_fails() -> None:
    first = _doc(USER).encode()
    approval = json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"Stop": [USER]}})
    io = FakeSettingsIO([first, approval.encode(), approval.encode()])
    result = write_settings(Path("s.json"), Path("s.json"), _merge_fn(_want(OURS), []), io=io)

    assert len(io.writes) == 1
    written = json.loads(io.writes[0][1])
    assert written["permissions"] == {"allow": ["Bash(ls)"]}  # the approval survived the redo
    assert written["hooks"]["Stop"] == [USER, OURS]
    assert result.changed

    racing = FakeSettingsIO([first, approval.encode(), b"{}"])
    with pytest.raises(SettingsMergeError, match="changed while"):
        write_settings(Path("s.json"), Path("s.json"), _merge_fn(_want(OURS), []), io=racing)
    assert racing.writes == []


def test_check_mode_reads_the_real_file_and_writes_the_scratch_target() -> None:
    io = FakeSettingsIO([_doc(USER).encode(), b"never read"])
    write_settings(Path("repo/s.json"), Path("scratch/s.json"), _merge_fn(_want(OURS), []), io=io)
    assert io.read_count == 1
    assert [path for path, _ in io.writes] == [Path("scratch/s.json")]


def test_write_keeps_crlf_bytes_and_bom(tmp_path: Path) -> None:
    target = tmp_path / ".claude" / "settings.json"
    target.parent.mkdir()
    target.write_bytes(("\ufeff" + _doc(USER)).replace("\n", "\r\n").encode("utf-8"))
    write_settings(target, target, _merge_fn(_want(OURS), []))

    data = target.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf{\r\n")
    assert b"\n" not in data.replace(b"\r\n", b"")
    assert json.loads(data.decode("utf-8-sig"))["hooks"]["Stop"] == [USER, OURS]


def test_absent_file_is_created_and_never_written_when_nothing_is_desired(tmp_path: Path) -> None:
    target = tmp_path / ".claude" / "settings.json"
    assert not write_settings(target, target, _merge_fn({}, [])).changed
    assert not target.parent.exists()
    write_settings(target, target, _merge_fn(_want(OURS), []))
    assert json.loads(target.read_bytes()) == {"hooks": {"Stop": [OURS]}}


def test_invalid_utf8_is_a_settings_error() -> None:
    io = FakeSettingsIO([b'{\n  "a": "\xff"\n}'])
    with pytest.raises(SettingsMergeError, match="UTF-8") as caught:
        write_settings(Path("s.json"), Path("s.json"), _merge_fn({}, []), io=io)
    assert (caught.value.line, caught.value.col) == (2, 9)


# --- managed string arrays (§C.2.8, §E.4/§E.5) ------------------------------------------


def _at(doc: dict[str, Any], pointer: str) -> Any:
    node: Any = doc
    for key in pointer.strip("/").split("/"):
        node = node[key]
    return node


def _with_array(pointer: str, items: list[object]) -> str:
    doc: dict[str, Any] = {"model": "x"}
    node = doc
    keys = pointer.strip("/").split("/")
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = items
    return json.dumps(doc, indent=2) + "\n"


@pytest.mark.parametrize(
    "pointer",
    [
        pytest.param("/permissions/allow", id="permissions_allow"),
        pytest.param("/permissions/deny", id="permissions_deny"),
        pytest.param("/sandbox/filesystem/denyRead", id="sandbox_denyRead"),
        pytest.param("/sandbox/network/allowedDomains", id="sandbox_allowedDomains"),
    ],
)
def test_managed_strings_append_ours_delete_ours_keep_user_create_parents(pointer: str) -> None:
    created = merge_managed_entries('{\n  "model": "x"\n}\n', {}, [], strings={pointer: ["a", "b"]})
    assert _at(_parsed(created), pointer) == ["a", "b"]
    last = pointer.rsplit("/", 1)[1]
    assert [(e.scope, e.artifact_id) for e in created.entries] == [
        (f"json:{pointer}", f"permission:{last}:a"),
        (f"json:{pointer}", f"permission:{last}:b"),
    ]

    with_user = _with_array(pointer, ["user", "a", "b"])
    updated = merge_managed_entries(with_user, {}, created.entries, strings={pointer: ["b", "c"]})
    assert _at(_parsed(updated), pointer) == ["user", "b", "c"]

    disabled = merge_managed_entries(updated.text, {}, updated.entries)
    assert _at(_parsed(disabled), pointer) == ["user"]

    only_ours = merge_managed_entries(created.text, {}, created.entries)
    assert _parsed(only_ours) == {"model": "x"}


def test_user_copy_of_a_wanted_string_is_neither_duplicated_nor_claimed() -> None:
    text = _with_array("/permissions/deny", ["Read(./.env)"])
    result = merge_managed_entries(text, {}, [], strings={"/permissions/deny": ["Read(./.env)"]})
    assert (result.changed, result.entries) == (False, ())
    after = merge_managed_entries(text, {}, result.entries)
    assert after.changed is False


def test_duplicate_copies_of_our_string_collapse_to_one() -> None:
    first = merge_managed_entries("{}", {}, [], strings={"/permissions/deny": ["x"]})
    text = _with_array("/permissions/deny", ["x", "user", "x"])
    result = merge_managed_entries(text, {}, first.entries, strings={"/permissions/deny": ["x"]})
    assert _at(_parsed(result), "/permissions/deny") == ["x", "user"]


def test_managed_string_pointers_are_the_four_spec_arrays() -> None:
    assert MANAGED_STRING_POINTERS == (
        "/permissions/allow",
        "/permissions/deny",
        "/sandbox/filesystem/denyRead",
        "/sandbox/network/allowedDomains",
    )


# --- lock entries -----------------------------------------------------------------------


def test_entries_cover_every_desired_group_including_noop() -> None:
    desired = {**_want(PRE, event="PreToolUse"), **_want(OURS)}
    result = merge_managed_entries(_doc(OURS), desired, _prior(OURS))
    assert result.changed  # PreToolUse was appended; Stop was a no-op
    assert [(e.scope, e.artifact_id) for e in result.entries] == [
        ("json:/hooks/PreToolUse", "registration:pre_tool_use"),
        ("json:/hooks/Stop", "registration:stop"),
    ]
    stop = result.entries[1]
    assert (stop.path, stop.kind, stop.adapter, stop.source) == (PATH, "runtime", "claude_code", "")
    assert stop.sha256 == compute_hash(canonical_json(OURS))
    assert stop.bytes == len(canonical_json(OURS))
    assert not stop.is_whole_file


def test_canonical_hash_ignores_key_order() -> None:
    assert canonical_json({"b": 1, "a": "é"}) == '{"a":"é","b":1}'.encode()
    assert canonical_json(_REORDERED) == canonical_json(OURS)
    one = scoped_lock_entry(PATH, "/hooks/Stop", _REORDERED, artifact_id="registration:stop")
    two = scoped_lock_entry(PATH, "/hooks/Stop", OURS, artifact_id="registration:stop")
    assert one == two


def test_claude_settings_imports_only_the_stdlib() -> None:
    """The merge must stay light: ``playbook check`` and the adapter import it."""
    loaded = new_modules_after(
        "import coding_agent_playbook.adapters.claude_code.settings.managed_merge"
    )
    ours = [name for name in loaded if name.startswith("coding_agent_playbook")]
    foreign = [
        name
        for name in loaded
        if name not in ours and name.split(".")[0] not in sys.stdlib_module_names
    ]
    assert foreign == []
    assert ours == [
        "coding_agent_playbook._atomic_io",
        "coding_agent_playbook._output_io",  # refuse_special_file before the read: stdlib-only
        "coding_agent_playbook.adapters",
        "coding_agent_playbook.adapters.claude_code",
        "coding_agent_playbook.adapters.claude_code.settings",
        "coding_agent_playbook.adapters.claude_code.settings._json_edits",
        "coding_agent_playbook.adapters.claude_code.settings._json_spans",
        "coding_agent_playbook.adapters.claude_code.settings._plan",
        "coding_agent_playbook.adapters.claude_code.settings.managed_merge",
        "coding_agent_playbook.lockfile",
        "coding_agent_playbook.lockfile.canonical_json",
        "coding_agent_playbook.lockfile.model",
    ]


def test_sandbox_arrays_share_one_created_parent_and_keep_user_values() -> None:
    strings = {
        "/sandbox/filesystem/denyRead": ["~/.ssh"],
        "/sandbox/network/allowedDomains": ["pypi.org"],
    }
    result = merge_managed_entries('{\n  "model": "x"\n}\n', {}, [], strings=strings)
    assert _parsed(result)["sandbox"] == {
        "filesystem": {"denyRead": ["~/.ssh"]},
        "network": {"allowedDomains": ["pypi.org"]},
    }

    mixed = _with_array("/permissions/deny", [7, "user", "ours"])
    claimed = merge_managed_entries("{}", {}, [], strings={"/permissions/deny": ["ours"]})
    dropped = merge_managed_entries(mixed, {}, claimed.entries)
    assert _at(_parsed(dropped), "/permissions/deny") == [7, "user"]


def test_managed_string_leaf_of_wrong_shape_is_an_error() -> None:
    text = '{"permissions": {\n  "allow": "Bash(ls)"}}'
    with pytest.raises(SettingsMergeError) as caught:
        merge_managed_entries(text, {}, [], strings={"/permissions/allow": ["x"]})
    assert (caught.value.line, caught.value.col) == (2, 12)
    assert 'permissions.allow must be an array of strings, got string "Bash(ls)"' in str(
        caught.value
    )


def test_untouched_managed_pointer_is_never_inspected() -> None:
    """A user shape the engine has no stake in must not fail the sync."""
    result = merge_managed_entries('{"sandbox": true}', {}, [])
    assert result.changed is False


def test_absurd_nesting_is_a_settings_error_not_a_crash() -> None:
    text = '{"a": ' + "[" * 100_000 + "]" * 100_000 + "}"
    with pytest.raises(SettingsMergeError, match="nested too deeply"):
        merge_managed_entries(text, {}, [])
