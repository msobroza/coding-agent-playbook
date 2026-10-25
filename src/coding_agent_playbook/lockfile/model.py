"""Lockfile dataclasses + hash helpers (SPEC §14.4).

The lockfile records the ``sha256`` content hash of every generated file plus
the engine version that produced them. ``playbook sync --check`` and
``playbook check`` use it to detect drift between canonical source and
rendered output.

Schema 2 (specs/prK-lifecycle-hooks.md §P P4, §B.6) adds provenance to every
entry: which kind of artifact produced the path, its id, its source package,
and the adapter that wrote it. Files that cannot carry a sentinel (copied
skill scripts and references) are owned through these entries alone, and the
leftover policy deletes stale skill output only through them (SPEC §4.2
step 9). Every new field has a default and is omitted from the TOML at that default, so v1
lockfiles load unchanged and an older engine reading a v2 file still finds
``path`` / ``sha256`` / ``bytes``.

Artifact digests (#281 ticket 03) follow the same rule: an entry's ``digest``
and the top-level ``[[artifacts]]`` table (:class:`ArtifactDigest`, one per
rule, prompt, skill and hook a sync dispatched) are omitted when empty, so the
schema stays 2 and older readers ignore them.

:func:`~coding_agent_playbook.lockfile.drift.drift_entries` is the one jinja2-free
definition of drift against these entries, shared by ``playbook check`` and the
hook runtime (specs/prK-hook-pack.md §E.1).
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal, get_args

if TYPE_CHECKING:
    import builtins
    from collections.abc import Mapping
    from pathlib import Path

ProvenanceKind = Literal["rule", "prompt", "skill", "hook", "composite", "runtime"]
"""Who produced a generated path. ``composite`` = a multi-source output
(``finalize`` results such as ``.claude/CLAUDE.md``, Claude Code's rules file and
``AGENTS.md``, or a path written by two different artifacts); ``hook`` = a
copied external-handler script; ``runtime`` = hook runtime files and managed
settings elements (§B.6)."""

PROVENANCE_KINDS: Final[tuple[str, ...]] = get_args(ProvenanceKind)

__all__ = [
    "PROVENANCE_KINDS",
    "ArtifactDigest",
    "LockEntry",
    "Lockfile",
    "LockfileFormatError",
    "Provenance",
    "ProvenanceKind",
    "compute_hash",
    "generated_paths",
    "merge_provenance",
]

# Always serialized, even at a falsy value: the v1 core every engine reads.
_REQUIRED_ENTRY_KEYS: Final[frozenset[str]] = frozenset({"path", "sha256", "bytes"})

# Marks a key with no default in :func:`_typed_key` (``None`` is not usable:
# no lockfile key defaults to it).
_MISSING: Final = object()


class LockfileFormatError(ValueError):
    """A lockfile that parses as TOML but not as a lockfile: a key is missing or
    has the wrong type (a hand edit, a bad merge resolution).

    The message names the offending key, its value and the expected type, so
    ``playbook sync --check`` can report it as one drift line instead of a
    traceback. A ``ValueError``, like ``tomllib.TOMLDecodeError``, so every
    "unreadable lockfile" handler catches both.

    Example::

        LockfileFormatError("entries[0].path: expected str, got int 3")
    """


def _typed_key(
    table: Mapping[str, Any], key: str, expected: type, *, where: str, default: object = _MISSING
) -> Any:
    """Return ``table[key]`` checked against ``expected`` (``bool`` is never an ``int``).

    A missing key returns ``default``, or raises :class:`LockfileFormatError`
    when the key is required; so does a value of the wrong type.
    """
    if key not in table:
        if default is _MISSING:
            raise LockfileFormatError(f"{where}{key}: missing; expected {expected.__name__}")
        return default
    value = table[key]
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        raise LockfileFormatError(
            f"{where}{key}: expected {expected.__name__}, got {type(value).__name__} {value!r}"
        )
    return value


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


def merge_provenance(previous: Provenance | None, new: Provenance) -> Provenance:
    """The provenance of one path once ``new`` is recorded for it after ``previous``.

    The single rule for a path two writers share (§P P4): the same provenance
    twice is kept; two different ones make it ``kind="composite"``, the adapter
    surviving only when both agree. ``ProvenanceRecorder`` applies it per
    resolved path, and the ``guard_config.json`` ``protected`` table per
    repo-mapped path, so both name a shared skill file the same way.

    Example::

        merge_provenance(Provenance(kind="skill", artifact_id="x", adapter="claude_code"),
                         Provenance(kind="skill", artifact_id="x", adapter="opencode")).kind
        # -> "composite"
    """
    if previous is None or previous == new:
        return new
    adapter = previous.adapter if previous.adapter == new.adapter else ""
    return Provenance(kind="composite", adapter=adapter)


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
    # The content digest of the artifact named by ``kind``/``artifact_id``
    # (``catalog.digest``); ``""`` for composite and runtime output and v1/v2 files.
    digest: str = ""

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
    def from_dict(cls, data: Mapping[str, Any], *, where: str = "") -> LockEntry:
        """Load one ``[[entries]]`` table; keys missing from v1 files default.

        ``where`` prefixes error messages (``"entries[3]."``). Raises
        :class:`LockfileFormatError` for a missing core key or a value of the
        wrong type.

        Example::

            LockEntry.from_dict({"path": "AGENTS.md", "sha256": "ab", "bytes": 2})
        """

        def text(key: str) -> str:
            return str(_typed_key(data, key, str, where=where, default=""))

        return cls(
            path=_typed_key(data, "path", str, where=where),
            sha256=_typed_key(data, "sha256", str, where=where),
            bytes=_typed_key(data, "bytes", int, where=where),
            kind=text("kind"),
            artifact_id=text("artifact_id"),
            source=text("source"),
            adapter=text("adapter"),
            scope=text("scope"),
            executable=_typed_key(data, "executable", bool, where=where, default=False),
            digest=text("digest"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize in field order, omitting every v2 field at its default so
        rule/prompt entries stay compact and v1-shaped entries are unchanged."""
        return {
            spec.name: getattr(self, spec.name)
            for spec in dataclasses.fields(self)
            if spec.name in _REQUIRED_ENTRY_KEYS or getattr(self, spec.name) != spec.default
        }

    @property
    def is_whole_file(self) -> bool:
        """True when the entry covers the whole file (``scope == ""``).

        A scoped ``json:<pointer>`` entry covers one managed element of a file
        shared with the user (§B.6), so that file is never an orphan to delete.
        """
        return not self.scope

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


