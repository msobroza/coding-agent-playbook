"""The release manifest: ``catalog/releases/<version>/manifest.toml`` (#281 ticket 10).

One manifest per release records, in the release commit itself:

- ``base``: the ``origin/main`` commit the release was prepared from, so tagging
  can check that nothing merged in between;
- ``[[graded]]``: the graded set (``release.graded_set``), each entry's kind, id,
  repo-relative path and digest, so ``freeze vX`` can rebuild an edition from the
  tag without parsing an old tree with today's loader;
- ``[[artifacts]]``: every shipped rule, prompt, skill and hook with its layer and
  digest, so the next release's notes can name what changed
  (``release.changes``).

Digests are ``catalog.digest.artifact_digest``. :func:`render_manifest` and
:func:`parse_manifest` round-trip exactly.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.toml_writer import dump_toml

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "MANIFEST_FILENAME",
    "MANIFEST_SCHEMA_VERSION",
    "NOTES_FILENAME",
    "RELEASES_DIRNAME",
    "ManifestEntry",
    "ManifestError",
    "ReleaseManifest",
    "parse_manifest",
    "read_manifest",
    "release_dir",
    "render_manifest",
]

#: ``catalog/<this>/<version>/``: outside every layer root, so no layer walker sees it.
RELEASES_DIRNAME: Final = "releases"
MANIFEST_FILENAME: Final = "manifest.toml"
NOTES_FILENAME: Final = "notes.md"
MANIFEST_SCHEMA_VERSION: Final = 1

_HEADER: Final = "# Written by `scripts/release.py prepare`. Never edit it by hand.\n\n"
_ENTRY_KEYS: Final = ("layer", "kind", "id", "path", "digest")
_TOP_KEYS: Final = frozenset({"schema_version", "version", "base", "graded", "artifacts"})


class ManifestError(ValueError):
    """A manifest file that does not have the shape :func:`render_manifest` writes."""


@dataclass(frozen=True, order=True)
class ManifestEntry:
    """One artifact as a release shipped it.

    ``layer`` is the artifact's ``source_package``; ``path`` is relative to the
    repository root (``catalog/core/prompts/review.md.j2``; a skill or hook names
    its directory).

    Example::

        >>> ManifestEntry("coding_agent_playbook", "prompt", "review", "catalog/core/prompts/review.md.j2", "ab12").key
        ('coding_agent_playbook', 'prompt', 'review', 'catalog/core/prompts/review.md.j2')
    """

    layer: str
    kind: str
    id: str
    path: str
    digest: str

    @property
    def key(self) -> tuple[str, str, str, str]:
        """What two manifests match entries on: everything but the digest."""
        return (self.layer, self.kind, self.id, self.path)


@dataclass(frozen=True)
class ReleaseManifest:
    """What one release recorded: its version, base commit, graded set and artifacts.

    Example::

        >>> ReleaseManifest("9.9.9", "f00d", (), ()).version
        '9.9.9'
    """

    version: str
    base: str
    graded: tuple[ManifestEntry, ...]
    artifacts: tuple[ManifestEntry, ...]


def release_dir(catalog_dir: Path, version: str) -> Path:
    """``<catalog>/releases/<version>``, where one release's manifest and notes live.

    Example::

        >>> release_dir(Path("catalog"), "9.9.9").as_posix()
        'catalog/releases/9.9.9'
    """
    return catalog_dir / RELEASES_DIRNAME / version


def render_manifest(manifest: ReleaseManifest) -> str:
    """``manifest`` as TOML text, entries sorted, behind a do-not-edit comment.

    Example::

        >>> render_manifest(ReleaseManifest("9.9.9", "f00d", (), ())).splitlines()[2]
        'schema_version = 1'
    """
    data: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "version": manifest.version,
        "base": manifest.base,
        "graded": [_entry_table(entry) for entry in sorted(manifest.graded)],
        "artifacts": [_entry_table(entry) for entry in sorted(manifest.artifacts)],
    }
    return _HEADER + dump_toml(data)


def _entry_table(entry: ManifestEntry) -> dict[str, str]:
    return {key: getattr(entry, key) for key in _ENTRY_KEYS}


def read_manifest(path: Path) -> ReleaseManifest:
    """Parse the manifest file at ``path``; a :class:`ManifestError` names the path on a bad file."""
    try:
        return parse_manifest(path.read_text(encoding="utf-8"))
    except (OSError, ManifestError) as exc:
        raise ManifestError(f"{path}: {exc}") from exc


def parse_manifest(text: str) -> ReleaseManifest:
    """The :class:`ReleaseManifest` that ``text`` (as :func:`render_manifest` writes it) holds.

    Raises :class:`ManifestError` naming the offending key or value.

    Example::

        >>> parse_manifest(render_manifest(ReleaseManifest("9.9.9", "f00d", (), ()))).base
        'f00d'
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"malformed TOML: {exc}") from exc
    unknown = sorted(set(data) - _TOP_KEYS)
    if unknown:
        raise ManifestError(f"unknown keys {unknown}; expected {sorted(_TOP_KEYS)}")
    if data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(
            f"schema_version {data.get('schema_version')!r}; expected {MANIFEST_SCHEMA_VERSION}"
        )
    return ReleaseManifest(
        version=_string(data, "version"),
        base=_string(data, "base"),
        graded=_entries(data, "graded"),
        artifacts=_entries(data, "artifacts"),
    )


def _string(table: dict[str, Any], key: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{key} = {value!r}; expected a non-empty string")
    return value


def _entries(data: dict[str, Any], key: str) -> tuple[ManifestEntry, ...]:
    tables = data.get(key, [])
    if not isinstance(tables, list):
        raise ManifestError(f"{key} = {tables!r}; expected an array of tables")
    return tuple(_entry(table, key) for table in tables)


def _entry(table: object, key: str) -> ManifestEntry:
    if not isinstance(table, dict) or set(table) != set(_ENTRY_KEYS):
        raise ManifestError(f"[[{key}]] entry {table!r}; expected exactly the keys {_ENTRY_KEYS}")
    return ManifestEntry(*(_string(table, name) for name in _ENTRY_KEYS))
