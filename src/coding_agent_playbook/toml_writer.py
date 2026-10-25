"""Shared hand-rolled TOML *writer* primitives (v1.1 DRY cleanup).

The engine vendors no TOML writer — it reads with stdlib :mod:`tomllib` and
emits with small hand-rolled serializers. Two call sites historically hand-rolled
near-identical scalar/string/key escaping:

* ``filesystem._dump_toml`` — the filesystem state source's Config/Lockfile
  document writer, which since v0.18 lives here as :func:`dump_toml`.
* ``agent_harness/manifest.py`` — the same scalars/strings *plus* inline tables for
  open-dict fields and quoting of non-identifier keys.

This module is the single source of those primitives. The only axis of variation
is whether inline tables (``dict`` values) are permitted: the manifest path and
:func:`dump_toml` (for tables nested in arrays) opt in via ``allow_inline_table=True``;
the default ``False`` rejects dicts with a ``TypeError``. The escape ladder,
``bool``-before-``int`` ordering, and the ``TypeError`` semantics are preserved
byte-for-byte from the original call sites.

Floats and dates/times are rendered too (v0.18): ``playbook init`` and
``playbook check --refresh`` write the committed entries ``Config`` does not
manage back verbatim (``Config.extra_tables``: ``[hooks]``, ``[guardrails]``,
``[metrics]``…), and those may hold any value :mod:`tomllib` parses — inline
values nested to any depth (the walk is iterative, so it never hits Python's
recursion limit), a NaN's sign, and integers too long for ``str`` (written in
hex). Four latent writer bugs were fixed on the way. Two wrote TOML ``tomllib``
refuses: bare keys were not ASCII-only (``café = 1``), and U+007F was written
raw. The third crashed on TOML ``tomllib`` accepts: every ``int`` went through
``str``, which raises ``ValueError`` past ``sys.get_int_max_str_digits()``
digits. The fourth wrote TOML ``tomllib`` *misreads*:
the filesystem source's ``_dump_toml`` wrote keys and header parts raw instead of
through :func:`format_key`, so a key that needs quotes — a dotted dependency name
in ``[detector_cache]`` (``ruamel.yaml``), a ``[user_choices]`` key such as
``"docs.style"`` — was re-read as a nested table. Output bytes change only where
the old writer crashed or its output was refused or misread.
"""

from __future__ import annotations

import datetime as dt
import math
import re
import string
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    #: One table :func:`dump_toml` still has to write: its ``[header]``/``[[header]]``
    #: line (``None`` for the document root), its key path, and the table itself.
    _TomlSection = tuple[str | None, tuple[str, ...], Mapping[str, Any]]

#: TOML 1.0 bare keys: ``A-Za-z0-9_-`` only (``str.isalnum`` also accepts ``é``, ``²``…).
_BARE_KEY_CHARS = frozenset(string.ascii_letters + string.digits + "-_")

#: Any character a TOML basic string cannot hold raw: ``"``, ``\``, U+0000..U+001F, U+007F.
_NEEDS_ESCAPE = re.compile(r'["\\\x00-\x1f\x7f]')
#: The characters with a short TOML escape, in replacement order: the backslash
#: first, so the backslashes the later escapes add are not doubled.
_NAMED_ESCAPES = (("\\", "\\\\"), ('"', '\\"'), ("\n", "\\n"), ("\r", "\\r"), ("\t", "\\t"))
#: The control characters with no short escape, written ``\uXXXX`` instead.
_UNNAMED_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
#: Their escapes, built once: per-match formatting doubled the cost of a run of them.
_UNICODE_ESCAPES = {chr(code): f"\\u{code:04X}" for code in (*range(0x20), 0x7F)}


@dataclass(frozen=True)
class _Rendered:
    """TOML text already rendered, queued between values :func:`format_scalar` has yet to render."""

    text: str


