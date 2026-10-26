"""``scripts/release.py freeze``, ``unfreeze`` and ``check-editions``: the git side (#281 ticket 13).

The decisions and file writes are the engine's (``release.edition_freeze`` for
the edition's files and the tag check, ``evals.edition_pins`` for the pins);
this module gathers their inputs through git and says what to commit:

- :func:`freeze_change` resolves tag ``vX`` to its commit, reads that commit's
  ``catalog/releases/X/manifest.toml`` with ``git show`` (never today's loaders
  over the old tree), copies each graded file's blob into the edition with the
  license and attribution notices it needs (found with ``git ls-tree``), pins
  the graded core samples, records the digests and re-runs the offline edition
  checks over the result;
- :func:`unfreeze_change` drops the pins and the edition;
- :func:`check_editions` compares every edition with its tag's manifest and
  blobs, for the CI job that has the full history and the tags; a file that
  moved since the tag is named at its current path.

``release.py`` commits a change on its branch, pushes it and opens (or reuses)
its pull request through the same path ``prepare`` uses.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from coding_agent_playbook.catalog.roots import catalog_root
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.evals.edition_checks import edition_problems
from coding_agent_playbook.evals.edition_pins import pin_graded_samples, unpin_samples
from coding_agent_playbook.release.edition_build import git_blob_reader, git_tree_lister
from coding_agent_playbook.release.edition_digests import NOTICE_KIND, edition_dir
from coding_agent_playbook.release.edition_freeze import (
    CurrentPathFinder,
    edition_tag_problems,
    graded_prompt_ids,
    remove_edition,
    write_edition,
    write_edition_digests,
)
from coding_agent_playbook.release.manifest import (
    MANIFEST_FILENAME,
    ReleaseManifest,
    parse_manifest,
    release_dir,
)
from coding_agent_playbook.release.snapshot import core_artifact_paths
from coding_agent_playbook.release.versions import is_release_tag

if TYPE_CHECKING:
    from collections.abc import Sequence

FREEZE: Final = "freeze"
UNFREEZE: Final = "unfreeze"
_CATALOG: Final = "catalog"


class EditionRefusal(Exception):
    """``freeze`` or ``unfreeze`` must not run; the message says why and what to do."""


class _Done(Protocol):
    @property
    def returncode(self) -> int: ...
    @property
    def stdout(self) -> str: ...


class EditionTools(Protocol):
    """What the edition commands need of ``release.Tools``."""

    @property
    def cwd(self) -> Path: ...
    def run(self, argv: Sequence[str]) -> _Done: ...


@dataclass(frozen=True)
class EditionChange:
    """What one ``freeze``/``unfreeze`` run wrote: its commit title, PR body and paths to stage."""

    title: str
    body: str
    paths: tuple[str, ...] = (_CATALOG,)


def edition_branch(command: str, tag: str) -> str:
    """The branch of ``freeze``/``unfreeze`` ``tag``: ``freeze/v0.1.0``.

    Example::

        >>> edition_branch("freeze", "v9.9.9")
        'freeze/v9.9.9'
    """
    return f"{command}/{tag}"


def freeze_change(tools: EditionTools, tag: str) -> EditionChange:
    """Write edition ``tag`` from the tag and pin the graded core samples to it.

    Refuses (:class:`EditionRefusal`) when ``tag`` is not a release tag, does not
    exist, or has no manifest.
    """
    commit = _tag_commit(tools, tag)
    if commit is None:
        raise EditionRefusal(f"no tag {tag}: freeze copies a released tag (fetch the tags first)")
    manifest = _manifest_at(tools, tag, commit)
    catalog = tools.cwd / _CATALOG
    reader, lister = git_blob_reader(tools.cwd), git_tree_lister(tools.cwd)
    digests = write_edition(catalog, tag, commit, manifest, reader, lister)
    pins = pin_graded_samples(catalog, tag, graded_prompt_ids(manifest))
    write_edition_digests(edition_dir(catalog, tag), digests, pins)
    problems = edition_problems(catalog)
    if problems:
        raise EditionRefusal(f"edition {tag} fails the edition checks:\n" + "\n".join(problems))
    samples = "".join(f"- `{pin.sample}`\n" for pin in sorted(pins))
    notices = sum(artifact.kind == NOTICE_KIND for artifact in digests.artifacts)
    body = (
        f"Freezes edition `{tag}` (commit `{commit}`): the {len(digests.artifacts) - notices} "
        f"graded files of its manifest and the {notices} license and attribution notices they "
        f"need, copied from the tag into `catalog/editions/{tag}/`, and pins "
        f"these core eval samples to it:\n\n{samples}\n"
        f"Written by `scripts/release.py freeze {tag}`; undo with `unfreeze {tag}`.\n"
    )
    return EditionChange(f"chore(evals): freeze edition {tag}", body)


def unfreeze_change(tools: EditionTools, tag: str) -> EditionChange:
    """Drop every pin on edition ``tag`` and the edition; refuses when neither exists."""
    _refuse_non_release_tag(tag)
    catalog = tools.cwd / _CATALOG
    unpinned = unpin_samples(catalog, tag)
    existed = remove_edition(catalog, tag)
    if not unpinned and not existed:
        raise EditionRefusal(f"nothing to unfreeze: no edition {tag} and no sample pins it")
    samples = "".join(f"- `{sample}`\n" for sample in unpinned) or "- (none)\n"
    body = (
        f"Unfreezes edition `{tag}`: removes `catalog/editions/{tag}/` and the pins of these "
        f"core eval samples, which grade the current text again:\n\n{samples}\n"
        f"Written by `scripts/release.py unfreeze {tag}`.\n"
    )
    return EditionChange(f"chore(evals): unfreeze edition {tag}", body)


def check_editions(tools: EditionTools, current_path: CurrentPathFinder | None = None) -> list[str]:
    """Every way the checkout's editions differ from their tags; ``[]`` when none does.

    ``current_path`` defaults to a lookup in the engine's own catalog
    (:func:`engine_current_paths`), which loads only when a recorded path is gone.
    """
    catalog = tools.cwd / _CATALOG
    return edition_tag_problems(
        catalog,
        lambda tag: _tag_commit(tools, tag),
        git_blob_reader(tools.cwd),
        git_tree_lister(tools.cwd),
        current_path or engine_current_paths(tools.cwd),
    )


def engine_current_paths(repo: Path) -> CurrentPathFinder:
    """``(kind, id)`` to its file in the engine's own catalog, loaded on the first lookup.

    Example::

        >>> engine_current_paths(Path("."))("prompt", "review")  # doctest: +SKIP
        'catalog/core/prompts/review.md.j2'
    """

    @functools.cache
    def paths() -> dict[tuple[str, str], str]:
        return core_artifact_paths(FileSystemArtifactSource(repo_root=repo), catalog_root())

    return lambda kind, artifact_id: paths().get((kind, artifact_id))


def _refuse_non_release_tag(tag: str) -> None:
    if not is_release_tag(tag):
        raise EditionRefusal(f"{tag!r} is not a release tag; expected vX.Y.Z")


def _tag_commit(tools: EditionTools, tag: str) -> str | None:
    _refuse_non_release_tag(tag)
    done = tools.run(["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"])
    return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else None


def _manifest_at(tools: EditionTools, tag: str, commit: str) -> ReleaseManifest:
    """Tag ``tag``'s own manifest, read from its commit with ``git show``."""
    path = (release_dir(Path(_CATALOG), tag.removeprefix("v")) / MANIFEST_FILENAME).as_posix()
    done = tools.run(["git", "show", f"{commit}:{path}"])
    if done.returncode != 0:
        raise EditionRefusal(
            f"tag {tag} ({commit}) has no manifest at {path}: only a release prepared by "
            "`scripts/release.py prepare` can be frozen"
        )
    return parse_manifest(done.stdout)
