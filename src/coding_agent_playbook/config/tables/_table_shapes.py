"""Declarative value shapes for the hook policy tables (specs/prK-lifecycle-hooks.md §B.1, §B.3).

A :class:`TableShape` says what one TOML key must hold and how to store it;
:func:`read_table` checks every key of a decoded table against its shape and
records one problem line per offending key, so the parser can report them all
in one ``ValueError``. Stdlib-only, like ``config.tables.hooks``, which uses it.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, TypeGuard

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


def _keep(value: Any) -> Any:
    return value


@dataclass(frozen=True)
class TableShape:
    """What one key must hold: ``accepts`` checks the decoded value, ``convert`` stores it.

    ``expected`` completes ``"<key>: must be <expected>, got <value>"``.

    Example::

        >>> STRINGS.accepts(["a"]), STRINGS.convert(["a"])
        (True, ('a',))
    """

    expected: str
    accepts: Callable[[object], bool]
    convert: Callable[[Any], Any] = _keep


def _is_strings(value: object) -> TypeGuard[list[str]]:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_positive_int(value: object) -> bool:
    # bool is an int subclass; `true` must not read as 1 day.
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


BOOL: Final = TableShape("true or false", lambda value: isinstance(value, bool))
STRINGS: Final = TableShape("a list of strings", _is_strings, tuple)
POSITIVE_INT: Final = TableShape("a positive integer", _is_positive_int)
TEXT: Final = TableShape(
    "a non-empty string", lambda value: isinstance(value, str) and bool(value.strip())
)


def one_of(*allowed: str) -> TableShape:
    """A string drawn from ``allowed``.

    Example::

        >>> one_of("deny", "warn").expected
        "one of 'deny', 'warn'"
    """
    return TableShape(f"one of {_quoted(allowed)}", lambda value: value in allowed)


def subset_of(*allowed: str, note: str = "") -> TableShape:
    """A list of strings, each drawn from ``allowed``; ``note`` explains a common slip.

    Example::

        >>> subset_of("default", "opt-in").accepts(["opt-in"])
        True
    """
    expected = f"a list drawn from {_quoted(allowed)}" + (f" ({note})" if note else "")

    def accepts(value: object) -> bool:
        return _is_strings(value) and all(item in allowed for item in value)

    return TableShape(expected, accepts, tuple)


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _is_iso_date_text(value: object) -> bool:
    if not isinstance(value, str) or _ISO_DATE.fullmatch(value) is None:
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


#: D-Q3: a TOML *string*, so a date literal (decoded as ``datetime.date``) is refused.
ISO_DATE_TEXT: Final = TableShape(
    'a "YYYY-MM-DD" string (quoted: a TOML string, not a TOML date literal)', _is_iso_date_text
)


def read_table(
    table: Mapping[str, Any],
    shapes: Mapping[str, TableShape],
    *,
    label: str,
    problems: list[str],
    also_allowed: str = "",
) -> dict[str, Any]:
    """The converted value of every well-shaped key; each other key adds a line to ``problems``.

    ``label`` (``"[hooks]"``) heads every line, which names the key, the value
    and the expected shape, or for an unknown key the allowed keys (then
    ``also_allowed``, e.g. ``"a [hooks.<hook-id>] table"``).

    Example::

        >>> problems = []
        >>> read_table({"on": 1}, {"enabled": BOOL}, label="[hooks]", problems=problems)
        {}
        >>> problems
        ["[hooks] unknown key 'on'; allowed: enabled"]
    """
    allowed = ", ".join(sorted(shapes)) + (f", or {also_allowed}" if also_allowed else "")
    values: dict[str, Any] = {}
    for key, value in table.items():
        shape = shapes.get(key)
        if shape is None:
            problems.append(f"{label} unknown key {key!r}; allowed: {allowed}")
        elif not shape.accepts(value):
            problems.append(shape_problem(label, key, shape.expected, value))
        else:
            values[key] = shape.convert(value)
    return values


def shape_problem(label: str, key: str, expected: str, value: object) -> str:
    """One problem line: ``"<label> <key>: must be <expected>, got <value>"``."""
    return f"{label} {key}: must be {expected}, got {value!r}"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(repr(value) for value in values)
