"""Tests for the shared TOML writer primitives (``coding_agent_playbook.toml_writer``).

These pin the behaviour the two call sites (the ``config/files.py``
Config/Lockfile writer and ``agent_harness/manifest.py``) share, so a future change to
the escape ladder, ``bool``-before-``int`` ordering, key quoting, the float and
date/time forms (P6), or the ``TypeError`` semantics breaks here rather than
silently in a round-trip elsewhere.
"""

from __future__ import annotations

import datetime as dt
import enum
import itertools
import random
import re
import string
import sys
import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook import toml_writer as _toml
from coding_agent_playbook.agent_harness.manifest import _format_scalar as _manifest_format_scalar
from tests.toml_equality import assert_toml_identical

if TYPE_CHECKING:
    from collections.abc import Callable

# --- scalars ---------------------------------------------------------------


def test_format_scalar_bool() -> None:
    assert _toml.format_scalar(True) == "true"
    assert _toml.format_scalar(False) == "false"


def test_format_scalar_int() -> None:
    assert _toml.format_scalar(0) == "0"
    assert _toml.format_scalar(42) == "42"
    assert _toml.format_scalar(-7) == "-7"


def test_format_scalar_int_past_the_int_to_str_limit_is_hex(
    default_int_max_str_digits: int,
) -> None:
    """Regression: ``str`` refuses an int past ``sys.get_int_max_str_digits()``
    (``ValueError``), yet ``tomllib`` reads such ints from ``0x``/``0o``/``0b``
    literals, so the writer crashed on a file ``tomllib`` accepted."""
    value = 1 << 20000
    literal = _toml.format_scalar(value)
    assert literal == hex(value)
    assert_toml_identical(tomllib.loads(f"x = {literal}")["x"], value)


def test_format_scalar_int_just_under_the_limit_stays_decimal(
    default_int_max_str_digits: int,
) -> None:
    value = 10 ** (default_int_max_str_digits - 1)
    assert _toml.format_scalar(value) == "1" + "0" * (default_int_max_str_digits - 1)


def test_format_scalar_int_past_a_disabled_limit_stays_decimal() -> None:
    """With the limit off (``PYTHONINTMAXSTRDIGITS=0``) ``str`` takes any int, so decimal."""
    previous = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        assert _toml.format_scalar(1 << 20000) == str(1 << 20000)
    finally:
        sys.set_int_max_str_digits(previous)


def test_format_scalar_rejects_a_negative_int_past_the_limit(
    default_int_max_str_digits: int,
) -> None:
    """TOML hex is unsigned, so no literal holds it (``tomllib`` cannot produce one)."""
    with pytest.raises(ValueError, match=r"20001-bit negative integer .* TOML hex is unsigned"):
        _toml.format_scalar(-(1 << 20000))


def test_format_scalar_bool_before_int() -> None:
    """``isinstance(True, int)`` is True; bool must be handled first so a bool
    never renders as ``1``/``0``."""
    assert _toml.format_scalar(True) == "true"
    assert _toml.format_scalar(False) == "false"


def test_format_scalar_str_simple() -> None:
    assert _toml.format_scalar("hello") == '"hello"'


@pytest.mark.parametrize(
    ("value", "literal"),
    [
        (1.5, "1.5"),
        (1.0, "1.0"),
        (20.0, "20.0"),
        (1e-05, "1e-05"),
        (1e16, "1e+16"),
        (-0.0, "-0.0"),
        (float("inf"), "inf"),
        (float("-inf"), "-inf"),
        (float("nan"), "nan"),
        (-float("nan"), "-nan"),
    ],
)
def test_format_scalar_float(value: float, literal: str) -> None:
    """Floats are supported since ``playbook init`` writes back user tables such as
    ``[metrics.weights]`` verbatim (this used to be pinned as a ``TypeError``,
    when no writer needed floats). The literal re-parses to the same float — still
    a float when integral (``1.0``, never ``1``), and with its sign (``-0.0``,
    ``-nan``, which ``float.__repr__`` alone writes as ``nan``)."""
    assert _toml.format_scalar(value) == literal
    assert_toml_identical(tomllib.loads(f"x = {literal}")["x"], value)


