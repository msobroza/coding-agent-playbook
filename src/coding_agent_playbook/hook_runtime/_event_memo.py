"""One event's shared memo: work several hooks need, computed once per dispatch (specs/prK-hook-pack.md §E.3).

The dispatcher builds one :class:`EventMemo` per event and hands the same
instance to every hook's ``HandlerContext``, so the first handler that needs
a value (the D1 ruff diagnostics of an edited file) computes it and the rest
reuse it. It lives exactly as long as the event: ``CanonicalEvent`` is
frozen, and a module-level cache would leak between the in-process
``run_event`` calls of ``simulate`` and the tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable

__all__ = ["EventMemo"]


class EventMemo:
    """A per-event ``key -> value`` cache; values are computed on first request.

    Example::

        >>> memo = EventMemo()
        >>> memo.get_or_compute(("d1", "a.py"), lambda: 1), memo.get_or_compute(("d1", "a.py"), lambda: 2)
        (1, 1)
    """

    __slots__ = ("_values",)

    def __init__(self) -> None:
        self._values: dict[Hashable, Any] = {}

    def get_or_compute[T](self, key: Hashable, compute: Callable[[], T]) -> T:
        """The value stored under ``key``, computing and storing it on the first call.

        An exception from ``compute`` stores nothing, so the next caller retries.
        """
        if key not in self._values:
            self._values[key] = compute()
        value: T = self._values[key]
        return value

    def __contains__(self, key: object) -> bool:
        return key in self._values
