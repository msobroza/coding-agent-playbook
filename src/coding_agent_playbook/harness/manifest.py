"""The ``.playbook/manifest.toml`` round-trip sidecar (Track H1, §C).

The harness format cannot represent canonical fields like rule ``scope``/``globs``
or prompt ``includes_rules``. The adapter records them here, keyed by each
artifact's harness-relative path, so the importer can rebuild canonical artifacts
losslessly. Without this sidecar an importer falls back to best-effort structural
inference (and surfaces the lossiness).

TOML I/O mirrors the project's existing conventions: read with stdlib
:mod:`tomllib`; write with a small hand-rolled serializer (the engine vendors no
TOML *writer* — see ``sources/filesystem.py``). The serializer emits one
``[[artifact]]`` array-of-tables entry per artifact, with nested
``[[artifact.script]]`` entries for a skill's (or hook's) scripts and inline
tables for open-dict fields (``applies_if``, ``extra_frontmatter``,
``hook_frontmatter``).

Kind ``"hook"`` (specs/prK-lifecycle-hooks.md §C.6) needs no schema bump: an
older engine ignores the unknown ``hook_frontmatter`` key and warns-and-skips
the unknown kind.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from coding_agent_playbook import _toml

if TYPE_CHECKING:
    from pathlib import Path

#: Sidecar directory + file names (dotfile so harness clients skip it).
SIDECAR_DIRNAME = ".playbook"
MANIFEST_FILENAME = "manifest.toml"

#: Current manifest schema version.
SCHEMA_VERSION = 1

ArtifactKind = Literal["rule", "prompt", "skill", "eval_task", "hook"]


@dataclass
class ScriptEntry:
    """One script's path + git-style executable bit (decision #1)."""

    path: str
    executable: bool


@dataclass
class ManifestEntry:
    """One artifact's full canonical reconstruction payload, keyed by its
    harness-relative ``path``.

    The sidecar is the **lossless source of truth**: it records every frontmatter
    field the harness format cannot represent (e.g. rule ``name``/``scope``,
    prompt ``includes_rules``) *and* the original, un-rendered canonical source
    ``body`` plus ``is_templated`` for every kind. The harness leaf files are
    the client-facing presentation (which may rewrite/inline content — a prompt's
    ``includes_rules`` get inlined into its ``SKILL.md`` body), so the lossless
    importer reconstructs each artifact from THIS entry via ``from_dict``, never
    from the possibly-rendered on-disk file.

    Only the fields relevant to ``kind`` are populated; the rest keep their
    defaults so equality round-trips through :func:`write_manifest` /
    :func:`read_manifest`.
    """

    kind: ArtifactKind
    path: str
    id: str
    # Canonical reconstruction payload (all kinds): the un-rendered source body
    # and templated flag, so reconstruction never depends on the rendered leaf.
    name: str | None = None
    body: str | None = None
    is_templated: bool | None = None
    # Rule-only.
    scope: str | None = None
    priority: int | None = None
    globs: list[str] = field(default_factory=list)
    applies_if: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    version: int | None = None
    # Prompt-only.
    slash: str | None = None
    input_variables: list[dict[str, Any]] = field(default_factory=list)
    includes_rules: list[str] = field(default_factory=list)
    eval_tasks: list[str] = field(default_factory=list)
    # Skill-only.
    extra_frontmatter: dict[str, Any] = field(default_factory=dict)
    # Skill and hook.
    scripts: list[ScriptEntry] = field(default_factory=list)
    # Hook-only: the canonical HOOK.md frontmatter (``HookFrontmatter.to_mapping``).
    hook_frontmatter: dict[str, Any] = field(default_factory=dict)


@dataclass
class Manifest:
    """A parsed manifest: the schema version plus every recorded entry."""

    schema: int
    entries: list[ManifestEntry] = field(default_factory=list)

    def index_by_path(self) -> dict[str, ManifestEntry]:
        """Return a ``{harness_relative_path: entry}`` index for the importer."""
        return {entry.path: entry for entry in self.entries}


# --- field selection per kind ----------------------------------------------