@dataclass(frozen=True)
class ArtifactDigest:
    """One ``[[artifacts]]`` record: an artifact sync dispatched and its content digest.

    Recorded for every rule, prompt, skill and hook a sync rendered, including
    the always rules that reach only composite outputs such as ``AGENTS.md``,
    so the next sync can name what changed (#281 ticket 03). ``kind`` is a plain
    ``str``, like :attr:`LockEntry.kind`, so a newer engine's file still loads.

    Example::

        ArtifactDigest(kind="rule", artifact_id="python-typing", digest="5f3c...")
    """

    kind: str
    artifact_id: str
    digest: str

    @property
    def key(self) -> str:
        """``<kind>:<id>``, how the sync summary names the artifact.

        Example: ``ArtifactDigest("rule", "x", "ab").key`` -> ``"rule:x"``.
        """
        return f"{self.kind}:{self.artifact_id}"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, where: str = "") -> ArtifactDigest:
        """Load one ``[[artifacts]]`` table, raising :class:`LockfileFormatError` on a bad key.

        Example: ``ArtifactDigest.from_dict({"kind": "rule", "artifact_id": "x", "digest": "ab"})``.
        """
        return cls(
            kind=_typed_key(data, "kind", str, where=where),
            artifact_id=_typed_key(data, "artifact_id", str, where=where),
            digest=_typed_key(data, "digest", str, where=where),
        )

    def to_dict(self) -> dict[str, str]:
        """The TOML table, inverse of :meth:`from_dict`."""
        return {"kind": self.kind, "artifact_id": self.artifact_id, "digest": self.digest}


