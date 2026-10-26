"""An edition's files from its release tag, and the CI check that they still equal it (#281 ticket 13).

``scripts/release.py freeze vX`` builds edition ``vX`` from the tag alone:

- :func:`write_edition` copies each file the tag's manifest lists as graded
  (``release.manifest``: kind, id and repo path) byte for byte from the tag into
  ``catalog/editions/vX/core/<path under catalog/core/>``, writes the digests
  file without pins and the ``catalog/editions/README.md`` that says the
  directory is generated. Nothing parses the old tree with today's loaders: the
  manifest says what to copy and git supplies the bytes (``BlobReader``).
- :func:`write_edition_digests` records the pins once the samples carry them.
- :func:`remove_edition` is ``unfreeze``'s half.

:func:`edition_tag_problems` is the check the CI job with full history runs on
every pull request: each edition's digests file names its tag's commit, and
each frozen file equals that tag's blob at the recorded path. The offline
checks (``evals.edition_checks``) compare the files with the digests file only,
so a hand edit that also updates the digests file is caught here.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import replace
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.catalog.roots import CHECKOUT_CATALOG_DIRNAME
from coding_agent_playbook.release.edition_digests import (
    DIGESTS_FILENAME,
    EDITION_KINDS,
    EDITIONS_DIRNAME,
    EditionArtifact,
    EditionDigests,
    EditionDigestsError,
    PinDigests,
    edition_dir,
    read_edition_digests,
    render_edition_digests,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from coding_agent_playbook.release.manifest import ManifestEntry, ReleaseManifest

__all__ = [
    "EDITIONS_README",
    "EDITIONS_README_FILENAME",
    "BlobReader",
    "EditionFreezeError",
    "TagResolver",
    "current_file",
    "edition_tag_problems",
    "graded_prompt_ids",
    "remove_edition",
    "write_edition",
    "write_edition_digests",
]

#: ``(commit, repo-relative path)`` to that blob's bytes, ``None`` when the commit has no such file.
type BlobReader = Callable[[str, str], bytes | None]
#: A tag name to the commit it names, ``None`` when no such tag exists.
type TagResolver = Callable[[str], str | None]

#: Sits beside the edition directories (``catalog/editions/README.md``), never inside one.
EDITIONS_README_FILENAME: Final = "README.md"
EDITIONS_README: Final = """\
# Editions: generated, never edit by hand

Each `<tag>/` directory here is a byte copy of the graded set (the graded
prompts and the rules they include) as release `<tag>` shipped it. Only
`scripts/release.py freeze <tag>` writes one and only
`scripts/release.py unfreeze <tag>` removes it; eval samples pinned to an
edition grade these files, so CI fails when a file differs from its tag.

