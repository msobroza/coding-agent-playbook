"""Object model for a parsed Agent Harness tree (Track H1).

These frozen dataclasses are the in-memory representation produced by
:func:`coding_agent_playbook.agent_harness.parser.parse_harness`. They mirror the
artifact catalog in ``specs/prH-agent-harness.md`` §A:

- :class:`Harness` — the root (``HARNESS.md`` + every top-level branch).
- :class:`HarnessDirectory` — a grouping directory (routing file + children).
- :class:`SkillLeaf` — a ``SKILL.md``-typed leaf with ``scripts/`` + ``references/``.
- :class:`ScriptFile` — one file under a skill's ``scripts/`` (with its exec bit).
- :class:`ContentFile` — a markdown content file (optional ``description``).
- :class:`RawAsset` — a non-markdown passthrough file (tracked by ``sha256``).
- :class:`LeafMarker` — a ``.harnessleaf``-terminated opaque directory.

Collections are stored as tuples so the whole tree is hashable and immutable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class NotAHarnessError(Exception):
    """Raised when a directory is not a valid harness root (no ``HARNESS.md``)."""


@dataclass(frozen=True)
class ScriptFile:
    """One file enumerated under a skill's ``scripts/`` directory.

    ``executable`` records git's single permission bit (whether *any* execute
    bit is set on disk), not a full octal mode — see decision #1 in the spec.
    """

    path: Path
    executable: bool


@dataclass(frozen=True)
class ContentFile:
    """A markdown content file (``description`` drives Discovery relevance)."""

    filename: str
    description: str | None
    path: Path
    is_markdown: bool


@dataclass(frozen=True)
class RawAsset:
    """A non-markdown passthrough file, tracked by content checksum."""

    path: Path
    sha256: str


@dataclass(frozen=True)
class LeafMarker:
    """A ``.harnessleaf``-terminated directory: an opaque unit, never recursed."""

    path: Path


@dataclass(frozen=True)
class SkillLeaf:
    """A skill leaf: ``SKILL.md`` (``name``/``description`` + body) plus side files."""

    name: str
    description: str
    body: str
    path: Path
    scripts: tuple[ScriptFile, ...] = field(default_factory=tuple)
    references: tuple[ContentFile, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HarnessDirectory:
    """A grouping directory: its routing file plus classified children.

    ``routing_file_name`` is derived from the **top-level** ancestor segment and
    is identical for every directory in the same branch (propagation rule).
    ``children`` are nested grouping dirs, ``leaves`` are typed/opaque leaves,
    ``content`` are this dir's own content/raw files (excluding the routing file).
    """

    name: str
    routing_file_name: str
    description: str | None
    path: Path
    children: tuple[HarnessDirectory, ...] = field(default_factory=tuple)
    leaves: tuple[SkillLeaf | LeafMarker, ...] = field(default_factory=tuple)
    content: tuple[ContentFile | RawAsset, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Harness:
    """The parsed harness root: ``HARNESS.md`` metadata plus every branch."""

    name: str
    description: str
    body: str
    path: Path
    directories: tuple[HarnessDirectory, ...] = field(default_factory=tuple)
