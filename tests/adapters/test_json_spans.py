"""The string-aware JSON span index and its textual splices (specs/prK-lifecycle-hooks.md §C.2.4).

``JsonSpanIndex`` records where every value sits in the original text, and
``edit_splices`` turns a list of ``ArrayEdit`` into splices that leave every
byte outside the edited spans alone. ``apply_edits`` is the semantic twin the
self-check compares against.
"""

from __future__ import annotations

import json

import pytest

from coding_agent_playbook.adapters.claude_code.settings._json_edits import (
    ArrayEdit,
    apply_edits,
    edit_splices,
    render_fragment,
)
from coding_agent_playbook.adapters.claude_code.settings._json_spans import (
    DEFAULT_STYLE,
    JsonSpanError,
    JsonSpanIndex,
    JsonStyle,
    Splice,
    apply_splices,
    detect_style,
    line_col,
    line_indent,
)


def _edit(text: str, *edits: ArrayEdit) -> str:
    """Apply ``edits`` to ``text`` through the span index, checking the semantic twin."""
    planned = apply_edits(json.loads(text), edits)
    index = JsonSpanIndex.build(text)
    result = apply_splices(text, edit_splices(index, planned, edits, detect_style(text)))
    assert json.loads(result) == planned
    return result


# --- JsonSpanIndex ------------------------------------------------------------------


def test_spans_ignore_brackets_and_quotes_inside_strings() -> None:
    text = '{"a": "x}]\\"[{", "b": [1, "]", {"c": "{"}], "d\\"k": 2}'
    index = JsonSpanIndex.build(text)
    assert [member.key for member in index.root.members] == ["a", "b", 'd"k']
    array = index.locate(("b",))
    assert array is not None
    assert array.kind == "array"
    assert text[array.start : array.end] == '[1, "]", {"c": "{"}]'
    assert [text[e.start : e.end] for e in array.elements] == ["1", '"]"', '{"c": "{"}']


def test_keys_are_decoded_so_escaped_names_match() -> None:
    index = JsonSpanIndex.build('{"\\u0068ooks": {"Stop": []}}')
    node = index.locate(("hooks", "Stop"))
    assert node is not None
    assert node.kind == "array"


def test_locate_walks_array_indexes_and_misses_cleanly() -> None:
    text = '{"hooks": {"Stop": [{"x": 1}, {"y": 2}]}}'
    index = JsonSpanIndex.build(text)
    node = index.locate(("hooks", "Stop", 1))
    assert node is not None
    assert text[node.start : node.end] == '{"y": 2}'
    assert index.locate(("hooks", "Stop", 2)) is None
    assert index.locate(("hooks", "Nope")) is None
    assert index.locate(("hooks", 0)) is None


def test_member_span_starts_at_its_key() -> None:
    text = '{ "a" : 1 }'
    member = JsonSpanIndex.build(text).root.members[0]
    assert text[member.key_start : member.value.end] == '"a" : 1'


@pytest.mark.parametrize(
    ("text", "offset", "fragment"),
    [
        pytest.param('{"a": 1,\n "a": 2}', 10, "duplicate key 'a'", id="duplicate-key"),
        pytest.param('{"a": NaN}', 6, "NaN", id="nan"),
        pytest.param('{"a": [-Infinity]}', 7, "-Infinity", id="neg-infinity"),
        pytest.param('{"a": 1} x', 9, "trailing", id="trailing-data"),
    ],
)
def test_build_rejects_non_strict_json_with_offset(text: str, offset: int, fragment: str) -> None:
    with pytest.raises(JsonSpanError) as caught:
        JsonSpanIndex.build(text)
    assert caught.value.offset == offset
    assert fragment in caught.value.message


def test_line_col_and_line_indent() -> None:
    text = '{\n  "a": [\n\t\t1\n  ]\n}'
    assert line_col(text, 0) == (1, 1)
    assert line_col(text, text.index('"a"')) == (2, 3)
    assert line_indent(text, text.index("1")) == "\t\t"
    assert line_indent(text, text.index("[")) == "  "


# --- detect_style -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "style"),
    [
        pytest.param('{\n    "a": 1\n}\n', JsonStyle("    ", "\n", True, False), id="indent4"),
        pytest.param('{\n\t"a": 1\n}', JsonStyle("\t", "\n", False, False), id="tabs"),
        pytest.param('{\r\n  "a": 1\r\n}\r\n', JsonStyle("  ", "\r\n", True, False), id="crlf"),
        pytest.param('\ufeff{\n "a": 1\n}\n', JsonStyle(" ", "\n", True, True), id="bom"),
        pytest.param('{"a": 1}', JsonStyle("  ", "\n", False, False), id="one-line"),
    ],
)
def test_detect_style(text: str, style: JsonStyle) -> None:
    assert detect_style(text) == style


def test_default_style_is_two_space_lf() -> None:
    assert JsonStyle("  ", "\n", True, False) == DEFAULT_STYLE


# --- apply_splices ------------------------------------------------------------------