@dataclass
class Lockfile:
    """The whole ``.coding-agent-playbook.lock``: ownership ``entries`` plus artifact digests.

    ``artifacts`` is empty for a file written before digests existed; it is
    omitted from the TOML when empty, and older engines ignore the table.

    Example::

        Lockfile(2, "0.1.0", "2026-10-25T00:00:00Z", entries=[...], artifacts=[...])
    """

    schema_version: int
    engine_version: str
    rendered_at: str  # ISO-8601 UTC timestamp from when sync ran
    entries: list[LockEntry] = field(default_factory=list)
    artifacts: list[ArtifactDigest] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Lockfile:
        """Load a parsed lockfile, validating its shape.

        Raises :class:`LockfileFormatError` naming the offending key and value
        when a top-level key or an entry has the wrong type (e.g. ``entries =
        "oops"`` or ``path = 3``), never a bare ``TypeError``.

        Example::

            Lockfile.from_dict(tomllib.loads(path.read_text()))
        """
        raw_entries = _typed_key(data, "entries", list, where="", default=[])
        entries: list[LockEntry] = []
        for index, raw in enumerate(raw_entries):
            if not isinstance(raw, dict):
                raise LockfileFormatError(
                    f"entries[{index}]: expected a table, got {type(raw).__name__} {raw!r}"
                )
            entries.append(LockEntry.from_dict(raw, where=f"entries[{index}]."))
        return cls(
            schema_version=_typed_key(data, "schema_version", int, where=""),
            engine_version=_typed_key(data, "engine_version", str, where=""),
            rendered_at=_typed_key(data, "rendered_at", str, where=""),
            entries=entries,
            artifacts=_artifact_digests(data),
        )

    def to_dict(self) -> dict[str, Any]:
        """The TOML document; ``artifacts`` only when there are any (older files stay alike)."""
        doc: dict[str, Any] = {
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "rendered_at": self.rendered_at,
            "entries": [entry.to_dict() for entry in self.entries],
        }
        if self.artifacts:
            doc["artifacts"] = [record.to_dict() for record in self.artifacts]
        return doc

    def recorded_paths(self) -> frozenset[str]:
        """Every repo-relative path an entry records, scoped entries included.

        Example::

            Lockfile(1, "0", "", [LockEntry("AGENTS.md", "0" * 64, 1)]).recorded_paths()
            # frozenset({'AGENTS.md'})
        """
        return frozenset(entry.path for entry in self.entries)

    def find(self, repo_relative_path: str) -> LockEntry | None:
        for entry in self.entries:
            if entry.path == repo_relative_path:
                return entry
        return None


def _artifact_digests(data: Mapping[str, Any]) -> list[ArtifactDigest]:
    """The ``[[artifacts]]`` tables of a parsed lockfile; ``[]`` when the file has none."""
    raw_records = _typed_key(data, "artifacts", list, where="", default=[])
    records: list[ArtifactDigest] = []
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            raise LockfileFormatError(
                f"artifacts[{index}]: expected a table, got {type(raw).__name__} {raw!r}"
            )
        records.append(ArtifactDigest.from_dict(raw, where=f"artifacts[{index}]."))
    return records


def generated_paths(lockfile: Lockfile | None) -> frozenset[str]:
    """The paths the engine wrote, per ``lockfile``; empty before the first sync.

    The one home for "which repo files are engine output" (D79): ``playbook
    check`` and interactive ``playbook init`` both exclude these from the
    harness markers. Scoped entries count, since the engine may have created
    that shared file; the unused-adapter hint says such files were skipped.

    Example::

        generated_paths(None)  # frozenset()
    """
    return lockfile.recorded_paths() if lockfile is not None else frozenset()
