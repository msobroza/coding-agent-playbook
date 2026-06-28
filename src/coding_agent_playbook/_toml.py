"""Shared hand-rolled TOML *writer* primitives (v1.1 DRY cleanup).

The engine vendors no TOML writer — it reads with stdlib :mod:`tomllib` and
emits with small hand-rolled serializers. Two call sites historically hand-rolled
near-identical scalar/string/key escaping:

* ``sources/filesystem.py`` — flat Config/Lockfile values (no dicts).
* ``harness/manifest.py`` — the same scalars/strings *plus* inline tables for
  open-dict fields and quoting of non-identifier keys.

This module is the single source of those primitives. The only axis of variation
is whether inline tables (``dict`` values) are permitted: the manifest path opts
in via ``allow_inline_table=True``; the flat Config/Lockfile path keeps the
default ``False`` and so rejects dicts exactly as before (they fall through to a
``TypeError``). The escape ladder, ``bool``-before-``int`` ordering, and the
``TypeError`` semantics are preserved byte-for-byte from the original call sites.
"""

from __future__ import annotations

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
    """Render a TOML key — bare when it is a simple identifier, else quoted."""
    if key and all(ch.isalnum() or ch in "-_" for ch in key):
        return key
    return format_string(key)


def format_scalar(
    value: Any,
    *,
    allow_inline_table: bool = False,
    type_error_prefix: str = "TOML serializer",
) -> str:
    """Render a scalar/collection as an inline TOML value.

    Supports ``bool``, ``int``, ``str`` and lists of those (recursively). When
    ``allow_inline_table`` is ``True``, ``dict`` values are rendered as inline
    tables (``{ key = value, ... }``) with their keys formatted via
    :func:`format_key`; when ``False`` (the default), a ``dict`` is unsupported
    and falls through to the ``TypeError`` like any other unhandled type.

    Anything else raises ``TypeError`` so a future schema change fails loudly
    rather than silently producing invalid TOML. ``type_error_prefix`` lets each
    call site preserve its historical error-message wording.
    """
    # bool must come before int — `isinstance(True, int)` is True in Python.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return format_string(value)
    if isinstance(value, list):
        return (
            "["
            + ", ".join(
                format_scalar(
                    item,
                    allow_inline_table=allow_inline_table,
                    type_error_prefix=type_error_prefix,
                )
                for item in value
            )
            + "]"
        )
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
