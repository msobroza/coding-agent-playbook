"""An edition's digests file: ``catalog/editions/<tag>/digests.toml`` (#281 ticket 09).

An **edition** (CONTEXT.md) is a frozen copy of the graded set as the release
``<tag>`` shipped it. Its files sit under ``catalog/editions/<tag>/core/``, at
their path relative to ``catalog/`` (``core/prompts/review.md.j2``), next to one
small file that says what the copy is and what the pins froze::

    # Written by `scripts/release.py freeze`. Never edit it by hand.
    schema_version = 1
    tag = "v0.1.0"                 # the release the copy comes from
    commit = "<sha>"               # the commit that tag names

    [[artifacts]]                  # the id-to-path map, one entry per frozen file
    kind = "prompt"                # "prompt", "rule" or "notice"
    id = "review"
    path = "core/prompts/review.md.j2"   # relative to the edition directory
    sha256 = "<sha256 of the file's bytes>"

    [[pins]]                       # one entry per eval sample pinned to the edition
    sample = "review/spot-the-bug"
    rendered_prompt_digest = "<sha256 of the prompt text the sample renders>"
    sample_digest = "<evals.sample_digest.sample_digest of the sample>"

A ``notice`` is a license or attribution file the frozen rule text needs (the
vendored sources' ``references/LICENSE.<source>`` and ``core/ATTRIBUTIONS.md``,
``release.edition_notices``); its id is its path. It is copied and checked like
any frozen file, but the edition loader reads no notice.

The sample digest covers ``sample.toml`` as pinned: it is taken after
``edition = "<tag>"`` is written into it. The edition directory holds only the
digests file and the listed files; the README saying the directories are
generated sits beside them, at ``catalog/editions/README.md``.

``scripts/release.py freeze`` writes it (``release.edition_freeze``,
``evals.edition_pins``); the edition loader (``release.edition``), the offline
edition checks (``evals.edition_checks``) and the CI tag check
(``release.edition_freeze.edition_tag_problems``) read it.
:func:`render_edition_digests` and :func:`parse_edition_digests` round-trip exactly.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

from coding_agent_playbook.toml_writer import dump_toml

__all__ = [
    "DIGESTS_FILENAME",
    "EDITIONS_DIRNAME",
    "EDITION_KINDS",
    "NOTICE_KIND",
    "EditionArtifact",
    "EditionDigests",
    "EditionDigestsError",
    "PinDigests",
    "edition_dir",
    "parse_edition_digests",
    "read_edition_digests",
    "render_edition_digests",
]

#: ``catalog/<this>/<tag>/``: outside every layer root, so no layer walker sees it.
EDITIONS_DIRNAME: Final = "editions"
DIGESTS_FILENAME: Final = "digests.toml"
#: Editions copy the graded set only: prompts and the rules they include.
EDITION_KINDS: Final = ("prompt", "rule")
#: A license or attribution file the frozen text needs; its id is its edition path.
NOTICE_KIND: Final = "notice"
_ARTIFACT_KINDS: Final = (*EDITION_KINDS, NOTICE_KIND)
#: Every frozen file lives under the edition's copy of the engine layer.
_CORE_PREFIX: Final = "core"
_SCHEMA_VERSION: Final = 1

_HEADER: Final = "# Written by `scripts/release.py freeze`. Never edit it by hand.\n\n"
_TOP_KEYS: Final = frozenset({"schema_version", "tag", "commit", "artifacts", "pins"})
_ARTIFACT_KEYS: Final = ("kind", "id", "path", "sha256")
_PIN_KEYS: Final = ("sample", "rendered_prompt_digest", "sample_digest")


class EditionDigestsError(ValueError):
    """A digests file that does not have the shape :func:`render_edition_digests` writes."""


@dataclass(frozen=True, order=True)
class EditionArtifact:
    """One frozen file: its kind, id, path relative to the edition dir and byte sha256.

    Example::

        >>> EditionArtifact("prompt", "review", "core/prompts/review.md.j2", "aa").kind
        'prompt'
    """

    kind: str
    id: str
    path: str
    sha256: str


@dataclass(frozen=True, order=True)
class PinDigests:
    """What one pin froze: the sample id, its rendered prompt's digest and its sample digest.

    Example::

        >>> PinDigests("review/spot-the-bug", "cc", "dd").sample
        'review/spot-the-bug'
    """

    sample: str
    rendered_prompt_digest: str
    sample_digest: str


@dataclass(frozen=True)
class EditionDigests:
    """The parsed digests file of one edition.

    Example::

        >>> EditionDigests("v9.9.9", "f00d", (), ()).tag
        'v9.9.9'
    """

    tag: str
    commit: str
    artifacts: tuple[EditionArtifact, ...]
    pins: tuple[PinDigests, ...]

    def pin(self, sample_id: str) -> PinDigests | None:
        """The pin of ``sample_id``, or ``None`` when the edition does not list it."""
        return next((pin for pin in self.pins if pin.sample == sample_id), None)


def edition_dir(catalog_dir: Path, tag: str) -> Path:
    """``<catalog>/editions/<tag>``, where one edition's files and digests file live.

    Example::

        >>> edition_dir(Path("catalog"), "v9.9.9").as_posix()
        'catalog/editions/v9.9.9'
    """
    return catalog_dir / EDITIONS_DIRNAME / tag


def render_edition_digests(digests: EditionDigests) -> str:
    """``digests`` as TOML text, entries sorted, behind a do-not-edit comment.

    Example::

        >>> render_edition_digests(EditionDigests("v9.9.9", "f00d", (), ())).splitlines()[2]
        'schema_version = 1'
    """
    data: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "tag": digests.tag,
        "commit": digests.commit,
        "artifacts": [_table(entry, _ARTIFACT_KEYS) for entry in sorted(digests.artifacts)],
        "pins": [_table(pin, _PIN_KEYS) for pin in sorted(digests.pins)],
    }
    return _HEADER + dump_toml(data)


def _table(entry: object, keys: tuple[str, ...]) -> dict[str, str]:
    return {key: getattr(entry, key) for key in keys}


def read_edition_digests(path: Path) -> EditionDigests:
    """Parse the digests file at ``path``; an :class:`EditionDigestsError` names the path.

    Example::

        >>> read_edition_digests(Path("catalog/editions/v0.1.0/digests.toml"))  # doctest: +SKIP
    """
    try:
        return parse_edition_digests(path.read_text(encoding="utf-8"))
    except (OSError, EditionDigestsError) as exc:
        raise EditionDigestsError(f"{path}: {exc}") from exc


def parse_edition_digests(text: str) -> EditionDigests:
    """The :class:`EditionDigests` ``text`` holds; :class:`EditionDigestsError` names the fault.

    Example::

        >>> parse_edition_digests(render_edition_digests(EditionDigests("v9.9.9", "f00d", (), ()))).commit
        'f00d'
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise EditionDigestsError(f"malformed TOML: {exc}") from exc
    unknown = sorted(set(data) - _TOP_KEYS)
    if unknown:
        raise EditionDigestsError(f"unknown keys {unknown}; expected {sorted(_TOP_KEYS)}")
    if data.get("schema_version") != _SCHEMA_VERSION:
        raise EditionDigestsError(
            f"schema_version {data.get('schema_version')!r}; expected {_SCHEMA_VERSION}"
        )
    artifacts = tuple(_artifact(t) for t in _tables(data, "artifacts", _ARTIFACT_KEYS))
    pins = tuple(PinDigests(*(t[k] for k in _PIN_KEYS)) for t in _tables(data, "pins", _PIN_KEYS))
    _refuse_duplicates([(a.kind, a.id) for a in artifacts], "artifact")
    _refuse_duplicates([("pin", p.sample) for p in pins], "pin")
    return EditionDigests(_string(data, "tag"), _string(data, "commit"), artifacts, pins)