# Scalar/list fields emitted for each kind, in stable order. ``applies_if`` and
# ``extra_frontmatter`` (dicts) and ``scripts`` (sub-tables) are handled apart.
#
# ``name``, ``body`` and ``is_templated`` are part of the canonical
# reconstruction payload for every artifact kind: the sidecar stores the
# un-rendered source body (the harness leaf may inline/rewrite it) so the
# lossless importer never reconstructs from the rendered file.
_KIND_FIELDS: dict[str, tuple[str, ...]] = {
    "rule": ("name", "body", "is_templated", "scope", "priority", "globs", "tags", "version"),
    "prompt": (
        "name",
        "body",
        "is_templated",
        "slash",
        "version",
        "input_variables",
        "includes_rules",
        "eval_tasks",
    ),
    "skill": ("name", "body"),
    "eval_task": (),
    "hook": ("name", "body", "is_templated"),
}


def _entry_to_table(entry: ManifestEntry) -> dict[str, Any]:
    """Project a :class:`ManifestEntry` to the ordered dict serialized as TOML."""
    table: dict[str, Any] = {"kind": entry.kind, "path": entry.path, "id": entry.id}
    for name in _KIND_FIELDS[entry.kind]:
        table[name] = getattr(entry, name)
    if entry.kind in ("rule", "prompt"):
        table["applies_if"] = entry.applies_if
    if entry.kind == "skill":
        table["extra_frontmatter"] = entry.extra_frontmatter
    if entry.kind == "hook":
        table["hook_frontmatter"] = entry.hook_frontmatter
    return table


def _entry_from_table(table: dict[str, Any]) -> ManifestEntry:
    """Inverse of :func:`_entry_to_table`. Absent keys fall back to defaults."""
    scripts = [
        ScriptEntry(path=script["path"], executable=bool(script["executable"]))
        for script in table.get("script", [])
    ]
    return ManifestEntry(
        kind=table["kind"],
        path=table["path"],
        id=table["id"],
        name=table.get("name"),
        body=table.get("body"),
        is_templated=table.get("is_templated"),
        scope=table.get("scope"),
        priority=table.get("priority"),
        globs=list(table.get("globs", [])),
        applies_if=dict(table.get("applies_if", {})),
        tags=list(table.get("tags", [])),
        version=table.get("version"),
        slash=table.get("slash"),
        input_variables=list(table.get("input_variables", [])),
        includes_rules=list(table.get("includes_rules", [])),
        eval_tasks=list(table.get("eval_tasks", [])),
        extra_frontmatter=dict(table.get("extra_frontmatter", {})),
        scripts=scripts,
        hook_frontmatter=dict(table.get("hook_frontmatter", {})),
    )


# --- TOML serialization ----------------------------------------------------


def _format_scalar(value: Any) -> str:
    """Render a scalar/collection as a TOML value (inline forms only).

    Thin wrapper over :func:`coding_agent_playbook._toml.format_scalar` with
    inline tables enabled: bool before int (``isinstance(True, int)``),
    control-char-safe basic strings, inline arrays, and inline tables for dicts.
    Preserves the historical ``manifest TOML …`` ``TypeError`` wording.
    """
    return _toml.format_scalar(value, allow_inline_table=True, type_error_prefix="manifest TOML")


def _serialize(entries: list[ManifestEntry]) -> str:
    """Serialize the whole manifest to a TOML document string."""
    lines: list[str] = [f"schema = {SCHEMA_VERSION}"]
    for entry in entries:
        lines.append("")
        lines.append("[[artifact]]")
        for key, value in _entry_to_table(entry).items():
            lines.append(f"{_toml.format_key(key)} = {_format_scalar(value)}")
        for script in entry.scripts:
            lines.append("")
            lines.append("[[artifact.script]]")
            lines.append(f"path = {_toml.format_string(script.path)}")
            lines.append(f"executable = {'true' if script.executable else 'false'}")
    return "\n".join(lines) + "\n"


# --- public API ------------------------------------------------------------


def write_manifest(root: Path, entries: list[ManifestEntry]) -> Path:
    """Write ``root/.playbook/manifest.toml`` (schema 1). Return the file path."""
    sidecar = root / SIDECAR_DIRNAME
    sidecar.mkdir(parents=True, exist_ok=True)
    target = sidecar / MANIFEST_FILENAME
    target.write_text(_serialize(entries), encoding="utf-8")
    return target


def read_manifest(root: Path) -> Manifest | None:
    """Read ``root/.playbook/manifest.toml``. Return ``None`` when absent."""
    target = root / SIDECAR_DIRNAME / MANIFEST_FILENAME
    if not target.is_file():
        return None
    with target.open("rb") as handle:
        data = tomllib.load(handle)
    entries = [_entry_from_table(table) for table in data.get("artifact", [])]
    return Manifest(schema=int(data.get("schema", SCHEMA_VERSION)), entries=entries)
