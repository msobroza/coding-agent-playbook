"""How ``playbook check`` judges managed ``settings.json`` elements (specs/prK-lifecycle-hooks.md §C.2.6).

The element match itself (an element of the array at ``<pointer>`` with the
recorded canonical hash) is ``lockfile.drift.managed_drift``, shared with the hook
runtime. This module adds the two Claude-specific refinements ``playbook
check`` passes to ``lockfile.drift.drift_entries``:

- :func:`settings_document`: the strict parser Claude Code itself applies, so
  a file Claude would reject is reported ``unreadable`` with its line and column;
- :func:`stray_launcher_edited`: a missing managed hook group whose array still
  holds an unrecorded launcher-only group was hand-edited, not removed.

Stdlib-only apart from the settings parser.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.adapters.claude_code.settings._plan import launcher_kind
from coding_agent_playbook.adapters.claude_code.settings.managed_merge import (
    SettingsMergeError,
    decode_settings,
    parse_settings,
)
from coding_agent_playbook.lockfile.drift import ScopedUnreadable, managed_drift

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.lockfile.drift import DriftItem
    from coding_agent_playbook.lockfile.model import LockEntry

__all__ = ["managed_entry_drift", "settings_document", "stray_launcher_edited"]

_HOOKS_POINTER: Final = "/hooks/"


def settings_document(data: bytes | None, rel: str) -> object:
    """``data`` parsed as Claude Code parses settings; absent or blank is ``{}``.

    Raises ``ScopedUnreadable("line L, col C: <message>")`` for what Claude rejects.

    Example::

        >>> settings_document(b'{"model": "x"}', ".claude/settings.json")
        {'model': 'x'}
    """
    try:
        return parse_settings(decode_settings(data, path=rel), path=rel)
    except SettingsMergeError as exc:
        raise ScopedUnreadable(f"line {exc.line}, col {exc.col}: {exc.message}") from None


def stray_launcher_edited(
    pointer: str, items: Sequence[object], hashes: Sequence[str], recorded: frozenset[str]
) -> bool:
    """Whether a hook array holds a launcher-only group no entry recorded: our group, edited.

    Example::

        >>> stray_launcher_edited("/permissions/allow", [], [], frozenset())
        False
    """
    if not pointer.startswith(_HOOKS_POINTER):
        return False
    return any(
        isinstance(item, dict) and launcher_kind(item) == "suspect" and digest not in recorded
        for item, digest in zip(items, hashes, strict=True)
    )


def managed_entry_drift(doc: object, entries: Iterable[LockEntry]) -> list[DriftItem]:
    """The scoped ``entries`` no element of ``doc`` matches, ``edited`` per :func:`stray_launcher_edited`.

    Example::

        >>> managed_entry_drift({}, [])
        []
    """
    return managed_drift(doc, entries, edited=stray_launcher_edited)