def test_format_scalar_float_subclass_renders_as_a_plain_float() -> None:
    """A float subclass with its own ``repr`` (NumPy 2's ``np.float64(1.5)``) must
    still render as a TOML float, not as its repr."""

    class _Tagged(float):
        def __repr__(self) -> str:
            return f"_Tagged({float(self)})"

    assert _toml.format_scalar(_Tagged(2.5)) == "2.5"


# --- dates and times ---------------------------------------------------------

_MINUS_SEVEN = dt.timezone(dt.timedelta(hours=-7))


@pytest.mark.parametrize(
    ("value", "literal"),
    [
        (dt.date(1979, 5, 27), "1979-05-27"),
        (dt.datetime(1979, 5, 27, 7, 32), "1979-05-27T07:32:00"),
        (dt.datetime(1979, 5, 27, 7, 32, tzinfo=dt.UTC), "1979-05-27T07:32:00+00:00"),
        (
            dt.datetime(1979, 5, 27, 0, 32, 0, 999999, tzinfo=_MINUS_SEVEN),
            "1979-05-27T00:32:00.999999-07:00",
        ),
        (dt.time(7, 32), "07:32:00"),
        (dt.time(0, 32, 0, 500000), "00:32:00.500000"),
    ],
)
def test_format_scalar_date_and_time(value: dt.date | dt.time, literal: str) -> None:
    assert _toml.format_scalar(value) == literal
    # Strict: ``==`` would accept the right instant at the wrong offset.
    assert_toml_identical(tomllib.loads(f"x = {literal}")["x"], value)


def test_format_scalar_datetime_checked_before_date() -> None:
    """``datetime`` subclasses ``date``: it must keep its time part (P6)."""
    value = dt.datetime(2026, 10, 14, 9, 0)
    assert _toml.format_scalar(value) == "2026-10-14T09:00:00"
    assert _toml.format_scalar([value.date(), value]) == "[2026-10-14, 2026-10-14T09:00:00]"


def test_format_scalar_rejects_a_time_with_an_offset() -> None:
    """TOML has local times only: an offset would be written as invalid TOML."""
    value = dt.time(7, 32, tzinfo=dt.UTC)
    with pytest.raises(ValueError, match=r"TOML times carry no UTC offset.*07:32"):
        _toml.format_scalar(value)


def test_format_scalar_rejects_a_sub_minute_offset() -> None:
    """TOML offsets are ``+HH:MM``; ``isoformat`` would write ``+00:00:30``."""
    value = dt.datetime(1979, 5, 27, tzinfo=dt.timezone(dt.timedelta(seconds=30)))
    with pytest.raises(ValueError, match=r"whole minutes.*0:00:30"):
        _toml.format_scalar(value)


# --- string escaping -------------------------------------------------------


def test_format_string_escapes_quote_and_backslash() -> None:
    assert _toml.format_string('a"b') == '"a\\"b"'
    assert _toml.format_string("a\\b") == '"a\\\\b"'


def test_format_string_escapes_named_control_chars() -> None:
    assert _toml.format_string("a\nb") == '"a\\nb"'
    assert _toml.format_string("a\rb") == '"a\\rb"'
    assert _toml.format_string("a\tb") == '"a\\tb"'


def test_format_string_unicode_escape_fallback_for_other_control_chars() -> None:
    """Control chars below U+0020 without a named escape fall back to \\uXXXX
    (uppercase hex, 4 digits)."""
    assert _toml.format_string("\x00") == '"\\u0000"'
    assert _toml.format_string("\x01") == '"\\u0001"'
    assert _toml.format_string("\x08") == '"\\u0008"'
    assert _toml.format_string("\x1f") == '"\\u001F"'


def test_format_string_passes_through_printable_unicode() -> None:
    # Non-control unicode (>= U+0020) is emitted verbatim, not escaped.
    assert _toml.format_string("café — π") == '"café — π"'


