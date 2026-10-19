"""Tests for the shared TOML writer primitives (``coding_agent_playbook.toml_writer``).

These pin the behaviour the two call sites (the ``config/files.py``
Config/Lockfile writer and ``harness/manifest.py``) share, so a future change to
the escape ladder, ``bool``-before-``int`` ordering, key quoting, the float and
date/time forms (P6), or the ``TypeError`` semantics breaks here rather than
silently in a round-trip elsewhere.
"""

from __future__ import annotations

import datetime as dt
import sys
import tomllib

import pytest

from coding_agent_playbook import toml_writer as _toml
from tests.toml_equality import assert_toml_identical

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
