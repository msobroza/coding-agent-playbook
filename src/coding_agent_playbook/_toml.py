"""Shared hand-rolled TOML *writer* primitives (v1.1 DRY cleanup).

The engine vendors no TOML writer — it reads with stdlib :mod:`tomllib` and
emits with small hand-rolled serializers. Two call sites share these primitives:

* ``sources/filesystem.py`` — the Config/Lockfile document writer
  (``_dump_toml``). Since P6 it also writes back the tables ``Config`` does not
  model (``[hooks]``, ``[links]``, ``[metrics]``…), so values nested below its
  table headers are inline tables.
* ``harness/manifest.py`` — scalars, strings and inline tables for open-dict
  fields, with quoting of non-identifier keys.

This module is the single source of those primitives. Inline tables (``dict``
values) are opt-in through ``allow_inline_table=True``; with the default
``False`` a dict falls through to the ``TypeError``. Every value ``tomllib``
can return is writable — ``bool``, ``int``, ``float``, ``str``, dates, datetimes,
times, arrays and tables — except a non-finite float (refused, P6). The escape
ladder, ``bool``-before-``int`` ordering and the ``TypeError`` wording are
preserved byte-for-byte from the original call sites.
"""

from __future__ import annotations

import datetime
import math
from typing import Any


def format_string(value: str) -> str:
    """Render ``value`` as a TOML basic string, escaping control characters.

    ``tomllib`` rejects unescaped control chars (U+0000 through U+001F) in basic
    strings. The named ones (``\\``, ``"``, ``\\n``, ``\\r``, ``\\t``) are
    escaped inline and the remainder fall back to ``\\uXXXX`` so the emitted
    TOML is always parseable.
    """
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
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def format_key(key: str) -> str:
    """Render a TOML key — bare when it is a simple identifier, else quoted.

    Bare keys are ASCII ``A-Za-z0-9_-`` only: ``str.isalnum`` alone would also
    pass ``é`` or ``²``, which ``tomllib`` refuses unquoted.

    Example::

        >>> format_key("python-house-style"), format_key("a.b")
        ('python-house-style', '"a.b"')
    """
    if key and all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in key):
        return key
    return format_string(key)


def format_scalar(
    value: Any,
    *,
    allow_inline_table: bool = False,
    type_error_prefix: str = "TOML serializer",
) -> str:
    """Render a scalar/collection as an inline TOML value.

    Supports ``bool``, ``int``, finite ``float``, ``str``, ``datetime.date``,
    ``datetime.datetime``, offset-free ``datetime.time`` and lists of those
    (recursively). When ``allow_inline_table`` is ``True``, ``dict`` values are
    rendered as inline tables (``{ key = value, ... }``) with their keys
    formatted via :func:`format_key`; when ``False`` (the default), a ``dict``
    is unsupported and falls through to the ``TypeError`` like any other
    unhandled type.

    Anything else raises ``TypeError`` so a future schema change fails loudly
    rather than silently producing invalid TOML. ``type_error_prefix`` lets each
    call site preserve its historical error-message wording.

    Example::

        >>> format_scalar([0.5, True, "x"])
        '[0.5, true, "x"]'
    """
    atom = _format_atom(value, type_error_prefix)
    if atom is not None:
        return atom
    if isinstance(value, list):
        items = (
            format_scalar(
                item, allow_inline_table=allow_inline_table, type_error_prefix=type_error_prefix
            )
            for item in value
        )
        return "[" + ", ".join(items) + "]"
    if allow_inline_table and isinstance(value, dict):
        inner = ", ".join(
            f"{format_key(k)} = "
            f"{format_scalar(v, allow_inline_table=allow_inline_table, type_error_prefix=type_error_prefix)}"
            for k, v in value.items()
        )
        return "{ " + inner + " }" if inner else "{}"
    raise TypeError(
        f"{type_error_prefix} does not support value of type {type(value).__name__}: {value!r}"
    )


def _format_atom(value: object, type_error_prefix: str) -> str | None:
    """Render a non-container TOML value, or ``None`` when ``value`` is not one."""
    # bool must come before int — `isinstance(True, int)` is True in Python.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return format_string(value)
    if isinstance(value, float):
        return _format_float(value, type_error_prefix)
    # One isoformat() serves all three: a ``datetime`` (a ``date`` subclass)
    # dispatches to its own method, so it keeps its time part.
    if isinstance(value, (datetime.date, datetime.time)):
        return _format_temporal(value, type_error_prefix)
    return None


def _format_float(value: float, type_error_prefix: str) -> str:
    """``repr`` of a finite float: always a valid TOML float (``1.0``, ``1e-05``)."""
    if not math.isfinite(value):
        # Refused rather than written as TOML's inf/nan (P6): no engine table
        # holds one, so it is almost surely a config mistake worth surfacing.
        raise TypeError(f"{type_error_prefix} does not support a non-finite float: {value!r}")
    return repr(value)


def _format_temporal(value: datetime.date | datetime.time, type_error_prefix: str) -> str:
    """ISO 8601 for a TOML date, offset/local datetime or local time."""
    if isinstance(value, datetime.time) and value.tzinfo is not None:
        raise TypeError(
            f"{type_error_prefix} does not support a time with a UTC offset "
            f"(TOML has local times only): {value!r}"
        )
    return value.isoformat()
