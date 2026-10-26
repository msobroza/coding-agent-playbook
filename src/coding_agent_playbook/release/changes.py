"""What changed between two release manifests: the digest diff the notes and the bump floor read.

Entries match on everything but the digest (``ManifestEntry.key``): an artifact
whose digest moved is *changed*, one only in the newer manifest is *added*, one
only in the older is *removed*. A moved or renamed file is a removal plus an
addition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.release.manifest import ManifestEntry, ReleaseManifest

__all__ = ["ArtifactChanges", "diff_entries", "graded_set_changed"]


@dataclass(frozen=True)
class ArtifactChanges:
    """The entries added, changed and removed between two manifests, each sorted.

    Example::

        >>> ArtifactChanges((), (), ()).is_empty
        True
    """

    added: tuple[ManifestEntry, ...]
    changed: tuple[ManifestEntry, ...]
    removed: tuple[ManifestEntry, ...]

    @property
    def is_empty(self) -> bool:
        """True when nothing was added, changed or removed."""
        return not (self.added or self.changed or self.removed)


def diff_entries(
    previous: Iterable[ManifestEntry], current: Iterable[ManifestEntry]
) -> ArtifactChanges:
    """The :class:`ArtifactChanges` from ``previous`` to ``current``; ``changed`` holds the new entries.

    Example::

        >>> diff_entries([], []).is_empty
        True
    """
    before = {entry.key: entry for entry in previous}
    after = {entry.key: entry for entry in current}
    return ArtifactChanges(
        added=tuple(sorted(after[key] for key in after.keys() - before.keys())),
        changed=tuple(
            sorted(
                entry
                for key, entry in after.items()
                if key in before and before[key].digest != entry.digest
            )
        ),
        removed=tuple(sorted(before[key] for key in before.keys() - after.keys())),
    )


def graded_set_changed(previous: ReleaseManifest | None, current: ReleaseManifest) -> bool:
    """Whether the graded set differs from the previous release's; always true for the first.

    A graded set change raises the release to at least a minor (ADR 0012).

    Example::

        >>> graded_set_changed(None, ReleaseManifest("9.9.9", "f00d", (), ()))
        True
    """
    if previous is None:
        return True
    return not diff_entries(previous.graded, current.graded).is_empty
