"""Which managed ``settings.json`` elements drifted (specs/prK-lifecycle-hooks.md §C.2.6).

``playbook check`` cannot byte-compare a file it co-owns with the user, so a
scoped lock entry (``json:<pointer>``) is checked by looking for an element of
the array at ``<pointer>`` whose canonical hash equals the recorded one. User
keys, user hook groups, reformatting and key order never count as drift.

Stdlib-only; it works on the parsed document (:func:`.claude_settings.parse_settings`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook.adapters._settings_plan import (
    canonical_json,
    launcher_kind,
    pointer_keys,
)
from coding_agent_playbook.lockfile import compute_hash

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.lockfile import LockEntry

__all__ = ["DriftKind", "ManagedDrift", "managed_entry_drift"]

DriftKind = Literal["edited", "missing"]
_JSON_SCOPE: Final = "json:"
_HOOKS_POINTER: Final = "/hooks/"


@dataclass(frozen=True)
class ManagedDrift:
    """One scoped entry with no matching element: hand-edited, or gone.

    Example: ``ManagedDrift(entry, "missing").line()``.
    """

    entry: LockEntry
    kind: DriftKind

    def line(self) -> str:
        """``managed entry <kind>: <path>#<pointer>`` (the ``playbook check`` drift line)."""
        pointer = self.entry.scope.removeprefix(_JSON_SCOPE)
        return f"managed entry {self.kind}: {self.entry.path}#{pointer}"


def managed_entry_drift(doc: object, entries: Iterable[LockEntry]) -> list[ManagedDrift]:
    """The scoped ``entries`` that no element of ``doc`` matches, in entry order.

    A managed hook group whose array still holds an unrecorded launcher-only
    group was ``edited``; anything else (a deleted group, a removed string, an
    absent array) is ``missing``. Whole-file entries are skipped.

    Example::

        >>> managed_entry_drift({}, lock.entries)  # doctest: +SKIP
        [ManagedDrift(entry=..., kind='missing')]
    """
    scoped = [entry for entry in entries if entry.scope.startswith(_JSON_SCOPE)]
    drift: list[ManagedDrift] = []
    for entry in scoped:
        pointer = entry.scope.removeprefix(_JSON_SCOPE)
        hashes = [compute_hash(canonical_json(item)) for item in _array_at(doc, pointer)]
        if entry.sha256 in hashes:
            continue
        recorded = {other.sha256 for other in scoped if other.scope == entry.scope}
        edited = pointer.startswith(_HOOKS_POINTER) and _has_stray_launcher(
            _array_at(doc, pointer), hashes, recorded
        )
        drift.append(ManagedDrift(entry, "edited" if edited else "missing"))
    return drift


def _array_at(doc: object, pointer: str) -> Sequence[Any]:
    """The array at ``pointer``, or ``()`` when a step is absent or of another shape."""
    node: Any = doc
    for key in pointer_keys(pointer):
        if not isinstance(node, dict) or key not in node:
            return ()
        node = node[key]
    return node if isinstance(node, list) else ()


def _has_stray_launcher(items: Sequence[Any], hashes: list[str], recorded: set[str]) -> bool:
    """Whether a launcher-only group carries a hash no entry recorded: our group, edited."""
    return any(
        isinstance(item, dict) and launcher_kind(item) == "suspect" and digest not in recorded
        for item, digest in zip(items, hashes, strict=True)
    )
