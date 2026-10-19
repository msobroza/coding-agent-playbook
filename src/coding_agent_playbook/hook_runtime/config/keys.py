"""The ``CONFIG_SCHEMA`` format of builtin hook handlers (specs/prK-lifecycle-hooks.md §A.6, §B.5).

A handler declares each ``handler.config`` key it reads as a :class:`ConfigKey`:
its value kind, which validate checks a consumer's ``[hooks.<hook-id>]``
against (H21), and its layer-merge policy, which the overlay merge applies
(``extend`` / ``strictest`` / ``relax`` / ``replace``). Stdlib-only, so sync
reads the same declarations the runtime registers.

The ``regex`` kind is a list of patterns, each a string or a row table with a
``regex`` string (specs/prK-hook-pack.md §E.4: secret ``extra_patterns``,
destructive ``extra_rows``, convention ``rules``). Its shape is checked here;
validate also screens every pattern (``security.secrets.screen_regex``), since
the hooks run it on agent-controlled text.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["ConfigKey", "ConfigKind", "KeyPolicy", "regex_of"]

type ConfigKind = Literal["string", "integer", "number", "boolean", "list", "table", "regex"]
type KeyPolicy = Literal["extend", "strictest", "relax", "replace"]

_KIND_TYPES: Final[Mapping[str, tuple[type, ...]]] = MappingProxyType(
    {
        "string": (str,),
        "integer": (int,),
        "number": (int, float),
        "boolean": (bool,),
        "list": (list, tuple),
        "table": (dict,),
        "regex": (list, tuple),
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
        if self.kind == "regex":
            return isinstance(value, list | tuple) and all(regex_of(i) is not None for i in value)
        return not (self.kind == "string" and self.order and value not in self.order)


def regex_of(item: object) -> str | None:
    """The pattern of one ``regex``-kind item: a string, or a table's ``regex`` string.

    Example::

        >>> regex_of({"id": "acme-token", "regex": "acme_[0-9a-f]{32}"})
        'acme_[0-9a-f]{32}'
    """
    if isinstance(item, str):
        return item
    pattern = item.get("regex") if isinstance(item, dict) else None
    return pattern if isinstance(pattern, str) else None