def format_string(value: str) -> str:
    """Render ``value`` as a TOML basic string, escaping control characters.

    ``tomllib`` rejects unescaped control chars (U+0000 through U+001F, and
    U+007F) in basic strings. The named ones (``\\``, ``"``, ``\\n``, ``\\r``,
    ``\\t``) are escaped inline and the remainder fall back to ``\\uXXXX`` so the
    emitted TOML is always parseable.

    Example::

        >>> format_string('say "hi"\\x7f')
        '"say \\\\"hi\\\\"\\\\u007F"'
    """
    if type(value) is not str:
        return _escape_char_by_char(value)
    # Perf: one C-level regex scan, then C-level replaces, instead of a Python
    # step per character: 13x less CPU (250 ms -> 19 ms) on the 6,088 strings,
    # 608,761 characters, that one sync in tests/cli/test_sync.py writes. A
    # str.translate table was no real gain: 9% faster to 13% slower than the
    # loop on those strings across runs, and 1.3-1.7x slower on non-ASCII text
    # (each character it does not map costs a raised and swallowed LookupError).
    if _NEEDS_ESCAPE.search(value) is None:
        return f'"{value}"'
    for char, escape in _NAMED_ESCAPES:
        value = value.replace(char, escape)
    return f'"{_UNNAMED_CONTROL.sub(_unicode_escape, value)}"'


def _unicode_escape(match: re.Match[str]) -> str:
    """The ``\\uXXXX`` escape (uppercase hex) of the one character ``match`` holds.

    Example::

        >>> _unicode_escape(re.fullmatch("\\x1b", "\\x1b"))
        '\\\\u001B'
    """
    return _UNICODE_ESCAPES[match[0]]


