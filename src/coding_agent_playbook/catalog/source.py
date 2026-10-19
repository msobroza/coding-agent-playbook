"""The ArtifactSource ABC and its filesystem implementation (SPEC.md §20.2, §20.3).

Third-party sources register via the ``coding_agent_playbook.artifact_sources``
entry point declared in ``pyproject.toml``. The filesystem source is the v1
implementation. It depends only on stdlib (pathlib, importlib.resources,
importlib.metadata) plus pyyaml for the frontmatter helpers already in types.py.
The StateSource ABC and FileSystemStateSource live in ``config/files.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

# A stdlib-only package module, so this stays a light import.
from coding_agent_playbook.artifacts.hook_schema import HookSchemaError
from coding_agent_playbook.catalog._hook_walk import walk_hook_layer
from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE, REPO_LOCAL_SOURCE
from coding_agent_playbook.catalog.roots import catalog_layer_root, is_bundled_layer
from coding_agent_playbook.evals.loader import (
    discover_eval_task_dirs,
    load_eval_task_from_dir,
)
from coding_agent_playbook.types import Prompt, Rule, Skill, split_frontmatter

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from typing import TypeVar

    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.types import Hook

    _T = TypeVar("_T")


class ArtifactSource(ABC):
    """Where rules, prompts, skills, hooks, and eval tasks come from."""

    name: str

    @abstractmethod
    def list_rules(self) -> list[Rule]: ...

    @abstractmethod
    def list_prompts(self) -> list[Prompt]: ...

    @abstractmethod
    def list_skills(self) -> list[Skill]: ...

    def list_hooks(self) -> list[Hook]:
        """Every hook this source ships, raising ``HookSchemaError`` on a malformed one.

        Concrete, returning ``[]``, not abstract: a third-party source written
        before hooks existed must still instantiate (prK §A.5).

        Example::

            >>> source.list_hooks()  # doctest: +SKIP
            []
        """
        return []

    def collect_hooks(self) -> tuple[list[Hook], list[HookSchemaError]]:
        """Every well-formed hook plus the errors of malformed ones, never raising.

        What ``playbook validate`` reads, so it can report every malformed hook
        (prK §P P8c). This default can only record the one error a failing
        :meth:`list_hooks` raises; a source that sees each hook overrides it.

        Example::

            >>> hooks, errors = source.collect_hooks()  # doctest: +SKIP
        """
        try:
            return self.list_hooks(), []
        except HookSchemaError as exc:
            return [], [exc]

    @abstractmethod
    def list_eval_tasks(self) -> list[EvalTask]: ...


def _resource_subdir(package: str, subdir: str) -> Path | None:
    """Resolve a layer's ``<subdir>`` kind directory, or ``None`` when it ships none.

    A bundled layer (the engine, or a bundled plugin under either namespace)
    reads ``<subdir>`` from its directory in the catalog root
    (``catalog.roots.catalog_layer_root``) and is never imported. Every other
    package resolves ``<package>/resources/<subdir>`` via importlib.resources.

    Returns ``None`` if the package is not importable, has no ``resources/``
    directory, or has no matching subdirectory, so sources silently skip
    packages that ship no artifacts of a given kind (SPEC §20.3). The one raise
    is :class:`CatalogMissingError` for a bundled layer when the engine's
    catalog root is missing: a broken install must fail loudly, not render
    without the engine's artifacts.
    """
    # Outside the ``except Exception`` guard below on purpose: a missing catalog
    # root must propagate, never read as "this layer ships nothing".
    if is_bundled_layer(package):
        return _bundled_subdir(package, subdir)
    try:
        resource_root = resources.files(package).joinpath("resources", subdir)
    except Exception:
        # ``files()`` imports the package, and an overlay's import may raise
        # anything (its own code, a missing dependency, an empty name). Skip it
        # like a missing one: sync/validate/check/init run the shared
        # ``validation.preflight.unusable_overlays`` check, which names it and the
        # error, so discovery must not crash before that check can report it.
        return None
    # We need a ``Path`` for ``rglob``-based walking, not just a
    # ``Traversable``. On the on-disk backend, ``resources.files(<package>)`` is a
    # ``PosixPath``, or a ``MultiplexedPath`` for a namespace package spread over
    # several portions. ``str()`` of a ``MultiplexedPath`` is not a filesystem
    # path, so the conversion is safe only because it happens after the full
    # two-segment join, which descends into the one portion holding ``<subdir>``.
    # The limit (pre-existing, not supported): a kind directory that itself spans
    # portions stays a ``MultiplexedPath``, ``Path(str(...))`` is not a directory,
    # and that overlay's artifacts of this kind are skipped.
    candidate = Path(str(resource_root))
    if not candidate.is_dir():
        return None
    return candidate


def _bundled_subdir(layer: str, subdir: str) -> Path | None:
    """``<layer root>/<subdir>`` for a bundled layer, or ``None`` when it has no such dir.

    ``layer`` is the engine or a bundled-plugin name (either namespace); an
    unknown plugin leaf resolves to ``None`` like a missing kind directory.
    Raises :class:`CatalogMissingError` when the catalog root is missing.

    Example::

        >>> _bundled_subdir("coding_agent_playbook", "rules")  # doctest: +SKIP
        PosixPath('/repo/catalog/core/rules')
    """
    layer_root = catalog_layer_root(layer)
    if layer_root is None:
        return None
    candidate = layer_root / subdir
    return candidate if candidate.is_dir() else None


def _iter_md_files(root: Path) -> Iterator[Path]:
    """Yield ``*.md`` and ``*.md.j2`` files under ``root`` in deterministic order."""
    for path in sorted(root.rglob("*.md*")):
        # Skip dotted directories (.git, .venv, node_modules-of-vendored-skills,
        # etc.) for hygiene — these never legitimately contain canonical
        # artifacts, and walking them silently inflates source listings.
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        # Note: case-sensitive on Linux/macOS APFS (lowercase .md convention).
        # Banking deployments on case-insensitive volumes may need to revisit.
        if path.name.endswith(".md") or path.name.endswith(".md.j2"):
            yield path


def _iter_skills(skills_root: Path, source_package: str) -> Iterator[Skill]:
    """Yield one ``Skill`` per subdirectory of ``skills_root`` (SPEC §6.3.1).

    Each skill directory must contain ``SKILL.md`` (or ``SKILL.md.j2``).
    ``scripts/`` and ``references/`` sibling subdirectories are recorded on
    the Skill if present.
    """
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        skill_md = _find_skill_md(skill_dir)
        if skill_md is None:
            continue
        text = skill_md.read_text(encoding="utf-8")
        frontmatter, body = split_frontmatter(text)
        scripts_dir = skill_dir / "scripts"
        references_dir = skill_dir / "references"
        yield Skill(
            frontmatter=frontmatter,
            body=body,
            scripts_dir=scripts_dir if scripts_dir.is_dir() else None,
            references_dir=references_dir if references_dir.is_dir() else None,
            source_package=source_package,
        )


def _find_skill_md(skill_dir: Path) -> Path | None:
    """Return ``SKILL.md`` or ``SKILL.md.j2`` inside ``skill_dir`` if it exists."""
    for candidate_name in ("SKILL.md", "SKILL.md.j2"):
        candidate = skill_dir / candidate_name
        if candidate.is_file():
            return candidate
    return None


class FileSystemArtifactSource(ArtifactSource):
    """Walks the engine's catalog (``catalog/core/`` and the enabled
    ``catalog/plugins/<name>/``, located by ``catalog.roots``), importlib.resources
    for overlay packages, plus <repo>/playbook/ for repo-local artifacts
    (SPEC §20.3, §11).

    ``extra_resource_roots`` adds ``resources/`` directories found by path
    rather than by package name — config-less ``playbook validate`` passes an
    overlay checkout's ``<root>/src/<pkg>/resources/`` (prK §P P8). Every
    walker, and validate's per-layer checks, go through :meth:`layer_roots`.
    """

    name = "filesystem"

    def __init__(
        self,
        *,
        repo_root: Path,
        engine_package: str = ENGINE_PACKAGE,
        overlay_packages: list[str] | None = None,
        extra_resource_roots: Sequence[Path] = (),
    ) -> None:
        self._repo_root = repo_root
        self._engine_package = engine_package
        self._overlay_packages = overlay_packages or []
        self._extra_resource_roots = tuple(extra_resource_roots)

    @property
    def engine_package(self) -> str:
        """Public read-only accessor for the engine package name.

        Callers that need to walk the same package set this source walks
        should prefer :meth:`layer_roots`; this and :attr:`overlay_packages`
        stay public so nobody reaches into the private ``_engine_package`` /
        ``_overlay_packages`` attributes, which a rename would silently degrade.
        """
        return self._engine_package

    @property
    def overlay_packages(self) -> tuple[str, ...]:
        """Public read-only accessor for the overlay package names.

        Returns a tuple (not the live list) so callers cannot mutate the
        source's internal package list. Order matches the walk order in
        :meth:`list_rules` / :meth:`list_prompts` / :meth:`list_eval_tasks`.
        """
        return tuple(self._overlay_packages)

    @property
    def extra_resource_roots(self) -> tuple[Path, ...]:
        """The path-based ``resources/`` layers, walked after the overlays."""
        return self._extra_resource_roots

    def layer_roots(self, subdir: str) -> list[tuple[str, Path]]:
        """``(source_package, <layer>/<subdir>)`` for each layer that has ``subdir``.

        Layers come in resolution order (later wins, SPEC §11): the engine
        package, the overlays in ``overlays_enabled`` order, the extra
        ``resources/`` roots, then repo-local ``playbook/``. The label is what
        artifacts found there carry as ``source_package``: the package name,
        the extra root's parent directory name, or ``"<repo-local>"``. A
        layer's containment root for links is ``root.parent``.

        Example::

            >>> FileSystemArtifactSource(repo_root=Path("/repo")).layer_roots("rules")[0][0]
            'coding_agent_playbook'
        """
        candidates: list[tuple[str, Path | None]] = [
            *((package, _resource_subdir(package, subdir)) for package in self._packages()),
            *((root.parent.name, root / subdir) for root in self._extra_resource_roots),
            (REPO_LOCAL_SOURCE, self._repo_root / "playbook" / subdir),
        ]
        return [(label, root) for label, root in candidates if root is not None and root.is_dir()]

    def _packages(self) -> tuple[str, ...]:
        """The importable layers: the engine package, then the overlays."""
        return (self._engine_package, *self._overlay_packages)

    def list_rules(self) -> list[Rule]:
        return self._walk_artifacts(
            subdir="rules",
            builder=Rule.from_markdown,
        )

    def list_prompts(self) -> list[Prompt]:
        return self._walk_artifacts(
            subdir="prompts",
            builder=Prompt.from_markdown,
        )

    def list_skills(self) -> list[Skill]:
        return [
            skill
            for label, root in self.layer_roots("skills")
            for skill in _iter_skills(root, label)
        ]

    def list_hooks(self) -> list[Hook]:
        """Every hook directory of every layer, in :meth:`layer_roots` order (prK §A.5).

        Fails loudly, like ``Rule.from_markdown``: raises the first
        :class:`~coding_agent_playbook.artifacts.hook_schema.HookSchemaError` that
        :meth:`collect_hooks` finds.
        """
        hooks, errors = self.collect_hooks()
        if errors:
            raise errors[0]
        return hooks

    def collect_hooks(self) -> tuple[list[Hook], list[HookSchemaError]]:
        """Every well-formed hook plus every malformed one's error, never raising.

        What ``SyncContext.from_repo(..., tolerate_hook_errors=True)`` reads, so
        ``playbook validate`` reports each malformed hook (prK §P P8c).

        Example::

            >>> FileSystemArtifactSource(repo_root=Path("/no/such/repo")).collect_hooks()
            ([], [])
        """
        walks = [walk_hook_layer(root, label) for label, root in self.layer_roots("hooks")]
        return [h for walk in walks for h in walk.hooks], [e for walk in walks for e in walk.errors]

    def _walk_artifacts(
        self,
        *,
        subdir: str,
        builder: Callable[[Path, str], _T],
    ) -> list[_T]:
        return [
            builder(md, label)
            for label, root in self.layer_roots(subdir)
            for md in _iter_md_files(root)
        ]

    def list_eval_tasks(self) -> list[EvalTask]:
        """Walk every layer's ``eval_tasks/<id>/`` (:meth:`layer_roots` order).

        Each layer's ``eval_tasks/`` (``catalog/core/eval_tasks/`` for the
        engine, ``catalog/plugins/<name>/eval_tasks/`` for a bundled plugin,
        ``<pkg>/resources/eval_tasks/`` for an overlay package, then
        ``<repo>/playbook/eval_tasks/``). Later layers do NOT override earlier
        ones here — the orchestrator's :class:`OverlayResolver` handles ID-based
        collision semantics for rules/prompts/skills, but eval tasks are
        aggregated as-is in v1 (no per-layer override pass yet; the
        collision-by-id pattern is identical and lands when first overlay ships
        eval tasks). Each task's ``source_package`` is its layer's label (the
        engine package, a bundled-plugin or overlay-package name, or
        ``"<repo-local>"``).
        """
        return [
            load_eval_task_from_dir(task_dir, source_package=label)
            for label, root in self.layer_roots("eval_tasks")
            for task_dir in discover_eval_task_dirs(root)
        ]
