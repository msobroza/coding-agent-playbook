"""Per-session flags, dedupe keys, asked tool calls and deferred notes (specs/prK-lifecycle-hooks.md §D.6.4).

One locked ``sessions/<sha256(session_id)[:16]>/session.json`` per session.
Every list is capped, because the document is read on every dispatch:

- ``once`` keys (context dedupe, one-note-per-session): the newest 1,024;
- ``asked`` tool_use ids (drive the ``override`` log line): the newest 64;
- deferred notes (drained into the next user-facing channel): the newest 5.

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

__all__ = ["MAX_ASKED_IDS", "MAX_DEFERRED_NOTES", "MAX_ONCE_KEYS", "SessionState"]

MAX_ASKED_IDS: Final = 64
MAX_DEFERRED_NOTES: Final = 5
MAX_ONCE_KEYS: Final = 1024


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

    def once(self, key: str) -> bool:
        """True only the first time ``key`` is seen this session (always True stateless)."""
        try:
            return self._store.update_json(
                self.document, lambda doc: _add_capped(doc, "once", key, MAX_ONCE_KEYS)
            )
        except StateUnavailable:
            return True

    def flag(self, name: str) -> bool:
        """Whether session flag ``name`` is set (e.g. taint-escalation's ``tainted``)."""
        return name in self._read("flags")

    def set_flag(self, name: str) -> None:
        """Set flag ``name`` until the session ends; flags never clear within a session."""
        self._write(lambda doc: _add_capped(doc, "flags", name, MAX_ONCE_KEYS))

    def mark_asked(self, tool_use_id: str) -> None:
        """Remember that the tool call ``tool_use_id`` was answered with an ask."""
        self._write(lambda doc: _add_capped(doc, "asked", tool_use_id, MAX_ASKED_IDS))

    def was_asked(self, tool_use_id: str) -> bool:
        """Whether ``tool_use_id`` was asked: its post-tool event is then a user override."""
        return tool_use_id in self._read("asked")

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
