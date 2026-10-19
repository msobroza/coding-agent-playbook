"""The ``guard_config.hooks.<id>`` record, parsed (specs/prK-lifecycle-hooks.md §A.7, §D.8.2).

The schema is ``schema.HookRecordJson``, whose keys are ``schema.HOOK_RECORD_KEYS``:
``hooks.resolution.resolved.ResolvedHook.to_json()`` returns it and the runtime
may not import ``hooks`` (§D.1), so this module re-reads it field by field and
``test_guard_config.py`` parses a real ``to_json()`` output to pin the two
together. Matcher path globs are compiled here, once, folded for the
platform, so selection never compiles a pattern per event.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook.hook_runtime.config.reader import Malformed, TableReader
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.globs import GlobSet, compile_globs
from coding_agent_playbook.hook_runtime.policy import OnError, effective_on_error

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = ["HandlerKind", "HandlerSpec", "HookRecord", "MatcherSpec", "parse_hook_record"]

type HandlerKind = Literal["builtin", "entry_point", "external"]

_HANDLER_KINDS: Final[tuple[HandlerKind, ...]] = ("builtin", "entry_point", "external")
_ON_ERROR_VALUES: Final[tuple[OnError, ...]] = ("ask", "deny", "open")


@dataclass(frozen=True, slots=True, kw_only=True)
class MatcherSpec:
    """One event's matcher (§A.2): present dimensions are ANDed; empty means any.

    ``tools`` and ``tool_names`` form one dimension, OR-ed: a call matches it
    by its class or by its name.

    ``paths`` is compiled; ``command`` stays as written (regexes the dispatcher
    compiles lazily, only for shell events).
    """

    tools: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()
    paths: GlobSet
    command: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    triggers: tuple[str, ...] = ()
    agent_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class HandlerSpec:
    """How one event runs the hook: a builtin name, an entry-point target, or an argv."""

    kind: HandlerKind
    name: str | None = None
    target: str | None = None
    dist: str | None = None
    argv: tuple[str, ...] = ()
    config: Mapping[str, Any]


@dataclass(frozen=True, slots=True, kw_only=True)
class HookRecord:
    """One enabled hook as the dispatcher selects and runs it.

    ``on_error`` is already clamped per event (§A.2); ``raw`` is the record as
    rendered, which ``HandlerContext.hook`` hands to handlers unchanged.
    """

    id: str
    source_package: str
    events: tuple[EventName, ...]
    priority: int
    matcher: Mapping[EventName, MatcherSpec]
    handlers: Mapping[EventName, HandlerSpec]
    decisions: frozenset[Decision]
    timeout_ms: int
    on_error: Mapping[EventName, OnError]
    supports: frozenset[str]
    mandatory: bool
    script_sha256: str | None
    raw: Mapping[str, Any]


def parse_hook_record(hook_id: str, raw: object, *, platform: str, home: str | None) -> HookRecord:
    """Parse ``guard_config.hooks[hook_id]``; raises :class:`Malformed`.

    Example::

        >>> parse_hook_record("x", resolved.to_json(), platform="linux", home=None).id  # doctest: +SKIP
        'x'
    """
    reader = TableReader(raw, f"hooks.{hook_id}")
    if reader.text("id") != hook_id:
        raise Malformed(
            reader.key("id"), f"expected the record key {hook_id!r}", reader.table["id"]
        )
    events = tuple(_event(reader.key("events"), name) for name in reader.strings("events"))
    return HookRecord(
        id=hook_id,
        source_package=reader.text("source_package"),
        events=events,
        priority=reader.integer("priority"),
        matcher=_per_event(reader.child("matcher"), lambda r: _matcher(r, platform, home)),
        handlers=_per_event(reader.child("handlers", required=True), _handler),
        decisions=frozenset(
            _decision(reader.key("decisions"), d) for d in reader.strings("decisions")
        ),
        timeout_ms=reader.integer("timeout_ms", minimum=1),
        on_error=_on_error(reader.child("on_error")),
        supports=frozenset(reader.strings("supports")),
        mandatory=reader.boolean("mandatory"),
        script_sha256=reader.optional_text("script_sha256"),
        raw=MappingProxyType(reader.table),
    )


def _event(where: str, name: str) -> EventName:
    try:
        return EventName(name)
    except ValueError:
        raise Malformed(where, "expected a canonical event name", name) from None


def _decision(where: str, value: str) -> Decision:
    try:
        return Decision(value)
    except ValueError:
        raise Malformed(
            where, f"expected decisions from {[d.value for d in Decision]}", value
        ) from None


def _per_event[T](reader: TableReader, parse: Callable[[TableReader], T]) -> Mapping[EventName, T]:
    """``{event: parse(child reader)}`` for every key of the per-event object ``reader``."""
    return MappingProxyType(
        {
            _event(reader.where, name): parse(reader.child(name, required=True))
            for name in reader.table
        }
    )


def _matcher(reader: TableReader, platform: str, home: str | None) -> MatcherSpec:
    return MatcherSpec(
        tools=reader.strings("tools", ()),
        tool_names=reader.strings("tool_names", ()),
        paths=compile_globs(reader.strings("paths", ()), platform=platform, home=home),
        command=reader.strings("command", ()),
        sources=reader.strings("sources", ()),
        triggers=reader.strings("triggers", ()),
        agent_types=reader.strings("agent_types", ()),
    )


def _handler(reader: TableReader) -> HandlerSpec:
    kind = reader.choice("kind", _HANDLER_KINDS, "")
    config = reader.frozen("config")
    if kind == "builtin":
        return HandlerSpec(kind="builtin", name=reader.text("name"), config=config)
    if kind == "entry_point":
        target, dist = reader.text("target"), reader.optional_text("dist")
        return HandlerSpec(kind="entry_point", target=target, dist=dist, config=config)
    argv = reader.strings("argv")
    if not argv:
        raise Malformed(reader.key("argv"), "expected a non-empty list of strings", argv)
    return HandlerSpec(kind="external", argv=argv, config=config)


def _on_error(reader: TableReader) -> Mapping[EventName, OnError]:
    clamped: dict[EventName, OnError] = {}
    for name in reader.table:
        event = _event(reader.where, name)
        declared = reader.choice(name, _ON_ERROR_VALUES, "open")
        clamped[event] = effective_on_error(declared, event)
    return MappingProxyType(clamped)
