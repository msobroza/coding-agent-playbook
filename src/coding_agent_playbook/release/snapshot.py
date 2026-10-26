"""Build a :class:`~coding_agent_playbook.release.manifest.ReleaseManifest` from a catalog.

:func:`shipped_source` opens the engine's catalog with every bundled plugin;
:func:`build_manifest` digests what it ships (``catalog.digest.artifact_digest``)
and the graded set (``release.graded_set``) into one manifest;
:func:`core_artifact_paths` says where each core prompt and rule lives today, for
the edition tag check's error messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.artifacts.hook import Hook
from coding_agent_playbook.artifacts.identity import artifact_id_of
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.catalog.digest import artifact_digest, digest_kind
from coding_agent_playbook.catalog.layers import REPO_LOCAL_SOURCE
from coding_agent_playbook.catalog.roots import CHECKOUT_CATALOG_DIRNAME, bundled_plugins
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.release.graded_set import core_graded_prompt_ids, graded_set
from coding_agent_playbook.release.manifest import ManifestEntry, ReleaseManifest

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule

__all__ = ["build_manifest", "core_artifact_paths", "shipped_source"]

type _Shipped = Rule | Prompt | Skill | Hook


def shipped_source(repo_root: Path, catalog_dir: Path) -> FileSystemArtifactSource:
    """The engine layer plus every bundled plugin under ``catalog_dir``: what a release ships.

    ``catalog_dir`` must be the catalog the engine itself loads
    (``catalog.roots.catalog_root()``); it only names the plugins here.

    Example::

        >>> shipped_source(Path("."), catalog_root()).overlay_packages  # doctest: +SKIP
        ('coding_agent_playbook.plugins.mattpocock_skills', 'coding_agent_playbook.plugins.superpowers')
    """
    return FileSystemArtifactSource(
        repo_root=repo_root, overlay_packages=bundled_plugins(catalog_dir)
    )


def build_manifest(
    source: FileSystemArtifactSource, catalog_dir: Path, *, version: str, base: str
) -> ReleaseManifest:
    """The manifest of release ``version`` prepared from commit ``base``.

    ``catalog_dir`` is the catalog root the source reads; entry paths are written
    relative to the repository (``catalog/...``). Raises
    :class:`~coding_agent_playbook.release.graded_set.GradedSetError` when a
    sample grades a prompt core does not ship.

    Example::

        >>> build_manifest(source, catalog_root(), version="9.9.9", base="f00d").base  # doctest: +SKIP
        'f00d'
    """
    rules = source.list_rules()
    prompts = source.list_prompts()
    twins = [twin for layer in source.prompt_set_layers() for twin in layer.twins]
    shipped: list[_Shipped] = [*rules, *prompts, *twins, *source.list_skills()]
    shipped.extend(source.list_hooks())
    core_prompts = [p for p in prompts if p.source_package == source.engine_package]
    core_rules = [r for r in rules if r.source_package == source.engine_package]
    graded = graded_set(core_graded_prompt_ids(source), core_prompts, core_rules)
    return ReleaseManifest(
        version=version,
        base=base,
        graded=_entries([*graded.prompts, *graded.rules], catalog_dir),
        artifacts=_entries(
            (item for item in shipped if item.source_package != REPO_LOCAL_SOURCE), catalog_dir
        ),
    )


def core_artifact_paths(
    source: FileSystemArtifactSource, catalog_dir: Path
) -> dict[tuple[str, str], str]:
    """``(kind, id)`` to the repo path (``catalog/...``) of each core prompt and rule ``source`` loads.

    Example::

        >>> core_artifact_paths(source, catalog_root())[("prompt", "review")]  # doctest: +SKIP
        'catalog/core/prompts/review.md.j2'
    """
    loaded: list[_Shipped] = [*source.list_rules(), *source.list_prompts()]
    core = [item for item in loaded if item.source_package == source.engine_package]
    return {
        (digest_kind(item), artifact_id_of(item)): _repo_path(item, catalog_dir) for item in core
    }


def _entries(artifacts: Iterable[_Shipped], catalog_dir: Path) -> tuple[ManifestEntry, ...]:
    entries = {
        ManifestEntry(
            layer=item.source_package,
            kind=digest_kind(item),
            id=artifact_id_of(item),
            path=_repo_path(item, catalog_dir),
            digest=artifact_digest(item),
        )
        for item in artifacts
    }
    return tuple(sorted(entries))


def _repo_path(artifact: _Shipped, catalog_dir: Path) -> str:
    """``catalog/<path under catalog_dir>`` of the artifact's file or directory."""
    location = _location(artifact)
    try:
        relative = location.relative_to(catalog_dir)
    except ValueError:
        raise ValueError(
            f"{location} is outside the catalog {catalog_dir}; a release ships only catalog files"
        ) from None
    return f"{CHECKOUT_CATALOG_DIRNAME}/{relative.as_posix()}"


def _location(artifact: _Shipped) -> Path:
    found = _artifact_path(artifact)
    if found is None:
        raise ValueError(f"{artifact_id_of(artifact)!r} was not loaded from a file")
    return found


def _artifact_path(artifact: _Shipped) -> Path | None:
    """A skill's or hook's directory; a rule's or prompt's file."""
    if isinstance(artifact, Hook):
        return artifact.hook_dir
    if isinstance(artifact, Skill):
        return artifact.source_dir
    return artifact.source_path