def test_format_string_escapes_delete() -> None:
    """Regression: U+007F is a control character TOML forbids unescaped in a basic
    string; it used to be emitted raw, which ``tomllib`` refuses to parse."""
    literal = _toml.format_string("a\x7fb")
    assert literal == '"a\\u007Fb"'
    assert tomllib.loads(f"x = {literal}")["x"] == "a\x7fb"


def test_format_scalar_str_delegates_to_format_string() -> None:
    assert _toml.format_scalar('weird "x"\twith\nctrl\x00') == _toml.format_string(
        'weird "x"\twith\nctrl\x00'
    )


@pytest.mark.parametrize(
    ("char", "escape"),
    [("\x00", "\\u0000"), ("\x0b", "\\u000B"), ("\x1b", "\\u001B"), ("\x7f", "\\u007F")],
)
def test_unicode_escape_is_four_uppercase_hex_digits(char: str, escape: str) -> None:
    match = re.fullmatch(".", char, re.DOTALL)
    assert match is not None
    assert _toml._unicode_escape(match) == escape


# --- string escaping: characterization against the per-character loop --------
#
# ``format_string`` escaped one character at a time in a Python loop until the
# perf change that replaced it; the loop is kept below, verbatim, as the
# reference the escaper must match byte for byte, exceptions included.


def _reference_format_string(value: str) -> str:
    """``toml_writer.format_string`` as of commit 8eb43dff, verbatim."""
    out: list[str] = ['"']
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ch == "\x7f":
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


#: A frozenset like the writer's own: ``ch in <str>`` would raise on an ``int``
#: (iterating bytes) where a set lookup just says no.
_REFERENCE_BARE_KEY_CHARS = frozenset(string.ascii_letters + string.digits + "-_")


def _reference_format_key(key: str) -> str:
    """``toml_writer.format_key`` as of commit 8eb43dff, over the reference escaper."""
    if key and all(ch in _REFERENCE_BARE_KEY_CHARS for ch in key):
        return key
    return _reference_format_string(key)


def _first_difference(actual: str, expected: str) -> int:
    """Index of the first character two strings differ at (the shorter length if none)."""
    pairs = enumerate(zip(actual, expected, strict=False))
    return next((index for index, (a, b) in pairs if a != b), min(len(actual), len(expected)))


def _outcome(render: Callable[[str], str], value: object) -> tuple[str, str]:
    """What ``render(value)`` does: ``("ok", text)``, or the exception's type and message."""
    try:
        return ("ok", render(value))  # type: ignore[arg-type]  # non-str inputs on purpose
    except Exception as error:
        return (type(error).__name__, str(error))


#: Every character the escaper rewrites: U+0000..U+001F, ``"``, ``\``, U+007F.
_ESCAPED_CHARS = "".join(map(chr, range(0x20))) + '"\\\x7f'
#: Those plus neighbours an escaper could confuse with them: the letters and hex
#: digits of the escapes, C1 controls and separators TOML keeps raw, BOM,
#: lone surrogates, astral characters.
_TRICKY_CHARS = (
    _ESCAPED_CHARS + "unrt0aAF \x80\x9f\xa0é\u2028\ufeff\ud800\udfff\U0001f600\U0010ffff"
)

_EDGE_CASES = [
    pytest.param("", id="empty"),
    pytest.param(_ESCAPED_CHARS, id="only-escapes"),
    pytest.param(_ESCAPED_CHARS[::-1] * 3, id="only-escapes-reversed-repeated"),
    pytest.param('\\\\\\""\\n\\\n', id="backslash-and-quote-runs"),
    pytest.param("C:\\path\\u0041\\n\\x7f", id="text-that-looks-escaped"),
    pytest.param("line\r\nline\n\ttab\r", id="crlf-and-tab"),
    pytest.param("café — π 日本 😀 ٣", id="mixed-unicode"),
    pytest.param("\x80\x9f\xa0\u2028\u2029\ufeff", id="c1-controls-and-separators-stay-raw"),
    pytest.param("\ud800a\udfff\ud83d", id="lone-surrogates"),
    pytest.param("\U00010000\U0010ffff", id="astral-bounds"),
    pytest.param("plain ascii without escapes", id="no-escape"),
    pytest.param("x" * 100_000, id="long-no-escape"),
    pytest.param('# T\n\nSome "quoted" \\ text\x00\x1b[0m\t\x7f\n' * 2_000, id="long-markdown"),
    pytest.param("\x00" * 10_000, id="long-only-nul"),
    pytest.param("日本語\n" * 5_000, id="long-non-ascii-with-newlines"),
]


