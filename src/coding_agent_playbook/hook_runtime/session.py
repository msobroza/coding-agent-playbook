"""Per-session flags, dedupe keys, asked tool calls and deferred notes (specs/prK-lifecycle-hooks.md §D.6.4).

One locked ``sessions/<sha256(session_id)[:16]>/session.json`` per session.
Every list is capped, because the document is read on every dispatch:

- ``once`` keys (context dedupe, one-note-per-session): the newest 1,024;
- ``asked`` tool_use ids (drive the ``override`` log line): the newest 64;
- deferred notes (drained into the next user-facing channel): the newest 5;
- ``debounce`` stamps (the source-changed branch's 2 s window): the newest 64.

When the store is stateless (or a lock stays busy), ``once`` answers True —
dedupe is off, so nothing is silently suppressed — while flags, asked ids and
notes are still kept in this process's memory.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.state import StateUnavailable, session_key

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.state import StateStore

__all__ = [
    "MAX_ASKED_IDS",
    "MAX_DEBOUNCE_KEYS",
    "MAX_DEFERRED_NOTES",
    "MAX_ONCE_KEYS",
    "SessionState",
]

MAX_ASKED_IDS: Final = 64
MAX_DEBOUNCE_KEYS: Final = 64
MAX_DEFERRED_NOTES: Final = 5
MAX_ONCE_KEYS: Final = 1024
#: Joins a tool_use id and the hook that asked about it in the ``asked`` list.
_ASKER_SEP: Final = "\x1f"


def _strings(document: dict[str, Any], key: str) -> list[str]:
    """``document[key]`` as a list of strings; anything else (a hand edit) is empty."""
    value = document.get(key)
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _add_capped(document: dict[str, Any], key: str, item: str, cap: int) -> bool:
    """Append ``item`` to ``document[key]`` unless present, keeping the newest ``cap``."""
    items = _strings(document, key)
    if item in items:
        return False
    document[key] = [*items, item][-cap:]
    return True


def _stamp(document: dict[str, Any], key: str, now: float, window_s: float) -> bool:
    """Stamp ``key`` at ``now`` unless its last stamp is under ``window_s`` old; keep the newest."""
    raw = document.get("debounce")
    stamps = {
        k: v
        for k, v in (raw.items() if isinstance(raw, dict) else ())
        if isinstance(k, str) and isinstance(v, int | float) and not isinstance(v, bool)
    }
    last = stamps.get(key)
    if last is not None and 0 <= now - last < window_s:
        return False
    stamps[key] = now
    newest = sorted(stamps.items(), key=lambda item: item[1])[-MAX_DEBOUNCE_KEYS:]
    document["debounce"] = dict(newest)
    return True


class SessionState:
    """The state of one session, keyed by its sanitized ``session_id``.

    Example::

        >>> session = SessionState(store, ev.session_id)  # doctest: +SKIP
        >>> session.once("ctx:ruff:1a2b3c4d"), session.once("ctx:ruff:1a2b3c4d")
        (True, False)
    """

    def __init__(self, store: StateStore, session_id: str) -> None:
        self._store = store
        self.document = f"sessions/{session_key(session_id)}/session.json"
        self._memory: dict[str, Any] = {}

    @property
    def store(self) -> StateStore:
        """The state root this session lives in (the Stop coordinator keeps its chain there)."""
        return self._store

    def once(self, key: str) -> bool:
        """True only the first time ``key`` is seen this session (always True stateless)."""
        try:
            return self._store.update_json(
                self.document, lambda doc: _add_capped(doc, "once", key, MAX_ONCE_KEYS)
            )
        except StateUnavailable:
            return True

    def debounce(self, key: str, window_s: float) -> bool:
        """True unless ``key`` already passed less than ``window_s`` seconds ago this session.

        The window is on the store clock's wall time (stamps outlive the hook
        process); a clock that went back reopens it. Stateless, it is always
        True: like :meth:`once`, nothing is silently dropped.

        Example::

            >>> session.debounce("validate", 2.0), session.debounce("validate", 2.0)
            ... # doctest: +SKIP
            (True, False)
        """
        now = self._store.clock.time()
        try:
            return self._store.update_json(
                self.document, lambda doc: _stamp(doc, key, now, window_s)
            )
        except StateUnavailable:
            return True

    def flag(self, name: str) -> bool:
        """Whether session flag ``name`` is set (e.g. taint-escalation's ``tainted``)."""
        return name in self._read("flags")

    def set_flag(self, name: str) -> None:
        """Set flag ``name`` until the session ends (or :meth:`clear_flag` drops it)."""
        self._write(lambda doc: _add_capped(doc, "flags", name, MAX_ONCE_KEYS))

    def flags(self) -> tuple[str, ...]:
        """Every flag set this session, read once (taint-escalation's ``taint:*`` sources)."""
        return tuple(dict.fromkeys(self._read("flags")))

    def clear_flag(self, name: str) -> None:
        """Drop flag ``name``; only a ``session_start`` with source ``clear`` does (§E.4).

        ``/clear`` empties the conversation, so the content that set the flag is
        gone from the context even when a harness keeps the session id.

        Example::

            >>> session.set_flag("taint:web"); session.clear_flag("taint:web")  # doctest: +SKIP
            >>> session.flag("taint:web")  # doctest: +SKIP
            False
        """

        def drop(document: dict[str, Any]) -> None:
            kept = [item for item in _strings(document, "flags") if item != name]
            if kept:
                document["flags"] = kept
            else:
                document.pop("flags", None)

        self._write(drop)
        drop(self._memory)  # a flag kept in memory while stateless goes too

    def mark_asked(self, tool_use_id: str, hook_id: str = "") -> None:
        """Remember that ``hook_id`` (or some hook) answered the tool call ``tool_use_id`` with an ask."""
        item = f"{tool_use_id}{_ASKER_SEP}{hook_id}" if hook_id else tool_use_id
        self._write(lambda doc: _add_capped(doc, "asked", item, MAX_ASKED_IDS))

    def was_asked(self, tool_use_id: str) -> bool:
        """Whether ``tool_use_id`` was asked: its post-tool event is then a user override."""
        prefix = f"{tool_use_id}{_ASKER_SEP}"
        return any(i == tool_use_id or i.startswith(prefix) for i in self._read("asked"))

    def askers(self, tool_use_id: str) -> tuple[str, ...]:
        """The hooks that asked about ``tool_use_id``, in the order they were marked.

        The ``override`` decision-log line names them, because the override
        rate is per hook (the evidence for flipping an ask to a deny).
        """
        prefix = f"{tool_use_id}{_ASKER_SEP}"
        hooks = (i[len(prefix) :] for i in self._read("asked") if i.startswith(prefix))
        return tuple(dict.fromkeys(hooks))

    def push_note(self, text: str) -> None:
        """Queue a user note for the next dispatch that can show one."""
        self._write(lambda doc: _add_capped(doc, "notes", text, MAX_DEFERRED_NOTES))

    def drain_notes(self) -> list[str]:
        """Every queued note, oldest first; the queue is empty afterwards."""
        stored: list[str] = []

        def take(document: dict[str, Any]) -> None:
            stored.extend(_strings(document, "notes"))
            document.pop("notes", None)

        with suppress(StateUnavailable):  # stateless: only the in-memory notes remain
            self._store.update_json(self.document, take)
        notes = [*stored, *self._memory.pop("notes", [])]
        return list(dict.fromkeys(notes))[-MAX_DEFERRED_NOTES:]

    def _read(self, key: str) -> list[str]:
        """``key``'s items from the store (when readable) plus those kept in memory."""
        try:
            stored = _strings(self._store.read_json(self.document), key)
        except StateUnavailable:
            stored = []
        return [*stored, *_strings(self._memory, key)]

    def _write(self, change: Callable[[dict[str, Any]], object]) -> None:
        """Apply ``change`` to the stored document, or keep it in memory when stateless."""
        try:
            self._store.update_json(self.document, change)
        except StateUnavailable:
            change(self._memory)