def _tables(data: dict[str, Any], key: str, keys: tuple[str, ...]) -> list[dict[str, str]]:
    tables = data.get(key, [])
    if not isinstance(tables, list):
        raise EditionDigestsError(f"{key} = {tables!r}; expected an array of tables")
    for table in tables:
        if not isinstance(table, dict) or set(table) != set(keys):
            raise EditionDigestsError(f"[[{key}]] entry {table!r}; expected exactly {keys}")
        for name in keys:
            _string(table, name)
    return tables


def _artifact(table: dict[str, str]) -> EditionArtifact:
    artifact = EditionArtifact(*(table[key] for key in _ARTIFACT_KEYS))
    if artifact.kind not in _ARTIFACT_KINDS:
        raise EditionDigestsError(
            f"artifact kind {artifact.kind!r}; expected one of {_ARTIFACT_KINDS}"
        )
    path = PurePosixPath(artifact.path)
    if path.is_absolute() or ".." in path.parts or path.parts[:1] != (_CORE_PREFIX,):
        raise EditionDigestsError(
            f"artifact path {artifact.path!r}; expected a relative path under {_CORE_PREFIX}/"
        )
    return artifact


def _refuse_duplicates(keys: list[tuple[str, str]], what: str) -> None:
    seen: set[tuple[str, str]] = set()
    for key in keys:
        if key in seen:
            raise EditionDigestsError(f"{what} {key[1]!r} is listed twice")
        seen.add(key)


def _string(table: dict[str, Any], key: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise EditionDigestsError(f"{key} = {value!r}; expected a non-empty string")
    return value