@pytest.mark.parametrize("value", _EDGE_CASES)
def test_format_string_matches_the_reference_loop_on_edge_cases(value: str) -> None:
    assert _toml.format_string(value) == _reference_format_string(value)


def test_format_string_matches_the_reference_loop_on_every_code_point() -> None:
    """One string of every code point U+0000..U+10FFFF, surrogates included."""
    everything = "".join(map(chr, range(0x110000)))
    actual, expected = _toml.format_string(everything), _reference_format_string(everything)
    # A bool, not ``assert actual == expected``: pytest would diff 1.1M characters.
    matches = actual == expected
    assert matches, f"first difference at output index {_first_difference(actual, expected)}"


def test_format_string_matches_the_reference_loop_on_every_pair_of_tricky_chars() -> None:
    pairs = ["".join(pair) for pair in itertools.product(_TRICKY_CHARS, repeat=2)]
    assert [p for p in pairs if _toml.format_string(p) != _reference_format_string(p)] == []


def _generated_strings(count: int, seed: int) -> list[str]:
    """``count`` seeded strings, each drawn from the tricky characters or all of Unicode."""
    rng = random.Random(seed)
    tricky = _TRICKY_CHARS + string.ascii_letters + string.digits
    strings: list[str] = []
    for index in range(count):
        size = rng.randrange(0, 80)
        if index % 2:
            strings.append("".join(rng.choices(tricky, k=size)))
        else:
            strings.append("".join(chr(rng.randrange(0x110000)) for _ in range(size)))
    return strings


def test_format_string_matches_the_reference_loop_on_generated_strings() -> None:
    generated = _generated_strings(4_000, seed=20261025)
    assert [s for s in generated if _toml.format_string(s) != _reference_format_string(s)] == []


# Deliberately not a StrEnum: only the mixin's ``format()`` differs from its text.
class _StrEnumMixin(str, enum.Enum):  # noqa: UP042
    """A ``(str, Enum)`` member: ``format()`` gives ``_StrEnumMixin.RED``, iterating ``r\\n``.

    GREEN and SPACED need no escaping, so an escaper that sent them down a
    ``str``-only fast path (``isinstance`` in place of ``type(...) is str``)
    would ``format()`` them as ``_StrEnumMixin.GREEN``; RED's ``\\n`` hides that,
    since ``str.replace`` returns a plain ``str``. SPACED is no bare key, so
    ``format_key`` hands it to ``format_string`` too.
    """

    RED = "r\n"
    GREEN = "green"
    SPACED = "a b"


class _TaggedStr(str):
    """A plain ``str`` subclass, as a YAML loader or a schema may hand the writer."""


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_StrEnumMixin.RED, id="str-enum-mixin-member"),
        pytest.param(_StrEnumMixin.GREEN, id="str-enum-mixin-member-without-escapes"),
        pytest.param(_StrEnumMixin.SPACED, id="str-enum-mixin-member-not-a-bare-key"),
        pytest.param(_TaggedStr('a"b\x01'), id="str-subclass"),
        pytest.param(0, id="int-zero"),
        pytest.param(None, id="none"),
        pytest.param(False, id="false"),
        pytest.param(b"", id="empty-bytes"),
        pytest.param(b"a", id="bytes"),
        pytest.param(["a", "\n", '"'], id="list-of-chars"),
        pytest.param(["ab"], id="list-of-a-long-str"),
    ],
)
def test_format_string_and_format_key_match_the_reference_on_non_str_input(
    value: object,
) -> None:
    """Outside the ``str`` signature, yet reachable: a YAML mapping key such as ``0``
    or ``null`` reaches ``format_key`` and then ``format_string`` (both falsy). The
    result, or the exception type and message, is the reference loop's."""
    assert _outcome(_toml.format_string, value) == _outcome(_reference_format_string, value)
    assert _outcome(_toml.format_key, value) == _outcome(_reference_format_key, value)


