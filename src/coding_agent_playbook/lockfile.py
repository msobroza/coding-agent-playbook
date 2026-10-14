"""Lockfile dataclasses + hash helpers (SPEC §14.4).

The lockfile records the ``sha256`` content hash of every generated file plus
the engine version that produced them. ``playbook sync --check`` and
``playbook check`` use it to detect drift between canonical source and
rendered output.

Schema 2 (specs/prK-lifecycle-hooks.md §P P4, §B.6) adds provenance to every
entry: which kind of artifact produced the path, its id, its source package,
and the adapter that wrote it. Files that cannot carry a sentinel
(``SKILL.md``, copied scripts) are owned through these entries alone. Every
new field has a default and is omitted from the TOML at that default, so v1
lockfiles load unchanged and an older engine reading a v2 file still finds
``path`` / ``sha256`` / ``bytes``.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal, get_args

if TYPE_CHECKING:
    import builtins

ProvenanceKind = Literal["rule", "prompt", "skill", "hook", "composite", "runtime"]
"""Who produced a generated path. ``composite`` = a multi-source output
(``finalize`` results such as ``CLAUDE.md`` / ``AGENTS.md``, or a path written
by two different artifacts); ``hook`` = a copied external-handler script;
``runtime`` = hook runtime files and managed settings elements (§B.6)."""

PROVENANCE_KINDS: Final[tuple[str, ...]] = get_args(ProvenanceKind)

# Always serialized, even at a falsy value: the v1 core every engine reads.
_REQUIRED_ENTRY_KEYS: Final[frozenset[str]] = frozenset({"path", "sha256", "bytes"})


def compute_hash(content: bytes) -> str:
    """sha256 hex digest of ``content``. Stable across platforms (binary mode)."""
    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class Provenance:
    """Where one generated path came from, recorded while ``playbook sync``
    dispatches artifacts to adapters (the adapter return type is unchanged).

    ``artifact_id`` and ``source`` stay ``""`` for composite and runtime
    outputs; ``adapter`` is ``""`` for sync-level writes.

    Example::

        Provenance(kind="rule", artifact_id="python-typing",
                   source="coding_agent_playbook", adapter="continue")
    """

    kind: ProvenanceKind
    artifact_id: str = ""
    source: str = ""
    adapter: str = ""

    def __post_init__(self) -> None:
        if self.kind not in PROVENANCE_KINDS:
            raise ValueError(
                f"unknown provenance kind {self.kind!r}; expected one of {PROVENANCE_KINDS}"
            )


@dataclass
class LockEntry:
    """One ownership record in ``.coding-agent-playbook.lock``.

    ``path`` is repo-relative with forward slashes. With ``scope == ""`` the
    hash and size cover the whole file; a ``json:<pointer>`` scope covers one
    managed element of the JSON array at that pointer (§C.1.4). ``kind`` is
    ``""`` for entries loaded from a v1 lockfile (unknown provenance) and is
    kept a plain ``str`` so a lockfile from a newer engine still loads.
    ``scope`` and ``executable`` are populated by the hook tracks only.

    Example::

        LockEntry(path="AGENTS.md", sha256=compute_hash(b"..."), bytes=3,
                  kind="composite", adapter="agents_md")
    """

    path: str
    sha256: str
    bytes: int
    kind: str = ""
    artifact_id: str = ""
    source: str = ""
    adapter: str = ""
    scope: str = ""
    executable: bool = False

    # ``builtins.bytes``: inside this class body ``bytes`` names the field above.
    @classmethod
    def from_provenance(
        cls, path: str, content: builtins.bytes, provenance: Provenance
    ) -> LockEntry:
        """Whole-file entry for ``content`` at ``path``, stamped with ``provenance``.

        Example::

            LockEntry.from_provenance("AGENTS.md", b"...", Provenance(kind="composite"))
        """
        return cls(
            path=path,
            sha256=compute_hash(content),
            bytes=len(content),
            kind=provenance.kind,
            artifact_id=provenance.artifact_id,
            source=provenance.source,
            adapter=provenance.adapter,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LockEntry:
        """Load one ``[[entries]]`` table; keys missing from v1 files default."""
        return cls(
            path=data["path"],
            sha256=data["sha256"],
            bytes=data["bytes"],
            kind=str(data.get("kind", "")),
            artifact_id=str(data.get("artifact_id", "")),
            source=str(data.get("source", "")),
            adapter=str(data.get("adapter", "")),
            scope=str(data.get("scope", "")),
            executable=bool(data.get("executable", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize in field order, omitting every v2 field at its default so
        rule/prompt entries stay compact and v1-shaped entries are unchanged."""
        return {
            spec.name: getattr(self, spec.name)
            for spec in dataclasses.fields(self)
            if spec.name in _REQUIRED_ENTRY_KEYS or getattr(self, spec.name) != spec.default
        }


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
            entries=[LockEntry.from_dict(entry) for entry in data.get("entries", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "rendered_at": self.rendered_at,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def find(self, repo_relative_path: str) -> LockEntry | None:
        for entry in self.entries:
            if entry.path == repo_relative_path:
                return entry
        return None
