"""Bounded reads of the runtime's config files and typed reads of their JSON (§D.8).

Sync renders the file and validate checks it, so a bad value here means the
file was hand-edited or written by another engine version. Every problem is a
:class:`Malformed` naming the dotted key and the offending value, which the
loader turns into one ``ConfigFault``: the runtime never raises on its config.
"""

from __future__ import annotations

import os
import stat
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__ = ["FileTooLarge", "Malformed", "TableReader", "read_small_file"]

_MISSING: Final = object()
# O_NONBLOCK: a FIFO planted at the path must not hang the hook in open().
_READ_FLAGS: Final = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)


class FileTooLarge(ValueError):
    """A config file over its read limit; the caller decides whether that fails safe."""


def read_small_file(path: Path, limit: int) -> tuple[bytes, os.stat_result]:
    """The bytes and stat of a regular file of at most ``limit`` bytes.

    Raises ``OSError`` when it cannot be opened, ``ValueError`` when it is not
    a regular file, and :class:`FileTooLarge` when it is larger than ``limit``.

    Example::

        >>> read_small_file(Path("pyproject.toml"), 1 << 20)[0][:1]  # doctest: +SKIP
        b'#'
    """
    descriptor = os.open(path, _READ_FLAGS)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"{path.name} is not a regular file")
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise FileTooLarge(f"{path.name} is larger than {limit} bytes")
    return data, info


class Malformed(ValueError):
    """A ``guard_config.json`` value of the wrong shape; the message starts with its key.

    Example::

        >>> str(Malformed("hooks.x.priority", "expected an integer", "high"))
        "hooks.x.priority: expected an integer, got 'high'"
    """

    def __init__(self, where: str, expected: str, value: object) -> None:
        shown = repr(value)
        shown = shown if len(shown) <= 80 else shown[:77] + "..."
        super().__init__(f"{where}: {expected}, got {shown}")
        self.where = where


class TableReader:
    """Reads typed keys of the JSON object ``table`` found at dotted path ``where``.

    A key that is absent returns the given default; a key that is present
    with the wrong type raises :class:`Malformed`.

    Example::

        >>> TableReader({"a": 1}, "cfg").integer("a")
        1
    """

    def __init__(self, table: object, where: str) -> None:
        if not isinstance(table, dict):
            raise Malformed(where, "expected an object", table)
        self.table: dict[str, Any] = table
        self.where = where

    def key(self, name: str) -> str:
        """The dotted path of key ``name``."""
        return f"{self.where}.{name}" if self.where else name

    def text(self, name: str, default: object = _MISSING) -> str:
        """A string value."""
        value = self._value(name, "expected a string", default)
        if not isinstance(value, str):
            raise Malformed(self.key(name), "expected a string", value)
        return value

    def optional_text(self, name: str) -> str | None:
        """A string or ``null`` value; absent is ``None``."""
        value = self.table.get(name)
        if value is not None and not isinstance(value, str):
            raise Malformed(self.key(name), "expected a string or null", value)
        return value

    def integer(self, name: str, default: object = _MISSING, *, minimum: int | None = None) -> int:
        """An integer value (never a bool), at least ``minimum`` when given."""
        value = self._value(name, "expected an integer", default)
        if not isinstance(value, int) or isinstance(value, bool):
            raise Malformed(self.key(name), "expected an integer", value)
        if minimum is not None and value < minimum:
            raise Malformed(self.key(name), f"expected an integer >= {minimum}", value)
        return value

    def boolean(self, name: str, default: object = _MISSING) -> bool:
        """A boolean value."""
        value = self._value(name, "expected true or false", default)
        if not isinstance(value, bool):
            raise Malformed(self.key(name), "expected true or false", value)
        return value

    def strings(self, name: str, default: object = _MISSING) -> tuple[str, ...]:
        """A list of strings, as a tuple."""
        value = self._value(name, "expected a list of strings", default)
        if not isinstance(value, list | tuple) or not all(isinstance(i, str) for i in value):
            raise Malformed(self.key(name), "expected a list of strings", value)
        return tuple(value)

    def child(self, name: str, *, required: bool = False) -> TableReader:
        """A reader for the nested object ``name`` (an empty one when absent and optional)."""
        if name not in self.table and not required:
            return TableReader({}, self.key(name))
        return TableReader(self.table.get(name), self.key(name))

    def frozen(self, name: str) -> Mapping[str, Any]:
        """The nested object ``name`` as a read-only mapping (empty when absent)."""
        return MappingProxyType(self.child(name).table)

    def choice(self, name: str, allowed: tuple[str, ...], default: str) -> str:
        """A string that must be one of ``allowed``."""
        value = self.text(name, default)
        if value not in allowed:
            raise Malformed(self.key(name), f"expected one of {list(allowed)}", value)
        return value

    def _value(self, name: str, expected: str, default: object) -> object:
        """``table[name]``, else ``default``; a required key that is absent is malformed."""
        if name in self.table:
            return self.table[name]
        if default is _MISSING:
            raise Malformed(self.key(name), f"missing; {expected}", None)
        return default