@pytest.mark.parametrize("value", [*_EDGE_CASES, pytest.param("bare-key_9", id="bare-key")])
def test_format_key_matches_the_reference_on_edge_cases(value: str) -> None:
    assert _toml.format_key(value) == _reference_format_key(value)


@pytest.mark.parametrize("value", _EDGE_CASES)
def test_manifest_format_scalar_matches_the_reference_on_edge_cases(value: str) -> None:
    """The manifest writer reaches the escaper through values and inline-table keys."""
    expected_table = f"{{ {_reference_format_key(value)} = [{_reference_format_string(value)}] }}"
    assert _manifest_format_scalar(value) == _reference_format_string(value)
    assert _manifest_format_scalar({value: [value]}) == expected_table


def test_manifest_format_scalar_keeps_the_error_for_a_falsy_non_str_key() -> None:
    """A YAML frontmatter key ``0`` in an inline table fails as it always did."""
    with pytest.raises(TypeError, match=r"^'int' object is not iterable$"):
        _manifest_format_scalar({0: "x"})


# --- keys ------------------------------------------------------------------


def test_format_key_bare_identifier() -> None:
    assert _toml.format_key("name") == "name"
    assert _toml.format_key("python-house-style") == "python-house-style"
    assert _toml.format_key("snake_case_99") == "snake_case_99"


def test_format_key_quotes_non_identifier() -> None:
    assert _toml.format_key("weird key.dotted") == '"weird key.dotted"'
    assert _toml.format_key("has space") == '"has space"'
    assert _toml.format_key("dot.ted") == '"dot.ted"'


def test_format_key_quotes_empty_key() -> None:
    assert _toml.format_key("") == '""'


@pytest.mark.parametrize("key", ["café", "x²", "日本", "٣"])
def test_format_key_quotes_non_ascii_keys(key: str) -> None:
    """Regression: TOML bare keys are ASCII ``A-Za-z0-9_-`` only, but ``isalnum``
    also accepts letters/digits outside ASCII, so ``café = 1`` was written bare
    and ``tomllib`` refused to parse it."""
    assert _toml.format_key(key) == _toml.format_string(key)
    assert tomllib.loads(f"{_toml.format_key(key)} = 1") == {key: 1}


# --- lists -----------------------------------------------------------------


def test_format_scalar_empty_list() -> None:
    assert _toml.format_scalar([]) == "[]"


def test_format_scalar_list_of_scalars() -> None:
    assert _toml.format_scalar([1, "two", True]) == '[1, "two", true]'


def test_format_scalar_nested_list() -> None:
    assert _toml.format_scalar([["a"], []]) == '[["a"], []]'


def test_format_scalar_nests_deeper_than_the_recursion_limit() -> None:
    """The walk is iterative: ``tomllib`` parses inline values recursively, so a
    recursive writer could overflow on a value it accepted when called from a
    deeper stack. Twice the recursion limit leaves no doubt."""
    depth = 2 * sys.getrecursionlimit()
    array: object = 1
    table: object = 1
    for _ in range(depth):
        array = [array]
        table = {"k": table}
    assert _toml.format_scalar(array) == "[" * depth + "1" + "]" * depth
    inline = _toml.format_scalar(table, allow_inline_table=True)
    assert inline == "{ k = " * depth + "1" + " }" * depth


# --- inline tables (manifest path) -----------------------------------------


def test_format_scalar_inline_table_enabled() -> None:
    out = _toml.format_scalar({"a": 1, "b": "x"}, allow_inline_table=True)
    assert out == '{ a = 1, b = "x" }'


