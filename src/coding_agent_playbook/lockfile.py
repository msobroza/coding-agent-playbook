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

:func:`drift_entries` (``_lock_drift``, re-exported here) is the one jinja2-free
definition of drift against these entries, shared by ``playbook check`` and the
hook runtime (specs/prK-hook-pack.md §E.1).
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal, get_args

from coding_agent_playbook._lock_drift import (
    DriftItem,
    DriftKind,
    EditedProbe,
    ScopedParser,
    ScopedUnreadable,
    drift_entries,
    managed_drift,
    parse_json_document,
)

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
    "DriftItem",
    "DriftKind",
    "EditedProbe",
    "LockEntry",
    "Lockfile",
    "LockfileFormatError",
    "Provenance",
    "ProvenanceKind",
    "ScopedParser",
    "ScopedUnreadable",
    "compute_hash",
    "drift_entries",
    "managed_drift",
    "parse_json_document",
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


@dataclass
class Lockfile:
    schema_version: int
    engine_version: str
    rendered_at: str  # ISO-8601 UTC timestamp from when sync ran
    entries: list[LockEntry] = field(default_factory=list)

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
