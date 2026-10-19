"""A string-aware span index over strict JSON text (specs/prK-lifecycle-hooks.md §C.2.4 step 6).

The Claude settings merge edits ``.claude/settings.json`` by splicing text and
never re-serializes the document, so every byte outside an edited span (user
keys, formatting, escape sequences, key order) survives. This module records
where each value sits (:class:`JsonSpanIndex`), detects the file's layout
(:func:`detect_style`) and applies splices (:func:`apply_splices`);
:mod:`._json_edits` decides what to splice. Stdlib-only.

The scanner is as strict as the merge's ``json.loads`` pass: duplicate keys,
``NaN`` / ``Infinity``, comments, trailing commas and trailing data raise
:class:`JsonSpanError` with the offending offset.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "DEFAULT_STYLE",
    "JsonMember",
    "JsonNode",
    "JsonSpanError",
    "JsonSpanIndex",
    "JsonStyle",
    "Splice",
    "apply_splices",
    "detect_style",
    "line_col",
    "line_indent",
]

NodeKind = Literal["object", "array", "string", "number", "literal"]
PathStep = str | int

_WHITESPACE: Final = re.compile(r"[ \t\n\r]*")
_INDENT: Final = re.compile(r"[ \t]*")
_FIRST_INDENTED_LINE: Final = re.compile(r"\n([ \t]+)[^ \t\r\n]")
# RFC 8259 strings: no raw control characters, only the eight short escapes or \uXXXX.
_STRING: Final = re.compile(r'"(?:[^"\\\x00-\x1f]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"')
_NUMBER: Final = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?")
_LITERALS: Final = ("true", "false", "null")
# Python's json accepts these; Claude Code's JSON.parse does not.
_NON_FINITE: Final = ("NaN", "Infinity", "-Infinity")


class JsonSpanError(ValueError):
    """Text that is not strict JSON; ``offset`` is where the scanner stopped.

    Example::

        JsonSpanError(10, "duplicate key 'a'")
    """

    def __init__(self, offset: int, message: str) -> None:
        super().__init__(f"offset {offset}: {message}")
        self.offset = offset
        self.message = message


@dataclass(frozen=True, slots=True)
class JsonMember:
    """One ``"key": value`` pair; its span runs from ``key_start`` to ``value.end``."""

    key: str
    key_start: int
    value: JsonNode


@dataclass(frozen=True, slots=True)
class JsonNode:
    """One JSON value at ``text[start:end]``; containers list their children."""

    kind: NodeKind
    start: int
    end: int
    members: tuple[JsonMember, ...] = ()
    elements: tuple[JsonNode, ...] = ()

    def child(self, step: PathStep) -> JsonNode | None:
        """The member value named ``step`` (object) or the element at ``step`` (array)."""
        if self.kind == "object" and isinstance(step, str):
            return next((m.value for m in self.members if m.key == step), None)
        if self.kind == "array" and isinstance(step, int) and 0 <= step < len(self.elements):
            return self.elements[step]
        return None


@dataclass(frozen=True, slots=True)
class JsonSpanIndex:
    """Where every value of one strict JSON document sits in ``text``.

    Example::

        >>> index = JsonSpanIndex.build('{"hooks": {"Stop": []}}')
        >>> index.locate(("hooks", "Stop")).kind
        'array'
    """

    text: str
    root: JsonNode

    @classmethod
    def build(cls, text: str) -> JsonSpanIndex:
        """Scan ``text``; raises :class:`JsonSpanError` unless it is one strict JSON value."""
        scanner = _Scanner(text)
        root = scanner.value(scanner.skip(0))
        end = scanner.skip(root.end)
        if end != len(text):
            raise JsonSpanError(end, "trailing data after the JSON document")
        return cls(text=text, root=root)

    def locate(self, path: Sequence[PathStep]) -> JsonNode | None:
        """The node at ``path`` (object keys and array indexes), or ``None`` when absent."""
        node: JsonNode | None = self.root
        for step in path:
            if node is None:
                return None
            node = node.child(step)
        return node


class _Scanner:
    """Recursive-descent scanner over ``text``; every method takes and returns offsets."""

    def __init__(self, text: str) -> None:
        self.text = text

    def skip(self, pos: int) -> int:
        match = _WHITESPACE.match(self.text, pos)
        return match.end() if match else pos

    def value(self, pos: int) -> JsonNode:
        char = self.text[pos : pos + 1]
        if char == "{":
            return self.object(pos)
        if char == "[":
            return self.array(pos)
        if char == '"':
            return JsonNode("string", pos, self.string_end(pos))
        return self.scalar(pos)

    def string_end(self, pos: int) -> int:
        match = _STRING.match(self.text, pos)
        if match is None:
            raise JsonSpanError(
                pos, "invalid string (unterminated, bad escape or control character)"
            )
        return match.end()

    def scalar(self, pos: int) -> JsonNode:
        for word in _NON_FINITE[::-1]:  # "-Infinity" before "Infinity"
            if self.text.startswith(word, pos):
                raise JsonSpanError(pos, f"{word} is not valid JSON")
        for word in _LITERALS:
            if self.text.startswith(word, pos):
                return JsonNode("literal", pos, pos + len(word))
        match = _NUMBER.match(self.text, pos)
        if match is None:
            raise JsonSpanError(pos, "expected a JSON value")
        return JsonNode("number", pos, match.end())

    def object(self, start: int) -> JsonNode:
        members: list[JsonMember] = []
        pos = self.skip(start + 1)
        if self.text.startswith("}", pos):
            return JsonNode("object", start, pos + 1)
        while True:
            member = self.member(pos, members)
            members.append(member)
            pos = self.skip(member.value.end)
            if self.text.startswith("}", pos):
                return JsonNode("object", start, pos + 1, members=tuple(members))
            pos = self.skip(self.expect(pos, ",", "expected ',' or '}' after an object member"))

    def member(self, pos: int, earlier: Sequence[JsonMember]) -> JsonMember:
        if not self.text.startswith('"', pos):
            raise JsonSpanError(pos, "expected a string key")
        key_end = self.string_end(pos)
        key = json.loads(self.text[pos:key_end])
        if any(m.key == key for m in earlier):
            raise JsonSpanError(pos, f"duplicate key {key!r}")
        after_colon = self.expect(self.skip(key_end), ":", "expected ':' after an object key")
        return JsonMember(key, pos, self.value(self.skip(after_colon)))

    def array(self, start: int) -> JsonNode:
        elements: list[JsonNode] = []
        pos = self.skip(start + 1)
        if self.text.startswith("]", pos):
            return JsonNode("array", start, pos + 1)
        while True:
            element = self.value(pos)
            elements.append(element)
            pos = self.skip(element.end)
            if self.text.startswith("]", pos):
                return JsonNode("array", start, pos + 1, elements=tuple(elements))
            pos = self.skip(self.expect(pos, ",", "expected ',' or ']' after an array element"))

    def expect(self, pos: int, token: str, message: str) -> int:
        if not self.text.startswith(token, pos):
            raise JsonSpanError(pos, message)
        return pos + len(token)


def line_col(text: str, offset: int) -> tuple[int, int]:
    """1-based ``(line, column)`` of ``offset`` in ``text``, columns counted in characters.

    Example::

        >>> line_col('{\\n  "a": 1}', 4)
        (2, 3)
    """
    line_start = text.rfind("\n", 0, offset) + 1
    return text.count("\n", 0, offset) + 1, offset - line_start + 1


def line_indent(text: str, offset: int) -> str:
    """The leading spaces/tabs of the line that holds ``offset``.

    Example::

        >>> line_indent('{\\n\\t"a": 1}', 4)
        '\\t'
    """
    line_start = text.rfind("\n", 0, offset) + 1
    match = _INDENT.match(text, line_start)
    return match.group() if match else ""


@dataclass(frozen=True, slots=True)
class JsonStyle:
    """The layout a file already uses, so inserted fragments look native.

    ``indent`` is one nesting level (spaces or a tab), ``newline`` is LF or
    CRLF, ``trailing_newline`` / ``bom`` record the file's ends.
    """

    indent: str
    newline: str
    trailing_newline: bool
    bom: bool


#: New files are two-space, LF, newline-terminated, without a BOM (§C.2.4 step 1).
DEFAULT_STYLE: Final = JsonStyle("  ", "\n", True, False)


def detect_style(text: str) -> JsonStyle:
    """Detect ``text``'s indent (first indented line), newline, trailing newline and BOM.

    A file with no indented line (one-line JSON) gets the default two-space indent.

    Example::

        >>> detect_style('{\\r\\n\\t"a": 1\\r\\n}')
        JsonStyle(indent='\\t', newline='\\r\\n', trailing_newline=False, bom=False)
    """
    match = _FIRST_INDENTED_LINE.search(text)
    indent = DEFAULT_STYLE.indent
    if match is not None:
        indent = "\t" if "\t" in match.group(1) else match.group(1)
    return JsonStyle(
        indent=indent,
        newline="\r\n" if "\r\n" in text else "\n",
        trailing_newline=text.endswith("\n"),
        bom=text.startswith("\ufeff"),
    )


@dataclass(frozen=True, slots=True)
class Splice:
    """Replace ``text[start:end]`` with ``text``; ``start == end`` is an insertion."""

    start: int
    end: int
    text: str


def apply_splices(text: str, splices: Sequence[Splice]) -> str:
    """Apply non-overlapping ``splices`` (offsets into the original ``text``).

    An insertion at the start of a replaced span lands before the replacement.
    Raises ``ValueError`` naming both spans when two splices overlap (two
    insertions at one offset count, since their order would be a guess).

    Example::

        >>> apply_splices("abc", [Splice(1, 2, "XY"), Splice(3, 3, "!")])
        'aXYc!'
    """
    ordered = sorted(splices, key=lambda s: (s.start, s.end))
    for before, after in pairwise(ordered):
        same_point = before.start == before.end == after.start == after.end
        if after.start < before.end or same_point:
            raise ValueError(
                f"splices overlap: ({before.start}, {before.end}) and ({after.start}, {after.end})"
            )
    parts: list[str] = []
    cursor = 0
    for splice in ordered:
        parts.append(text[cursor : splice.start])
        parts.append(splice.text)
        cursor = splice.end
    parts.append(text[cursor:])
    return "".join(parts)
