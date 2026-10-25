"""The one line ``playbook sync`` ends with: which artifacts' digests moved (#281 ticket 03).

Generated output is often gitignored, so a consumer cannot diff it after an
upgrade. Sync compares the ``[[artifacts]]`` digests of the lockfile it just
wrote with the previous one and names every artifact that is new, changed or
gone, as ``<kind>:<id>``. A repo without a previous lockfile, or whose lockfile
predates digests, reports every artifact as new.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook.lockfile.model import Lockfile

#: The line printed when no digest moved.
NO_GUIDANCE_CHANGED = "Guidance: no guidance changed"


@dataclass(frozen=True)
class GuidanceChanges:
    """The artifact keys (``<kind>:<id>``) whose digest moved between two syncs, sorted.

    Example::

        GuidanceChanges(new=("rule:a",), changed=(), removed=()).line()
        # 'Guidance changed: new rule:a'
    """

    new: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()

    def line(self) -> str:
        """The summary line: each non-empty group with its keys, else :data:`NO_GUIDANCE_CHANGED`."""
        groups = [("new", self.new), ("changed", self.changed), ("removed", self.removed)]
        parts = [f"{label} {', '.join(keys)}" for label, keys in groups if keys]
        return f"Guidance changed: {'; '.join(parts)}" if parts else NO_GUIDANCE_CHANGED


def guidance_changes(previous: Lockfile | None, current: Lockfile) -> GuidanceChanges:
    """Compare the artifact digests ``current`` records with those of ``previous``.

    ``previous`` is ``None`` on a first sync (or an unreadable lockfile); its
    empty ``artifacts`` (a lockfile from before digests) reads the same way.

    Example::

        guidance_changes(None, lockfile).new  # every artifact the sync dispatched
    """
    before = {} if previous is None else {r.key: r.digest for r in previous.artifacts}
    after = {record.key: record.digest for record in current.artifacts}
    return GuidanceChanges(
        new=tuple(sorted(key for key in after if key not in before)),
        changed=tuple(sorted(key for key in after if key in before and before[key] != after[key])),
        removed=tuple(sorted(key for key in before if key not in after)),
    )
