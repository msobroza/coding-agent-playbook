"""The ``CONFIG_SCHEMA`` format of builtin hook handlers (specs/prK-lifecycle-hooks.md §A.6, §B.5).

A handler declares each ``handler.config`` key it reads as a :class:`ConfigKey`:
its value kind, which validate checks a consumer's ``[hooks.<hook-id>]``
against (H21), and its layer-merge policy, which the overlay merge applies
(``extend`` / ``strictest`` / ``relax`` / ``replace``). Stdlib-only, so sync
reads the same declarations the runtime registers.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["ConfigKey", "ConfigKind", "KeyPolicy"]

type ConfigKind = Literal["string", "integer", "number", "boolean", "list", "table"]
type KeyPolicy = Literal["extend", "strictest", "relax", "replace"]

_KIND_TYPES: Final[Mapping[str, tuple[type, ...]]] = MappingProxyType(
    {
        "string": (str,),
        "integer": (int,),
        "number": (int, float),
        "boolean": (bool,),
        "list": (list, tuple),
        "table": (dict,),
    }
)


@dataclass(frozen=True, slots=True)
class ConfigKey:
    """One ``handler.config`` key of a builtin: its value kind and its layer-merge policy.

    ``policy`` is the §A.6 merge rule; ``order`` ranks a ``strictest`` key's
    modes weakest first and, for a ``string`` key, also lists its only values.

    Example::

        >>> ConfigKey("string", "strictest", ("off", "warn", "block")).accepts("warn")
        True
    """

    kind: ConfigKind
    policy: KeyPolicy = "replace"
    order: tuple[str, ...] = ()

    def accepts(self, value: object) -> bool:
        """Whether ``value`` has this key's kind (and is one of ``order``, when set)."""
        if isinstance(value, bool) and self.kind != "boolean":
            return False  # a bool is an int to Python, never to a TOML author
        if not isinstance(value, _KIND_TYPES[self.kind]):
            return False
        return not (self.kind == "string" and self.order and value not in self.order)