def _escape_char_by_char(value: Iterable[str]) -> str:
    """The original per-character escaper, for any ``value`` that is not exactly a ``str``.

    On those, :func:`format_string`'s fast path would change the output or the
    error: ``format()`` writes a ``(str, Enum)`` member as ``Class.NAME``, not its
    text, and a falsy non-``str`` YAML mapping key (``0``, ``null``) reaches it
    through :func:`format_key` and must keep raising, e.g., ``'int' object is
    not iterable``.

    Example::

        >>> _escape_char_by_char(["a", "\\n"])
        '"a\\\\n"'
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
        elif ord(ch) < 0x20 or ch == "\x7f":
            # TOML forbids raw U+0000..U+001F and U+007F (DEL) in basic strings.
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def format_key(key: str) -> str:
    """Render a TOML key — bare when it is a simple ASCII identifier, else quoted.

    Example::

        >>> format_key("python-house-style"), format_key("café"), format_key("a.b")
        ('python-house-style', '"café"', '"a.b"')
    """
    if key and all(ch in _BARE_KEY_CHARS for ch in key):
        return key
    return format_string(key)


def format_scalar(
    value: Any,
    *,
    allow_inline_table: bool = False,
    type_error_prefix: str = "TOML serializer",
) -> str:
    """Render a scalar/collection as an inline TOML value.

    Supports ``bool``, ``int``, ``float``, ``str``, ``datetime.date`` /
    ``datetime.datetime`` / ``datetime.time`` and lists of those, nested to any depth.
    When ``allow_inline_table`` is ``True``, ``dict`` values are rendered as
    inline tables (``{ key = value, ... }``) with their keys formatted via
    :func:`format_key`; when ``False`` (the default), a ``dict`` is unsupported
    and falls through to the ``TypeError`` like any other unhandled type.

    Anything else raises ``TypeError`` so a future schema change fails loudly
    rather than silently producing invalid TOML. ``type_error_prefix`` lets each
    call site preserve its historical error-message wording. A date/time TOML
    cannot hold (a time with an offset, a sub-minute offset) and a negative
    integer too long for ``str`` raise ``ValueError`` saying which and why.

    The walk is iterative, so nesting depth is unbounded: ``tomllib`` parses inline
    values recursively, and a writer that recursed too could hit the recursion
    limit on a value ``tomllib`` accepted, when called from a deeper stack.

    Example::

        >>> format_scalar([1, 2.5, "x", {"k": True}], allow_inline_table=True)
        '[1, 2.5, "x", { k = true }]'
    """
    out: list[str] = []
    pending: list[object] = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, _Rendered):
            out.append(item.text)
            continue
        atom = _format_atom(item)
        if atom is not None:
            out.append(atom)
            continue
        # Reversed so the first child is popped (rendered) first.
        pending.extend(reversed(_expand_collection(item, allow_inline_table, type_error_prefix)))
    return "".join(out)


def _expand_collection(
    value: object, allow_inline_table: bool, type_error_prefix: str
) -> list[object]:
    """One array/inline-table level: its punctuation as ``_Rendered``, its items as-is.

    Example::

        >>> _expand_collection([1, 2], False, "x")
        [_Rendered(text='['), 1, _Rendered(text=', '), 2, _Rendered(text=']')]
    """
    if isinstance(value, list):
        return _delimited("[", [[item] for item in value], "]", empty="[]")
    if allow_inline_table and isinstance(value, dict):
        entries = [[_Rendered(f"{format_key(key)} = "), item] for key, item in value.items()]
        return _delimited("{ ", entries, " }", empty="{}")
    raise TypeError(
        f"{type_error_prefix} does not support value of type {type(value).__name__}: {value!r}"
    )


def _delimited(
    opener: str, entries: list[list[object]], closer: str, *, empty: str
) -> list[object]:
    """``opener entry, entry closer`` as a flat list, or ``empty`` alone for no entries."""
    if not entries:
        return [_Rendered(empty)]
    parts: list[object] = [_Rendered(opener)]
    for index, entry in enumerate(entries):
        if index:
            parts.append(_Rendered(", "))
        parts.extend(entry)
    parts.append(_Rendered(closer))
    return parts


def _format_atom(value: object) -> str | None:
    """The literal for a non-collection TOML value, or ``None`` for anything else."""
    # bool must come before int — `isinstance(True, int)` is True in Python.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return _format_int(value)
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, str):
        return format_string(value)
    if isinstance(value, (dt.date, dt.time)):  # dt.datetime is a dt.date
        return _format_date_time(value)
    return None


def _format_date_time(value: dt.date | dt.time) -> str:
    """RFC 3339 literal for a TOML offset/local date-time, local date or local time.

    ``isoformat`` already matches TOML except where TOML has no such value: a
    time with an offset, or an offset that is not whole minutes — refused with a
    ``ValueError`` naming the value rather than written as unparseable TOML.

    Example::

        >>> _format_date_time(dt.datetime(1979, 5, 27, 7, 32, tzinfo=dt.UTC))
        '1979-05-27T07:32:00+00:00'
    """
    offset = value.utcoffset() if isinstance(value, (dt.datetime, dt.time)) else None
    if offset is not None and isinstance(value, dt.time):
        raise ValueError(
            f"TOML times carry no UTC offset, got {value.isoformat()}; drop its tzinfo"
        )
    if offset is not None and offset % dt.timedelta(minutes=1):
        raise ValueError(
            f"TOML offsets are whole minutes (+HH:MM), got {offset} in {value.isoformat()}"
        )
    return value.isoformat()


def _format_int(value: int) -> str:
    """Decimal, or hex for an integer too long for ``str``.

    ``tomllib`` reads ``0x``/``0o``/``0b`` literals with no digit limit, but
    ``str`` refuses an int past ``sys.get_int_max_str_digits()`` (4300 by
    default); hex is valid TOML and has no such limit. A negative one cannot come
    from ``tomllib`` (TOML hex is unsigned, and decimal has the same limit), so it
    is refused — without its digits, which cannot be rendered either.

    Example::

        >>> _format_int(-17), _format_int(1 << 20000)[:8]
        ('-17', '0x100000')
    """
    try:
        return str(value)
    except ValueError:
        if value < 0:
            raise ValueError(
                f"cannot write a {value.bit_length()}-bit negative integer as TOML: it "
                f"exceeds Python's {sys.get_int_max_str_digits()}-digit int-to-str limit "
                "and TOML hex is unsigned; raise it with sys.set_int_max_str_digits()"
            ) from None
        return hex(value)


def _format_float(value: float) -> str:
    """The shortest literal ``tomllib`` reads back as the same float, sign included.

    ``float.__repr__`` is already TOML-shaped (``1e-05``, ``1e+16``, ``1.0``,
    ``inf``, ``-inf``, ``nan``); calling it on the base class keeps a subclass's
    own repr (NumPy 2: ``np.float64(1.5)``) out of the file. It drops a NaN's
    sign, which ``tomllib`` keeps when it reads ``-nan``, so that one is explicit.

    Example::

        >>> _format_float(1.0), _format_float(-0.0), _format_float(-float("nan"))
        ('1.0', '-0.0', '-nan')
    """
    if math.isnan(value) and math.copysign(1.0, value) < 0:
        return "-nan"
    return float.__repr__(value)


def _format_inline_value(value: Any) -> str:
    """Render a non-table value as a TOML literal (arrays and inline tables included).

    :func:`format_scalar` with inline tables on — only tables nested in arrays
    reach it, since :func:`dump_toml` emits every other table as a ``[header]`` —
    keeping the ``_dump_toml does not support value of type …`` ``TypeError``
    wording from when the writer was the filesystem source's ``_dump_toml``.
    """
    return format_scalar(value, allow_inline_table=True, type_error_prefix="_dump_toml")


def dump_toml(data: Mapping[str, Any]) -> str:
    """Serialize ``data`` to a TOML document :mod:`tomllib` reads back as the same values.

    The ``.coding-agent-playbook.toml`` and lockfile writer (until v0.18 the
    filesystem source's ``_dump_toml``). Writes
    ``Config.to_dict()`` / ``Lockfile.to_dict()`` byte-for-byte as before wherever
    the old output parsed back correctly, and — since ``playbook init`` and
    ``playbook check --refresh`` write back committed entries ``Config`` does not
    manage — anything ``tomllib`` produces: every scalar (:func:`format_scalar`),
    tables at any depth (``[a.b.c]``), arrays of tables at any depth (``[[a.b]]``,
    sub-tables inside each element), and keys that need quoting
    (:func:`format_key`; they used to be written raw, so ``ruamel.yaml = …`` was
    re-read as a nested table). A table's own keys always come before its
    sub-tables. Both walks — this one over tables and ``format_scalar``'s over
    inline values — are iterative, so no nesting depth ``tomllib`` accepts (it
    builds header tables iteratively, with no limit) can raise ``RecursionError``
    here. Unsupported Python values raise ``TypeError``; a date/time TOML cannot
    hold raises ``ValueError``.

    Example::

        >>> print(dump_toml({"n": 1, "a": {"b": {"c": [{"d": 1.5}]}}}), end="")
        n = 1
        <BLANKLINE>
        [a]
        <BLANKLINE>
        [a.b]
        <BLANKLINE>
        [[a.b.c]]
        d = 1.5
    """
    lines: list[str] = []
    # Depth-first, pre-order: each popped table emits its own keys, then pushes
    # its sub-sections in reverse so the first one is written next, with all of
    # its descendants before the second one.
    pending: list[_TomlSection] = [(None, (), data)]
    while pending:
        header, path, table = pending.pop()
        if header is not None:
            if lines:
                lines.append("")
            lines.append(header)
        pending.extend(reversed(_emit_own_keys(lines, path, table)))
    return "\n".join(lines) + "\n"


def _is_toml_section(value: object) -> bool:
    """True for a value written under its own header: a table, or a non-empty
    array whose every item is a table (``[[...]]``). Everything else — an empty
    or mixed array included — is written inline as ``key = value``."""
    if isinstance(value, dict):
        return True
    return isinstance(value, list) and bool(value) and all(isinstance(v, dict) for v in value)


def _emit_own_keys(
    lines: list[str], path: tuple[str, ...], table: Mapping[str, Any]
) -> list[_TomlSection]:
    """Append ``table``'s own ``key = value`` lines; return its sub-sections, in order.

    Own keys go first because TOML puts every key written after a ``[header]``
    inside that header's table.
    """
    sections: list[_TomlSection] = []
    for key, value in table.items():
        if not _is_toml_section(value):
            lines.append(f"{format_key(key)} = {_format_inline_value(value)}")
            continue
        sub_path = (*path, key)
        dotted = ".".join(format_key(part) for part in sub_path)
        if isinstance(value, dict):
            sections.append((f"[{dotted}]", sub_path, value))
        else:
            sections.extend((f"[[{dotted}]]", sub_path, element) for element in value)
    return sections