To change the guidance, edit the current text instead: `<tag>/core/<path>` is a
copy of `catalog/core/<path>`.
"""

_ENGINE_LAYER_PREFIX: Final = f"{CHECKOUT_CATALOG_DIRNAME}/core/"


class EditionFreezeError(ValueError):
    """An edition that cannot be frozen from its tag; the message names the tag and path."""


def graded_prompt_ids(manifest: ReleaseManifest) -> list[str]:
    """The ids of the prompts ``manifest`` lists as graded, sorted.

    Example::

        >>> graded_prompt_ids(ReleaseManifest("9.9.9", "f00d", (), ()))
        []
    """
    return sorted({entry.id for entry in manifest.graded if entry.kind == "prompt"})


def current_file(edition_path: str) -> str:
    """The repo path of the current text an edition file copies (``core/x`` is ``catalog/core/x``).

    Example::

        >>> current_file("core/prompts/review.md.j2")
        'catalog/core/prompts/review.md.j2'
    """
    return f"{CHECKOUT_CATALOG_DIRNAME}/{edition_path}"


def write_edition(
    catalog_dir: Path, tag: str, commit: str, manifest: ReleaseManifest, read_blob: BlobReader
) -> EditionDigests:
    """Write edition ``tag`` (at ``commit``) from ``manifest``'s graded set; returns its digests.

    Replaces any earlier copy, so a re-run is idempotent. Raises
    :class:`EditionFreezeError` when an entry is outside the engine layer or the
    tag lacks its file; nothing is written then.

    Example::

        >>> write_edition(Path("catalog"), "v0.1.0", sha, manifest, reader)  # doctest: +SKIP
    """
    files = [_frozen_file(entry, tag, commit, read_blob) for entry in manifest.graded]
    root = edition_dir(catalog_dir, tag)
    shutil.rmtree(root, ignore_errors=True)
    for artifact, data in files:
        target = root / artifact.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    readme = root.parent / EDITIONS_README_FILENAME
    readme.write_text(EDITIONS_README, encoding="utf-8")
    digests = EditionDigests(tag, commit, tuple(sorted(a for a, _ in files)), ())
    write_edition_digests(root, digests, ())
    return digests


def _frozen_file(
    entry: ManifestEntry, tag: str, commit: str, read_blob: BlobReader
) -> tuple[EditionArtifact, bytes]:
    if entry.kind not in EDITION_KINDS or not entry.path.startswith(_ENGINE_LAYER_PREFIX):
        raise EditionFreezeError(
            f"tag {tag}'s manifest grades {entry.kind} {entry.id!r} at {entry.path}; an edition "
            f"holds only {EDITION_KINDS} files under {_ENGINE_LAYER_PREFIX}"
        )
    data = read_blob(commit, entry.path)
    if data is None:
        raise EditionFreezeError(
            f"tag {tag} ({commit}) has no file {entry.path}, which its manifest grades"
        )
    rel = PurePosixPath(entry.path).relative_to(CHECKOUT_CATALOG_DIRNAME).as_posix()
    return EditionArtifact(entry.kind, entry.id, rel, hashlib.sha256(data).hexdigest()), data


def write_edition_digests(root: Path, digests: EditionDigests, pins: Sequence[PinDigests]) -> None:
    """Write ``digests`` with ``pins`` (replacing any it held) to ``root``'s digests file."""
    text = render_edition_digests(replace(digests, pins=tuple(sorted(pins))))
    (root / DIGESTS_FILENAME).write_text(text, encoding="utf-8")


def remove_edition(catalog_dir: Path, tag: str) -> bool:
    """Delete edition ``tag``; returns whether it existed.

    With the last edition gone, the README and the empty ``editions/`` go too.
    """
    root = edition_dir(catalog_dir, tag)
    existed = root.is_dir()
    shutil.rmtree(root, ignore_errors=True)
    editions = catalog_dir / EDITIONS_DIRNAME
    if editions.is_dir() and not any(entry.is_dir() for entry in editions.iterdir()):
        (editions / EDITIONS_README_FILENAME).unlink(missing_ok=True)
        if not any(editions.iterdir()):
            editions.rmdir()
    return existed


# --------------------------------------------------------------------------- #
# The CI check
# --------------------------------------------------------------------------- #


def edition_tag_problems(
    catalog_dir: Path, resolve_tag: TagResolver, read_blob: BlobReader
) -> list[str]:
    """Every way the editions of ``catalog_dir`` differ from their tags; ``[]`` when none does.

    Example::

        >>> edition_tag_problems(Path("catalog"), resolver, reader)  # doctest: +SKIP
        []
    """
    editions = catalog_dir / EDITIONS_DIRNAME
    if not editions.is_dir():
        return []
    roots = sorted(entry for entry in editions.iterdir() if entry.is_dir())
    return [problem for root in roots for problem in _tag_problems(root, resolve_tag, read_blob)]


def _tag_problems(root: Path, resolve_tag: TagResolver, read_blob: BlobReader) -> list[str]:
    try:
        digests = read_edition_digests(root / DIGESTS_FILENAME)
    except EditionDigestsError as exc:
        return [str(exc)]
    commit = resolve_tag(root.name)
    if commit is None:
        return [
            f"{root}: no tag {root.name} in this clone; fetch the tags (`git fetch --tags`), "
            "or unfreeze an edition whose tag is gone"
        ]
    if digests.commit != commit:
        return [
            f"{root / DIGESTS_FILENAME}: records commit {digests.commit}, but tag "
            f"{root.name} names commit {commit}; unfreeze and freeze it again"
        ]
    return [p for a in digests.artifacts if (p := _file_problem(root, a, commit, read_blob))]


def _file_problem(root: Path, artifact: EditionArtifact, commit: str, read_blob: BlobReader) -> str:
    path = root / artifact.path
    current = current_file(artifact.path)
    if not path.is_file():
        return f"{path}: missing; tag {root.name} has it at {current}"
    if path.read_bytes() != read_blob(commit, current):
        return (
            f"{path}: differs from tag {root.name}'s {current}; editions are frozen copies, "
            f"edit the current text in {current} instead"
        )
    return ""