def test_apply_splices_applies_back_to_front() -> None:
    text = "abcdef"
    splices = [Splice(4, 6, "XY"), Splice(0, 1, ""), Splice(2, 2, "-")]
    assert apply_splices(text, splices) == "b-cdXY"


def test_apply_splices_rejects_overlap() -> None:
    with pytest.raises(ValueError, match=r"overlap.*\(1, 3\).*\(2, 4\)"):
        apply_splices("abcdef", [Splice(1, 3, ""), Splice(2, 4, "")])


# --- edit_splices: deletes keep separators valid ---------------------------------------

_LIST = '{\n  "a": [\n    1,\n    2,\n    3\n  ],\n  "z": 0\n}\n'


@pytest.mark.parametrize(
    ("deleted", "expected"),
    [
        pytest.param({0}, '{\n  "a": [\n    2,\n    3\n  ],\n  "z": 0\n}\n', id="first"),
        pytest.param({1}, '{\n  "a": [\n    1,\n    3\n  ],\n  "z": 0\n}\n', id="middle"),
        pytest.param({2}, '{\n  "a": [\n    1,\n    2\n  ],\n  "z": 0\n}\n', id="last"),
        pytest.param({0, 1, 2}, '{\n  "z": 0\n}\n', id="only"),
    ],
)
def test_delete_element_removes_separating_comma(deleted: set[int], expected: str) -> None:
    assert _edit(_LIST, ArrayEdit(("a",), delete=frozenset(deleted))) == expected


def test_delete_runs_in_compact_array() -> None:
    text = '{"a": [1, 2, 3, 4, 5]}'
    assert _edit(text, ArrayEdit(("a",), delete=frozenset({1, 2, 4}))) == '{"a": [1, 4]}'


def test_emptied_array_prunes_emptied_parents_but_not_user_siblings() -> None:
    text = '{\n  "s": {\n    "f": {\n      "d": ["x"]\n    },\n    "n": {}\n  }\n}\n'
    result = _edit(text, ArrayEdit(("s", "f", "d"), delete=frozenset({0})))
    assert result == '{\n  "s": {\n    "n": {}\n  }\n}\n'


def test_last_member_removed_leaves_empty_root() -> None:
    assert _edit('{\n  "a": [1]\n}\n', ArrayEdit(("a",), delete=frozenset({0}))) == "{}\n"


# --- edit_splices: appends and replacements -----------------------------------------


def test_append_member_reindents_fragment() -> None:
    text = '{\n    "permissions": {}\n}\n'
    edit = ArrayEdit(("sandbox", "network", "allowedDomains"), append=("example.com",))
    assert _edit(text, edit) == (
        "{\n"
        '    "permissions": {},\n'
        '    "sandbox": {\n'
        '        "network": {\n'
        '            "allowedDomains": [\n'
        '                "example.com"\n'
        "            ]\n"
        "        }\n"
        "    }\n"
        "}\n"
    )


def test_append_into_existing_parent_creates_only_missing_levels() -> None:
    text = '{\n\t"permissions": {\n\t\t"deny": []\n\t}\n}'
    edit = ArrayEdit(("permissions", "allow"), append=("Bash(ls)",))
    assert _edit(text, edit) == (
        '{\n\t"permissions": {\n\t\t"deny": [],\n\t\t"allow": [\n\t\t\t"Bash(ls)"\n\t\t]\n\t}\n}'
    )


def test_append_element_matches_last_element_indent_and_crlf() -> None:
    text = '{\r\n  "a": [\r\n    {"k": 1}\r\n  ]\r\n}\r\n'
    result = _edit(text, ArrayEdit(("a",), append=({"k": 2},)))
    assert (
        result == '{\r\n  "a": [\r\n    {"k": 1},\r\n    {\r\n      "k": 2\r\n    }\r\n  ]\r\n}\r\n'
    )


def test_append_into_empty_array_expands_it() -> None:
    result = _edit('{\n  "a": [ ]\n}\n', ArrayEdit(("a",), append=(3, 4)))
    assert result == '{\n  "a": [\n    3,\n    4\n  ]\n}\n'


def test_append_into_compact_array_stays_compact() -> None:
    assert _edit('{"a": [1, 2]}', ArrayEdit(("a",), append=(3,))) == '{"a": [1, 2, 3]}'


def test_append_after_tail_delete_keeps_one_separator() -> None:
    text = '{\n  "a": [\n    1,\n    2\n  ]\n}'
    result = _edit(text, ArrayEdit(("a",), delete=frozenset({1}), append=(9,)))
    assert result == '{\n  "a": [\n    1,\n    9\n  ]\n}'


def test_replace_element_in_place_keeps_neighbours() -> None:
    text = '{\n  "a": [\n    {"user": true},\n    {"ours": 1},\n    "tail"\n  ]\n}'
    result = _edit(text, ArrayEdit(("a",), replace={1: {"ours": 2}}))
    assert (
        result
        == '{\n  "a": [\n    {"user": true},\n    {\n      "ours": 2\n    },\n    "tail"\n  ]\n}'
    )


