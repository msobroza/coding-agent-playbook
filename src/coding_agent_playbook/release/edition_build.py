"""Build an edition from its release tag into any catalog directory, through git (#281 ticket 14).

``playbook eval --compare edition:<tag>`` grades a release's graded set without
freezing it: :func:`build_edition` resolves the tag, reads the tag's own
manifest with ``git show`` and copies each graded file's blob with
``release.edition_freeze.write_edition``, the copy ``scripts/release.py freeze``
makes (license and attribution notices included, listed with
:func:`git_tree_lister`), into a scratch catalog directory (the comparison's
work directory). ``scripts/release.py`` freezes and checks editions through the
same two git readers, so a built edition and a frozen one hold the same files.
Nothing is committed and the repository's ``catalog/editions/`` is not touched.

Every git call is bounded by :data:`GIT_TIMEOUT_SECONDS` and touches only the
local repository.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.catalog.roots import CHECKOUT_CATALOG_DIRNAME
from coding_agent_playbook.release.edition_digests import edition_dir
from coding_agent_playbook.release.edition_freeze import write_edition
from coding_agent_playbook.release.manifest import (
    MANIFEST_FILENAME,
    ManifestError,
    ReleaseManifest,
    parse_manifest,
    release_dir,
)
from coding_agent_playbook.release.versions import is_release_tag

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.release.edition_freeze import BlobReader
    from coding_agent_playbook.release.edition_notices import TreeLister

__all__ = [
    "GIT_TIMEOUT_SECONDS",
    "EditionBuildError",
    "build_edition",
    "git_blob_reader",
    "git_tree_lister",
    "tag_commit",
    "tag_manifest",
]

#: Bounds each git call; none of them waits on the network.
GIT_TIMEOUT_SECONDS: Final = 60
#: Variables that point git at another repository (a hook in a linked worktree
#: exports them); the reads here must act on ``repo``. The full list lives in
#: ``evals.run.git_env``, a layer above this one; these reads only need the
#: variables that relocate the object store and refs.
_REPO_LOCATION_VARS: Final = (
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_WORK_TREE",
)


class EditionBuildError(ValueError):
    """An edition that cannot be built from its tag; the message names the tag and what is missing."""


def build_edition(repo: Path, tag: str, catalog_dir: Path) -> Path:
    """Write edition ``tag`` of ``repo`` under ``catalog_dir``; returns the edition's directory.

    Raises :class:`EditionBuildError` when ``tag`` is not a release tag, does
    not exist, has no manifest, or lacks a file its manifest grades.

    Example::

        >>> build_edition(Path("."), "v0.1.0", work / "edition-base")  # doctest: +SKIP
        PosixPath('.../edition-base/editions/v0.1.0')
    """
    commit, manifest = tag_manifest(repo, tag)
    try:
        reader, lister = git_blob_reader(repo), git_tree_lister(repo)
        write_edition(catalog_dir, tag, commit, manifest, reader, lister)
    except ValueError as exc:
        raise EditionBuildError(f"edition {tag} cannot be built: {exc}") from exc
    return edition_dir(catalog_dir, tag)


def tag_manifest(repo: Path, tag: str) -> tuple[str, ReleaseManifest]:
    """Tag ``tag``'s commit and the manifest that commit records, read with ``git show``.

    Example::

        >>> tag_manifest(Path("."), "v0.1.0")[1].version  # doctest: +SKIP
        '0.1.0'
    """
    commit = tag_commit(repo, tag)
    if commit is None:
        raise EditionBuildError(f"no tag {tag} in {repo} (fetch the tags: `git fetch --tags`)")
    rel = release_dir(Path(CHECKOUT_CATALOG_DIRNAME), tag.removeprefix("v")) / MANIFEST_FILENAME
    done = _git(repo, ["show", f"{commit}:{rel.as_posix()}"])
    if done.returncode != 0:
        raise EditionBuildError(
            f"tag {tag} ({commit}) has no manifest at {rel.as_posix()}: only a release "
            "prepared by `scripts/release.py prepare` has a graded set to build"
        )
    try:
        return commit, parse_manifest(done.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ManifestError) as exc:
        raise EditionBuildError(f"tag {tag}'s {rel.as_posix()} cannot be read: {exc}") from exc


def tag_commit(repo: Path, tag: str) -> str | None:
    """The commit release tag ``tag`` names, ``None`` when ``repo`` has no such tag.

    Example::

        >>> tag_commit(Path("."), "v99.0.0") is None  # doctest: +SKIP
        True
    """
    if not is_release_tag(tag):
        raise EditionBuildError(f"{tag!r} is not a release tag; expected vX.Y.Z")
    done = _git(repo, ["rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"])
    commit = done.stdout.decode("utf-8", "replace").strip()
    return commit if done.returncode == 0 and commit else None


def git_blob_reader(repo: Path) -> BlobReader:
    """Read a blob's raw bytes (``git cat-file blob``: no text decoding, no filters).

    Example::

        >>> git_blob_reader(Path("."))("HEAD", "pyproject.toml")[:9]  # doctest: +SKIP
        b'[project]'
    """

    def read(commit: str, path: str) -> bytes | None:
        done = _git(repo, ["cat-file", "blob", f"{commit}:{path}"])
        return done.stdout if done.returncode == 0 else None

    return read


def git_tree_lister(repo: Path) -> TreeLister:
    """List the files directly in one directory of a commit (``git ls-tree``, blobs only).

    Raises :class:`EditionBuildError` when git cannot list ``directory``.

    Example::

        >>> git_tree_lister(Path("."))("HEAD", "catalog/core")  # doctest: +SKIP
        ['catalog/core/ATTRIBUTIONS.md']
    """

    def list_files(commit: str, directory: str) -> list[str]:
        args = ["ls-tree", "-z", commit, "--", f"{directory}/"]
        done = _git(repo, args)
        if done.returncode != 0:
            stderr = done.stderr.decode("utf-8", "replace").strip()
            raise EditionBuildError(f"`git {' '.join(args)}` failed in {repo}: {stderr}")
        rows = done.stdout.decode("utf-8").split("\0")
        return [row.partition("\t")[2] for row in rows if _is_blob_row(row)]

    return list_files


def _is_blob_row(row: str) -> bool:
    """Whether a ``git ls-tree`` row (``<mode> <type> <sha>\\t<path>``) names a file."""
    return row.split(" ", 2)[1:2] == ["blob"]


def _git(repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    env = {key: value for key, value in os.environ.items() if key not in _REPO_LOCATION_VARS}
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            env=env,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EditionBuildError(f"`git {' '.join(args)}` failed in {repo}: {exc}") from exc