def test_format_scalar_inline_table_empty() -> None:
    assert _toml.format_scalar({}, allow_inline_table=True) == "{}"


def test_format_scalar_inline_table_quotes_non_identifier_keys() -> None:
    out = _toml.format_scalar({"weird key.dotted": "v"}, allow_inline_table=True)
    assert out == '{ "weird key.dotted" = "v" }'


def test_format_scalar_inline_table_nested() -> None:
    out = _toml.format_scalar({"outer": {"inner": 1}}, allow_inline_table=True)
    assert out == "{ outer = { inner = 1 } }"


def test_format_scalar_list_of_inline_tables() -> None:
    out = _toml.format_scalar([{"a": 1}, {"b": 2}], allow_inline_table=True)
    assert out == "[{ a = 1 }, { b = 2 }]"


def test_format_scalar_inline_table_output_is_valid_toml() -> None:
    # Wrapping the inline table in a key assignment must parse back identically.
    out = _toml.format_scalar({"note": 'a "quoted" value', "n": 3}, allow_inline_table=True)
    parsed = tomllib.loads(f"x = {out}")
    assert parsed["x"] == {"note": 'a "quoted" value', "n": 3}


# --- dict rejection (inline tables off, the default) -----------------------


def test_format_scalar_dict_rejected_when_inline_tables_disabled() -> None:
    """Inline tables are opt-in: without ``allow_inline_table`` a dict is
    refused exactly as the original ``_format_toml_scalar`` did."""
    with pytest.raises(TypeError, match=r"does not support value of type dict"):
        _toml.format_scalar({"a": 1})


def test_format_scalar_dict_in_list_rejected_when_disabled() -> None:
    with pytest.raises(TypeError, match=r"does not support value of type dict"):
        _toml.format_scalar([{"a": 1}])


# --- TypeError on unsupported type + message wiring ------------------------


def test_format_scalar_rejects_unsupported_type() -> None:
    with pytest.raises(TypeError, match=r"does not support value of type object"):
        _toml.format_scalar(object())


def test_format_scalar_type_error_prefix_is_configurable() -> None:
    """Each call site keeps its historical error wording via the prefix."""
    with pytest.raises(TypeError, match=r"^_dump_toml does not support value of type"):
        _toml.format_scalar(object(), type_error_prefix="_dump_toml")
    with pytest.raises(TypeError, match=r"^manifest TOML does not support value of type"):
        _toml.format_scalar(object(), type_error_prefix="manifest TOML")


# --- dump_toml: the Config/Lockfile writer (moved from the artifact source tests, N3) ---


def test_dump_toml_rejects_unsupported_scalar() -> None:
    from coding_agent_playbook.toml_writer import dump_toml as _dump_toml

    with pytest.raises(TypeError, match=r"does not support value of type"):
        _dump_toml({"weird": object()})


def test_dump_toml_round_trips_mapping_deeper_than_two_levels() -> None:
    """Formerly pinned as a ``TypeError`` (only Config/Lockfile were written, and
    they nest two levels at most). ``playbook init`` now writes the committed
    tables ``Config`` does not manage back verbatim, and those nest deeper
    (``[metrics.thresholds.<metric>]``), so every depth must round-trip."""
    from coding_agent_playbook.toml_writer import dump_toml as _dump_toml

    data = {"a": {"b": {"c": {"d": 1, "w": 1.0}}}}
    assert_toml_identical(tomllib.loads(_dump_toml(data)), data)


def test_dump_toml_round_trips_nested_dict_in_list_of_tables() -> None:
    """Formerly pinned as a ``TypeError`` (the lockfile's ``[[entries]]`` hold
    scalars only); a preserved user table may hold sub-tables in each element."""
    from coding_agent_playbook.toml_writer import dump_toml as _dump_toml

    data = {"items": [{"key": {"deeper": 1, "flag": True}}]}
    assert_toml_identical(tomllib.loads(_dump_toml(data)), data)