def test_delete_all_and_append_rewrites_container_interior() -> None:
    text = '{"a": [1, 2]}'
    assert _edit(text, ArrayEdit(("a",), delete=frozenset({0, 1}), append=(3,))) == (
        '{"a": [\n  3\n]}'
    )


def test_noop_edit_produces_no_splices() -> None:
    text = '{"a": [1]}'
    edit = ArrayEdit(("a",))
    assert edit.is_noop
    assert edit_splices(JsonSpanIndex.build(text), json.loads(text), [edit], DEFAULT_STYLE) == []


# --- apply_edits (the semantic twin) -------------------------------------------------


def test_apply_edits_never_mutates_its_input() -> None:
    doc = {"a": [1, 2]}
    assert apply_edits(doc, [ArrayEdit(("a",), replace={0: 5}, append=(6,))]) == {"a": [5, 2, 6]}
    assert doc == {"a": [1, 2]}


def test_apply_edits_appends_new_keys_in_edit_order() -> None:
    doc: dict[str, object] = {"x": 1}
    planned = apply_edits(doc, [ArrayEdit(("b", "c"), append=(1,)), ArrayEdit(("a",), append=(2,))])
    assert list(planned) == ["x", "b", "a"]


def test_render_fragment_indents_continuation_lines() -> None:
    style = JsonStyle("\t", "\r\n", True, False)
    assert render_fragment({"k": [1]}, style, "  ") == '{\r\n  \t"k": [\r\n  \t\t1\r\n  \t]\r\n  }'
    assert render_fragment({"k": [1]}, style, "  ", compact=True) == '{"k": [1]}'


@pytest.mark.parametrize(
    ("text", "offset", "fragment"),
    [
        pytest.param('{"a": "x\ty"}', 6, "invalid string", id="raw-control-char"),
        pytest.param('{"a": "\\q"}', 6, "invalid string", id="bad-escape"),
        pytest.param('{"a": }', 6, "expected a JSON value", id="missing-value"),
        pytest.param("{a: 1}", 1, "expected a string key", id="bare-key"),
        pytest.param('{"a" 1}', 5, "expected ':'", id="missing-colon"),
        pytest.param('{"a": [1 2]}', 9, "expected ',' or ']'", id="missing-comma"),
        pytest.param('{"a": 1,}', 8, "expected a string key", id="trailing-comma"),
        pytest.param("", 0, "expected a JSON value", id="empty"),
    ],
)
def test_build_rejects_malformed_text_with_offset(text: str, offset: int, fragment: str) -> None:
    with pytest.raises(JsonSpanError) as caught:
        JsonSpanIndex.build(text)
    assert (caught.value.offset, fragment in caught.value.message) == (offset, True)


# --- ArrayEdit / apply_edits validation ------------------------------------------------


def test_array_edit_rejects_empty_path_and_conflicting_indexes() -> None:
    with pytest.raises(ValueError, match=r"got \(\)"):
        ArrayEdit(())
    with pytest.raises(ValueError, match=r"indexes \[1\] are deleted and replaced"):
        ArrayEdit(("a",), delete=frozenset({1}), replace={1: 0})


@pytest.mark.parametrize(
    ("doc", "edit", "message"),
    [
        pytest.param(
            {"a": {}}, ArrayEdit(("a",), append=(1,)), "expected an array, got dict", id="not-array"
        ),
        pytest.param(
            {"a": [1]},
            ArrayEdit(("a",), delete=frozenset({3})),
            r"indexes \[3\]",
            id="out-of-range",
        ),
        pytest.param(
            {"a": 1}, ArrayEdit(("a", "b"), append=(1,)), "'a' is not an object", id="scalar-parent"
        ),
        pytest.param(
            {},
            ArrayEdit(("a", "b"), delete=frozenset({0})),
            "'a' is not an object",
            id="missing-parent",
        ),
    ],
)
def test_apply_edits_names_the_offending_path(
    doc: dict[str, object], edit: ArrayEdit, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        apply_edits(doc, [edit])


def test_two_edits_under_one_missing_parent_create_it_once() -> None:
    text = '{\n  "model": "x"\n}\n'
    result = _edit(
        text,
        ArrayEdit(("sandbox", "filesystem", "denyRead"), append=("~/.ssh",)),
        ArrayEdit(("sandbox", "network", "allowedDomains"), append=("example.com",)),
    )
    assert json.loads(result) == {
        "model": "x",
        "sandbox": {
            "filesystem": {"denyRead": ["~/.ssh"]},
            "network": {"allowedDomains": ["example.com"]},
        },
    }
    assert result.startswith('{\n  "model": "x",\n  "sandbox": {\n    "filesystem": {\n')


def test_member_delete_and_member_add_in_one_object() -> None:
    text = '{\n  "hooks": {\n    "Stop": [1]\n  }\n}'
    result = _edit(
        text,
        ArrayEdit(("hooks", "Stop"), delete=frozenset({0})),
        ArrayEdit(("hooks", "PreToolUse"), append=(2,)),
    )
    assert result == '{\n  "hooks": {\n    "PreToolUse": [\n      2\n    ]\n  }\n}'
