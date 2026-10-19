"""A builtin's handler config, read against its own ``CONFIG_SCHEMA`` (specs/prT-package-layout.md §8 B.7).

The dispatcher hands every handler its merged ``handler.config`` as a plain
``Mapping`` (``HandlerContext.config``). A builtin wraps it in a
:class:`HookConfig` built from the same ``CONFIG_SCHEMA`` validate checks a
consumer's ``[hooks.<hook-id>]`` against (H21), so the kind checks live here
once while each handler keeps its own default, emptiness and range rule at the
call site. Out-of-tree handlers keep receiving the same ``Mapping`` and may
build a ``HookConfig`` from their own schema.

Stdlib-only, because every hot path loads it: ``hook_runtime.config.keys`` is
imported for type checking only.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.config.keys import ConfigKey

__all__ = ["Blanks", "Bound", "HookConfig"]

#: Which str items of a list key a read keeps: all, the non-empty, or the non-blank ones.
type Blanks = Literal["keep", "drop_empty", "drop_blank"]
#: What an int outside ``minimum``..``maximum`` reads as: the caller's default, or the bound.
type Bound = Literal["default", "clamp"]
type _ReadMethod = Literal["flag", "choice", "integer", "strings", "value"]

#: The declared kinds each read method serves, and how a mismatch error names them.
_READ_KINDS: Final[Mapping[_ReadMethod, tuple[frozenset[str], str]]] = MappingProxyType(
    {
        "flag": (frozenset({"boolean"}), "a boolean"),
        "choice": (frozenset({"string"}), "a string"),
        "integer": (frozenset({"integer", "number"}), "an integer or number"),
        "strings": (frozenset({"list"}), "a list"),
        "value": (frozenset({"regex", "table"}), "a regex or table"),
    }
)


class HookConfig:
    """A builtin's merged ``handler.config``, read against its own ``CONFIG_SCHEMA``.

    A value of the wrong kind reads as the caller's default (validate refuses it in a
    consumer's ``[hooks.<hook-id>]``, H21; the digest check keeps the file as sync wrote
    it). Reading a key the schema does not declare raises ``KeyError`` naming the key and
    the declared keys, and a read method that does not match the declared kind raises
    ``TypeError``: both are programming errors the handler's own tests surface. Nothing
    is read until a method asks, so a handler builds one before its early returns.

    Example::

        >>> config = HookConfig({"protected_branches": ["main", ""]}, CONFIG_SCHEMA)
        >>> config.strings("protected_branches", ("main", "master"))
        ('main',)
    """

    __slots__ = ("_raw", "_schema")

    def __init__(self, raw: Mapping[str, object], schema: Mapping[str, ConfigKey]) -> None:
        self._raw = raw
        self._schema = schema

    def flag(self, key: str, default: bool) -> bool:
        """The value when it is a bool (never ``0`` or ``"false"``), else ``default``.

        Example: ``config.flag("push_requires_green", False)`` is ``False`` for ``"yes"``.
        """
        value = self._read(key, "flag")
        return value if isinstance(value, bool) else default

    def choice(self, key: str, default: str) -> str:
        """The value when it is one of the key's declared ``ConfigKey.order``, else ``default``.

        A string key that declares no order reads any string, as validate accepts it.

        Example: ``config.choice("mode", "off")`` is ``"off"`` for ``"block"``.
        """
        value = self._read(key, "choice")
        return value if isinstance(value, str) and self._schema[key].accepts(value) else default

    def integer(
        self,
        key: str,
        default: int,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        below: Bound = "default",
        above: Bound = "default",
    ) -> int:
        """An int that is not a bool; out of range reads as ``default`` or is clamped.

        Example: ``config.integer("max_blocks", 2, minimum=1, maximum=8, above="clamp")``
        is ``8`` for ``99`` and ``2`` for ``0`` or ``True``.
        """
        value = self._read(key, "integer")
        if not isinstance(value, int) or isinstance(value, bool):
            return default
        if minimum is not None and value < minimum:
            return minimum if below == "clamp" else default
        if maximum is not None and value > maximum:
            return maximum if above == "clamp" else default
        return value

    def strings(
        self,
        key: str,
        default: tuple[str, ...] = (),
        *,
        blanks: Blanks = "drop_empty",
        strict: bool = False,
    ) -> tuple[str, ...]:
        """The str items of a list (a non-list is ``default``), kept as ``blanks`` says.

        ``strict`` raises ``ValueError`` naming the key for anything but a list of str
        (an absent key still reads as ``default``).

        Example: ``config.strings("allowed_hosts", blanks="drop_blank")`` is ``("pypi.org",)``
        for ``["pypi.org", " ", 3]``.
        """
        value = self._read(key, "strings")
        if strict and key in self._raw:
            _require_strings(key, value)
        if not isinstance(value, list | tuple):
            return default
        return tuple(item for item in value if isinstance(item, str) and _kept(item, blanks))

    def value(self, key: str) -> object:
        """The raw value of a ``regex`` or ``table`` key (``None`` when absent), for its row parser.

        Example: ``extra_row_hits(command.segments, config.value("extra_rows"))``.
        """
        return self._read(key, "value")

    def _read(self, key: str, method: _ReadMethod) -> object:
        """``key``'s raw value, once the schema declares it with a kind ``method`` serves."""
        spec = self._schema.get(key)
        if spec is None:
            declared = ", ".join(sorted(self._schema)) or "none"
            raise KeyError(f"{key!r} is not a config key of this handler; declared: {declared}")
        kinds, expected = _READ_KINDS[method]
        if spec.kind not in kinds:
            raise TypeError(
                f"HookConfig.{method}({key!r}) reads {expected} key; {key!r} is declared {spec.kind!r}"
            )
        return self._raw.get(key)


def _require_strings(key: str, value: object) -> None:
    if not isinstance(value, list | tuple) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"handler config {key!r} must be a list of strings, got {value!r}")


def _kept(item: str, blanks: Blanks) -> bool:
    """Whether a str item survives ``blanks``: ``drop_blank`` also drops whitespace-only ones."""
    if blanks == "keep":
        return True
    return bool(item.strip()) if blanks == "drop_blank" else item != ""
