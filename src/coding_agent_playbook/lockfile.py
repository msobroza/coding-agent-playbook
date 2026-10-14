"""Lockfile dataclass + hash helpers (SPEC §14.4).

The lockfile records ``sha256`` content hashes of every generated file plus
the engine version that produced them. ``playbook sync --check`` uses this to
detect drift between canonical source and rendered output.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def compute_hash(content: bytes) -> str:
    """sha256 hex digest of ``content``. Stable across platforms (binary mode)."""
    return hashlib.sha256(content).hexdigest()


@dataclass
class LockEntry:
    path: str  # relative to repo root, posix forward slashes
    sha256: str
    bytes: int

    def matches_file(self, path: Path) -> bool:
        """True when ``path``'s bytes still hash to this entry (unchanged engine output).

        The single "pristine" test of the leftover policy (SPEC §4.2 step 9): an
        unreadable or missing file is never pristine, so it is never deleted.

        Example::

            >>> LockEntry("a.md", compute_hash(b"x"), 1).matches_file(Path("/no/such"))  # doctest: +SKIP
            False
        """
        try:
            return compute_hash(path.read_bytes()) == self.sha256
        except OSError:
            return False


@dataclass
class Lockfile:
    schema_version: int
    engine_version: str
    rendered_at: str  # ISO-8601 UTC timestamp from when sync ran
    entries: list[LockEntry] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Lockfile:
        return cls(
            schema_version=data["schema_version"],
            engine_version=data["engine_version"],
            rendered_at=data["rendered_at"],
            entries=[
                LockEntry(
                    path=entry["path"],
                    sha256=entry["sha256"],
                    bytes=entry["bytes"],
                )
                for entry in data.get("entries", [])
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "rendered_at": self.rendered_at,
            "entries": [
                {"path": entry.path, "sha256": entry.sha256, "bytes": entry.bytes}
                for entry in self.entries
            ],
        }

    def find(self, repo_relative_path: str) -> LockEntry | None:
        for entry in self.entries:
            if entry.path == repo_relative_path:
                return entry
        return None
