"""An edition's files from its release tag, and the CI check that they still equal it (#281 ticket 13).

``scripts/release.py freeze vX`` builds edition ``vX`` from the tag alone:

- :func:`write_edition` copies each file the tag's manifest lists as graded
  (``release.manifest``: kind, id and repo path), and the license and
  attribution notices that text needs (``release.edition_notices``), byte for
  byte from the tag into ``catalog/editions/vX/core/<path under catalog/core/>``
  (:func:`edition_files`), writes the digests file without pins and the
  ``catalog/editions/README.md`` that says the directory is generated. Nothing
  parses the old tree with today's loaders: the manifest says what to copy, the
  tag's tree which notices exist (``TreeLister``) and git supplies the bytes
  (``BlobReader``).
- :func:`write_edition_digests` records the pins once the samples carry them.
- :func:`remove_edition` is ``unfreeze``'s half.

:func:`edition_tag_problems` is the check the CI job with full history runs on
every pull request: each edition's digests file names its tag's commit, lists
exactly the files the tag's manifest makes an edition hold (so a file dropped
from both the digests file and the directory is caught), and each frozen file
equals that tag's blob at the recorded path. The offline
checks (``evals.edition_checks``) compare the files with the digests file only,
so a hand edit that also updates the digests file is caught here.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.catalog.roots import CHECKOUT_CATALOG_DIRNAME
from coding_agent_playbook.release.edition_digests import (
    DIGESTS_FILENAME,
    EDITION_KINDS,
    EDITIONS_DIRNAME,
    NOTICE_KIND,
    EditionArtifact,
    EditionDigests,
    EditionDigestsError,
    PinDigests,
    edition_dir,
    read_edition_digests,
    render_edition_digests,
)
from coding_agent_playbook.release.edition_notices import notice_paths
from coding_agent_playbook.release.manifest import (
    MANIFEST_FILENAME,
    ManifestError,
    ReleaseManifest,
    parse_manifest,
    release_dir,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from coding_agent_playbook.release.edition_notices import TreeLister
    from coding_agent_playbook.release.manifest import ManifestEntry

__all__ = [
    "EDITIONS_README",
    "EDITIONS_README_FILENAME",
    "BlobReader",
    "CurrentPathFinder",
    "EditionFreezeError",
    "TagResolver",
    "current_file",
    "edition_files",
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
#: ``(kind, id)`` to the repo path of that artifact's current text, ``None`` when there is none.
type CurrentPathFinder = Callable[[str, str], str | None]

#: Sits beside the edition directories (``catalog/editions/README.md``), never inside one.
EDITIONS_README_FILENAME: Final = "README.md"
EDITIONS_README: Final = """\
# Editions: generated, never edit by hand

Each `<tag>/` directory here is a byte copy of the graded set (the graded
prompts and the rules they include) as release `<tag>` shipped it, with the
license and attribution notices that text needs. Only
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
    catalog_dir: Path,
    tag: str,
    commit: str,
    manifest: ReleaseManifest,
    read_blob: BlobReader,
    list_tree: TreeLister,
) -> EditionDigests:
    """Write edition ``tag`` (at ``commit``) from ``manifest``'s graded set; returns its digests.

    Replaces any earlier copy, so a re-run is idempotent. Raises
    :class:`EditionFreezeError` when an entry is outside the engine layer or the
    tag lacks its file; nothing is written then.

    Example::

        >>> write_edition(Path("catalog"), "v0.1.0", sha, manifest, reader, lister)  # doctest: +SKIP
    """
    files = edition_files(tag, commit, manifest, read_blob, list_tree)
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


def edition_files(
    tag: str, commit: str, manifest: ReleaseManifest, read_blob: BlobReader, list_tree: TreeLister
) -> list[tuple[EditionArtifact, bytes]]:
    """Every file edition ``tag`` holds, with its bytes at ``commit``: graded files, then notices.

    Raises :class:`EditionFreezeError` naming the entry or file the tag lacks.

    Example::

        >>> [a.kind for a, _ in edition_files("v0.1.0", sha, manifest, reader, lister)]  # doctest: +SKIP
        ['prompt', 'rule', 'notice', 'notice']
    """
    graded = [_frozen_file(entry, tag, commit, read_blob) for entry in manifest.graded]
    paths = notice_paths((entry.path for entry in manifest.graded), commit, list_tree)
    return graded + [_notice_file(path, tag, commit, read_blob) for path in paths]


def _notice_file(
    path: str, tag: str, commit: str, read_blob: BlobReader
) -> tuple[EditionArtifact, bytes]:
    data = read_blob(commit, path)
    if data is None:
        raise EditionFreezeError(f"tag {tag} ({commit}) lists the notice {path} but has no blob")
    rel = _edition_path(path)
    return EditionArtifact(NOTICE_KIND, rel, rel, hashlib.sha256(data).hexdigest()), data


