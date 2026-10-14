"""Tests for the shared TOML writer primitives (``coding_agent_playbook._toml``).

These pin the behaviour the two call sites (the ``sources/filesystem.py``
Config/Lockfile writer and ``harness/manifest.py``) share, so a future change to
the escape ladder, ``bool``-before-``int`` ordering, key quoting, the float and
date/time forms (P6), or the ``TypeError`` semantics breaks here rather than
silently in a round-trip elsewhere.
"""

from __future__ import annotations

import datetime
import math
import tomllib

import pytest

from coding_agent_playbook import _toml

# --- scalars ---------------------------------------------------------------


def test_format_scalar_bool() -> None:
    assert _toml.format_scalar(True) == "true"
    assert _toml.format_scalar(False) == "false"


def test_format_scalar_int() -> None:
    assert _toml.format_scalar(0) == "0"
    assert _toml.format_scalar(42) == "42"
    assert _toml.format_scalar(-7) == "-7"


def test_format_scalar_bool_before_int() -> None:
    """``isinstance(True, int)`` is True; bool must be handled first so a bool
    never renders as ``1``/``0``."""
    assert _toml.format_scalar(True) == "true"
    assert _toml.format_scalar(False) == "false"


def test_format_scalar_str_simple() -> None:
    assert _toml.format_scalar("hello") == '"hello"'


@pytest.mark.parametrize("value", [0.5, 1.0, -0.0, 1e-05, 1e300, 123456.789])
def test_format_scalar_float(value: float) -> None:
    """Floats render as ``repr`` (P6): a preserved ``[metrics]`` table holds
    ``max_worsening = 0.5`` and ``weights`` like ``x = 1.0``, so a re-run of
    ``playbook init`` must write them back rather than raise."""
    out = _toml.format_scalar(value)
    assert out == repr(value)
    parsed = tomllib.loads(f"x = {out}")["x"]
    assert isinstance(parsed, float)
    assert repr(parsed) == repr(value)  # -0.0 keeps its sign


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_format_scalar_rejects_nan_inf(value: float) -> None:
    with pytest.raises(TypeError, match=r"non-finite float") as exc:
        _toml.format_scalar(value, type_error_prefix="_dump_toml")
    assert repr(value) in str(exc.value)
    assert str(exc.value).startswith("_dump_toml ")


def test_format_scalar_date() -> None:
    out = _toml.format_scalar(datetime.date(2026, 10, 14))
    assert out == "2026-10-14"
    assert tomllib.loads(f"x = {out}")["x"] == datetime.date(2026, 10, 14)


@pytest.mark.parametrize(
    "value",
    [
        datetime.datetime(2026, 10, 14, 16, 4, 5, tzinfo=datetime.UTC),
        datetime.datetime(
            2026, 10, 14, 16, 4, 5, 250000, tzinfo=datetime.timezone(datetime.timedelta(hours=2))
        ),
        datetime.datetime(2026, 10, 14, 16, 4, 5),
    ],
    ids=["offset-utc", "offset-plus-two-fraction", "local"],
)
def test_format_scalar_datetime_offset_and_local(value: datetime.datetime) -> None:
    out = _toml.format_scalar(value)
    assert out == value.isoformat()
    assert tomllib.loads(f"x = {out}")["x"] == value


@pytest.mark.parametrize(
    "value", [datetime.time(7, 30), datetime.time(7, 30, 15, 500)], ids=["whole", "fraction"]
)
def test_format_scalar_time(value: datetime.time) -> None:
    out = _toml.format_scalar(value)
    assert out == value.isoformat()
    assert tomllib.loads(f"x = {out}")["x"] == value


def test_format_scalar_rejects_time_with_offset() -> None:
    """TOML has no offset time; ``isoformat`` would emit ``07:30:00+00:00``,
    which ``tomllib`` refuses, so it must fail loudly instead."""
    value = datetime.time(7, 30, tzinfo=datetime.UTC)
    with pytest.raises(TypeError, match=r"offset") as exc:
        _toml.format_scalar(value)
    assert repr(value) in str(exc.value)


def test_format_scalar_datetime_checked_before_date() -> None:
    """``datetime`` subclasses ``date``: it must keep its time part."""
    value = datetime.datetime(2026, 10, 14, 9, 0)
    assert _toml.format_scalar(value) == "2026-10-14T09:00:00"
    assert _toml.format_scalar([value.date(), value]) == "[2026-10-14, 2026-10-14T09:00:00]"


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


@pytest.mark.parametrize("key", ["café", "π", "x²"])
def test_format_key_quotes_non_ascii(key: str) -> None:
    """TOML bare keys are ASCII ``A-Za-z0-9_-`` only, but ``str.isalnum`` is
    True for ``é``/``π``/``²``: a preserved user key must still parse back."""
    out = _toml.format_key(key)
    assert out == f'"{key}"'
    assert tomllib.loads(f"{out} = 1") == {key: 1}


# --- lists -----------------------------------------------------------------


def test_format_scalar_empty_list() -> None:
    assert _toml.format_scalar([]) == "[]"


def test_format_scalar_list_of_scalars() -> None:
    assert _toml.format_scalar([1, "two", True]) == '[1, "two", true]'


def test_format_scalar_nested_list() -> None:
    assert _toml.format_scalar([["a"], []]) == '[["a"], []]'


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
