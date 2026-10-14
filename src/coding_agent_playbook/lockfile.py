"""Lockfile dataclass + hash helpers (SPEC §14.4).

The lockfile records ``sha256`` content hashes of every generated file plus
the engine version that produced them. ``playbook check`` uses it to report
drift, and ``playbook sync`` uses the previous one as the ownership record its
stale-output sweep deletes from (:mod:`coding_agent_playbook.stale_outputs`).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

#: Schema ``playbook sync`` writes. 2: entries list only files the engine itself
#: generated (repo-relative logical paths, never a symlink or a file merely found
#: inside a copied skill directory), so the stale-output sweep may delete them.
LOCKFILE_SCHEMA_VERSION = 2

#: Oldest schema the stale-output sweep trusts for deletion. Schema 1 lockfiles
#: (written before SPEC v0.15) could also list user files found inside a native
#: skill's copied ``scripts/`` / ``references/`` dir, and the targets of
#: symlinks, so their stale entries are reported, never deleted.
FIRST_OWNERSHIP_SCHEMA_VERSION = 2


def compute_hash(content: bytes) -> str:
    """sha256 hex digest of ``content``. Stable across platforms (binary mode)."""
    return hashlib.sha256(content).hexdigest()


@dataclass
class LockEntry:
    path: str  # relative to repo root, posix forward slashes
    sha256: str
    bytes: int


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