def _edition_path(repo_path: str) -> str:
    """``catalog/core/x`` is ``core/x`` in the edition."""
    return PurePosixPath(repo_path).relative_to(CHECKOUT_CATALOG_DIRNAME).as_posix()


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
    rel = _edition_path(entry.path)
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
    catalog_dir: Path,
    resolve_tag: TagResolver,
    read_blob: BlobReader,
    list_tree: TreeLister,
    current_path: CurrentPathFinder | None = None,
) -> list[str]:
    """Every way the editions of ``catalog_dir`` differ from their tags; ``[]`` when none does.

    ``current_path`` names the file to edit when an artifact's recorded path no
    longer exists in the checkout (it moved or was renamed since the tag).

    Example::

        >>> edition_tag_problems(Path("catalog"), resolver, reader, lister)  # doctest: +SKIP
        []
    """
    editions = catalog_dir / EDITIONS_DIRNAME
    if not editions.is_dir():
        return []
    check = _TagCheck(catalog_dir, resolve_tag, read_blob, list_tree, current_path)
    roots = sorted(entry for entry in editions.iterdir() if entry.is_dir())
    return [problem for root in roots for problem in check.problems(root)]


@dataclass(frozen=True)
class _TagCheck:
    """The tag check of one catalog: its inputs, shared by every edition directory."""

    catalog_dir: Path
    resolve_tag: TagResolver
    read_blob: BlobReader
    list_tree: TreeLister
    current_path: CurrentPathFinder | None

    def problems(self, root: Path) -> list[str]:
        """Every way the edition at ``root`` differs from its tag."""
        try:
            digests = read_edition_digests(root / DIGESTS_FILENAME)
        except EditionDigestsError as exc:
            return [str(exc)]
        commit = self.resolve_tag(root.name)
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
        try:
            expected = self._expected_files(root.name, commit)
        except (EditionFreezeError, ManifestError) as exc:
            return [f"{root}: {exc}"]
        blobs = {artifact.path: data for artifact, data in expected}
        return _listing_problems(root, digests, expected) + [
            p
            for a in digests.artifacts
            if a.path in blobs and (p := self._file_problem(root, a, blobs[a.path]))
        ]

    def _expected_files(self, tag: str, commit: str) -> list[tuple[EditionArtifact, bytes]]:
        """What tag ``tag``'s own manifest makes the edition hold, with the tag's bytes."""
        version = tag.removeprefix("v")
        path = (release_dir(Path(CHECKOUT_CATALOG_DIRNAME), version) / MANIFEST_FILENAME).as_posix()
        data = self.read_blob(commit, path)
        if data is None:
            raise EditionFreezeError(f"tag {tag} ({commit}) has no manifest at {path}")
        manifest = parse_manifest(data.decode("utf-8"))
        return edition_files(tag, commit, manifest, self.read_blob, self.list_tree)

    def _file_problem(self, root: Path, artifact: EditionArtifact, blob: bytes) -> str:
        path = root / artifact.path
        recorded = current_file(artifact.path)
        if not path.is_file():
            return f"{path}: missing; tag {root.name} has it at {recorded}"
        if path.read_bytes() == blob:
            return ""
        differs = f"{path}: differs from tag {root.name}'s {recorded}; editions are frozen copies"
        target = self._edit_target(artifact)
        if target is None:
            return (
                f"{differs}, and the current catalog has no {artifact.kind} {artifact.id!r} to "
                f"edit instead: restore it with `scripts/release.py freeze {root.name}`"
            )
        return f"{differs}, edit the current text in {target} instead"

    def _edit_target(self, artifact: EditionArtifact) -> str | None:
        """``artifact``'s current file: its recorded path while that exists, else a lookup.

        A notice has no id to look up, so a moved notice has no target.
        """
        if (self.catalog_dir / artifact.path).is_file():
            return current_file(artifact.path)
        if self.current_path is None or artifact.kind == NOTICE_KIND:
            return None
        return self.current_path(artifact.kind, artifact.id)


def _listing_problems(
    root: Path, digests: EditionDigests, expected: list[tuple[EditionArtifact, bytes]]
) -> list[str]:
    """Files the digests file lists that the tag does not put in the edition, and the reverse."""
    recorded = {(a.kind, a.id, a.path) for a in digests.artifacts}
    wanted = {(a.kind, a.id, a.path) for a, _ in expected}
    where, tag = root / DIGESTS_FILENAME, root.name
    fix = f"unfreeze and freeze {tag} again"
    missing = [
        f"{where}: lists no {kind} {aid!r} at {rel}, which tag {tag}'s manifest puts in the "
        f"edition; {fix}"
        for kind, aid, rel in sorted(wanted - recorded)
    ]
    extra = [
        f"{where}: lists {kind} {aid!r} at {rel}, which tag {tag}'s manifest does not put in "
        f"the edition; {fix}"
        for kind, aid, rel in sorted(recorded - wanted)
    ]
    return missing + extra
