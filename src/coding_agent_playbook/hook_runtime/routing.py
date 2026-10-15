"""Where a hook's handler runs on an event: the sync fan-out, the async dispatch, or nowhere (§C.2.1).

Three routes, decided from the handler binding alone so sync (registrations,
deadlines, ``guard_config.logging``) and the runtime (selection) never disagree:

- ``sink``: a decision sink (:data:`DECISION_SINK_HANDLERS`, guard-decision-log's
  ``decision_log``). It is the switch for the dispatcher's own decision log
  (pipeline step 8), so it has no registration, adds nothing to the §D.4
  deadline sum and is never selected as a handler (specs/prK-hook-pack.md §E.5);
- ``async``: an output-free handler declaring ``ASYNC_SAFE = True``
  (:data:`ASYNC_SAFE_HANDLERS`), bound to ``post_tool_use`` by a hook whose
  ``decisions`` are exactly ``[none]``. It runs only in the one extra async
  ``PostToolUse`` dispatch (OQ-19, the accepted amendment to L3), never in the
  synchronous one, so a ``Read`` costs no blocking interpreter start;
- ``sync``: everything else, the in-process fan-out of the one registration.

The sets are static (no handler import to route): a registry test pins them to
the ``ASYNC_SAFE`` module attributes and the sink declarations. Stdlib-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "ASYNC_AUDIT_MODE",
    "ASYNC_EVENT",
    "ASYNC_SAFE_HANDLERS",
    "DECISION_SINK_HANDLERS",
    "HandlerRoute",
    "handler_route",
    "is_sink",
]

type HandlerRoute = Literal["sync", "async", "sink"]

#: Builtins that receive the dispatcher's decisions and can never return one.
DECISION_SINK_HANDLERS: Final = frozenset({"decision_log"})
#: Builtins whose module declares ``ASYNC_SAFE = True``: they write no output.
ASYNC_SAFE_HANDLERS: Final = frozenset({"activity_log"})
#: The only event with an async registration (Claude's async hooks never block).
ASYNC_EVENT: Final = "post_tool_use"
#: ``guard_config.logging.audit_mode`` when an async route exists: the synchronous
#: ``post_tool_use`` dispatch then skips async-routed handlers (the async one runs them).
ASYNC_AUDIT_MODE: Final = "async"
_NONE_ONLY: Final = frozenset({"none"})


def is_sink(kind: str, name: str | None) -> bool:
    """Whether a handler binding is a decision sink (a builtin of :data:`DECISION_SINK_HANDLERS`).

    Example::

        >>> is_sink("builtin", "decision_log"), is_sink("builtin", "guard_x")
        (True, False)
    """
    return kind == "builtin" and name in DECISION_SINK_HANDLERS


def handler_route(
    event: str, *, kind: str, name: str | None, decisions: Iterable[str]
) -> HandlerRoute:
    """The route of a hook's handler binding on ``event``: ``sync``, ``async`` or ``sink``.

    ``decisions`` are the hook's declared decisions (values, e.g. ``"none"``).

    Example::

        >>> handler_route("post_tool_use", kind="builtin", name="activity_log", decisions=["none"])
        'async'
        >>> handler_route("session_start", kind="builtin", name="activity_log", decisions=["none"])
        'sync'
    """
    if is_sink(kind, name):
        return "sink"
    if (
        event == ASYNC_EVENT
        and kind == "builtin"
        and name in ASYNC_SAFE_HANDLERS
        and frozenset(decisions) == _NONE_ONLY
    ):
        return "async"
    return "sync"
