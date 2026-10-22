"""The ArtifactSource ABC and its filesystem implementation (SPEC.md §20.2, §20.3).

Third-party sources register via the ``coding_agent_playbook.artifact_sources``
entry point declared in ``pyproject.toml``. The filesystem source is the v1
implementation. It depends only on stdlib (pathlib, importlib.resources,
importlib.metadata) plus pyyaml for the helpers in ``artifacts/frontmatter.py``.
The StateSource ABC and FileSystemStateSource live in ``config/files.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter

# A stdlib-only package module, so this stays a light import.
from coding_agent_playbook.artifacts.hook_schema import HookSchemaError
from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.artifacts.rule import Rule, RuleLoadError
from coding_agent_playbook.artifacts.skill import Skill, side_dirs_at
from coding_agent_playbook.catalog._hook_walk import walk_hook_layer
from coding_agent_playbook.catalog._skill_rules import (
    iter_md_files,
    iter_skill_dirs,
    iter_skill_rule_files,
)
from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE, REPO_LOCAL_SOURCE
from coding_agent_playbook.catalog.prompt_sets import (
    DEFAULT_PROMPT_SET,
    LATER_PROMPT_SETS,
    PromptSet,
    prompt_set_dir,
    prompt_set_dirs,
    require_prompt_set,
)
from coding_agent_playbook.catalog.roots import catalog_layer_root, is_bundled_layer
from coding_agent_playbook.evals.loader import (
    discover_eval_sample_dirs,
    load_eval_sample_from_dir,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.evals.sample import EvalSample


@dataclass(frozen=True)
class PromptSetLayer:
    """One layer's later prompt set beside its v1 prompts (D76), for ``playbook validate``.

    ``rendered`` says whether the source's :meth:`ArtifactSource.list_prompts`
    returns this set; :attr:`unrendered` is what it leaves out.

    Example::

        >>> PromptSetLayer("v2", Path("prompts/v2"), (), (), rendered=False).unrendered
        ()
    """

    prompt_set: PromptSet
    set_dir: Path
    v1: tuple[Prompt, ...]
    twins: tuple[Prompt, ...]
    rendered: bool

    @property
    def unrendered(self) -> tuple[Prompt, ...]:
        """The layer's prompts a sync does not render: the twins, or the v1 prompts they replace.

        Example::

            >>> PromptSetLayer("v2", Path("prompts/v2"), (), (), rendered=True).unrendered
            ()
        """
        if not self.rendered:
            return self.twins
        twin_ids = {twin.frontmatter.id for twin in self.twins}
        return tuple(prompt for prompt in self.v1 if prompt.frontmatter.id in twin_ids)


class ArtifactSource(ABC):
    """Where rules, prompts, skills, hooks, and eval samples come from."""

    name: str

    @abstractmethod
    def list_rules(self) -> list[Rule]: ...

    def collect_rules(self) -> tuple[list[Rule], list[RuleLoadError]]:
        """Every well-formed rule plus the errors of malformed ones, never raising.

        What ``playbook validate`` reads, so it can report every malformed rule
        file (prU D21), mirroring :meth:`collect_hooks`. This default can only
        record the one error a failing :meth:`list_rules` raises; a source that
        sees each file overrides it.

        Example::

            >>> rules, errors = source.collect_rules()  # doctest: +SKIP
        """
        try:
            return self.list_rules(), []
        except RuleLoadError as exc:
            return [], [exc]

    @abstractmethod
    def list_prompts(self) -> list[Prompt]: ...

    def prompt_set_layers(self) -> list[PromptSetLayer]:
        """Each layer's later prompt set that has prompts (D76); ``[]`` by default.

        Concrete, returning ``[]``: a source without prompt sets has no twins to
        check, and a third-party source written before them still instantiates.

        Example::

            >>> source.prompt_set_layers()  # doctest: +SKIP
            []
        """
        return []

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
    def list_eval_samples(self) -> list[EvalSample]: ...


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


def _iter_skills(skills_root: Path, source_package: str) -> Iterator[Skill]:
    """Yield one ``Skill`` per subdirectory of ``skills_root`` (SPEC §6.3.1).

    Each skill directory must contain ``SKILL.md`` (or ``SKILL.md.j2``).
    ``scripts/``, ``references/`` and ``examples/`` (prU D48) sibling
    subdirectories are recorded on the Skill if present. A ``rules/``
    subdirectory is not: its files are rules, which
    :meth:`FileSystemArtifactSource.collect_rules` loads as members of this
    skill (prU D5), never byte-copied.
    """
    for skill_dir, skill_md in iter_skill_dirs(skills_root):
        text = skill_md.read_text(encoding="utf-8")
        frontmatter, body = split_frontmatter(text)
        yield Skill(
            frontmatter=frontmatter,
            body=body,
            source_package=source_package,
            source_dir=skill_dir,
            **side_dirs_at(skill_dir),
        )


def layer_prompts(prompts_root: Path, label: str, prompt_set: PromptSet) -> list[Prompt]:
    """One layer's prompts in ``prompt_set``: its v1 prompts, each replaced by its twin.

    The v1 set is every prompt under ``prompts_root`` outside the later sets'
    directories. For another set, a v1 prompt whose id has a twin in that set's
    directory takes the twin; the others keep their v1 text, so the ids, and
    their order, never change (D76). A twin with no v1 prompt is left out here;
    ``playbook validate`` reports it.

    Example::

        >>> layer_prompts(Path("catalog/core/prompts"), "coding_agent_playbook", "v2")  # doctest: +SKIP
        [Prompt(...), ...]
    """
    v1 = [
        Prompt.from_markdown(md, label)
        for md in iter_md_files(prompts_root, skip=prompt_set_dirs(prompts_root))
    ]
    if prompt_set == DEFAULT_PROMPT_SET:
        return v1
    twins = {
        twin.frontmatter.id: twin for twin in prompt_set_prompts(prompts_root, label, prompt_set)
    }
    return [twins.get(prompt.frontmatter.id, prompt) for prompt in v1]


def prompt_set_prompts(prompts_root: Path, label: str, prompt_set: PromptSet) -> list[Prompt]:
    """The prompts in ``prompt_set``'s own directory of one layer (``[]`` when it has none).

    Example::

        >>> prompt_set_prompts(Path("/no/such/prompts"), "x", "v2")
        []
    """
    set_root = prompt_set_dir(prompts_root, prompt_set)
    if not set_root.is_dir():
        return []
    return [Prompt.from_markdown(md, label) for md in iter_md_files(set_root)]


def _load_rule_or_error(
    path: Path, source_package: str, home_skill: str | None
) -> Rule | RuleLoadError:
    """The rule at ``path``, or the :class:`RuleLoadError` it raised (for collect_rules).

    ``home_skill`` is the skill whose ``rules/`` holds the file, or ``None``
    for a ``<layer>/rules/`` file.
    """
    try:
        return Rule.from_markdown(path, source_package, home_skill=home_skill)
    except RuleLoadError as exc:
        return exc


def _layer_rule_files(
    rules_root: Path | None, skills_root: Path | None
) -> Iterator[tuple[str | None, Path]]:
    """One layer's rule files: ``rules/`` first, then ``skills/*/rules/`` with each home skill."""
    if rules_root is not None and rules_root.is_dir():
        yield from ((None, path) for path in iter_md_files(rules_root))
    if skills_root is not None and skills_root.is_dir():
        yield from iter_skill_rule_files(skills_root)


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
        prompt_set: PromptSet = DEFAULT_PROMPT_SET,
    ) -> None:
        self._repo_root = repo_root
        self._engine_package = engine_package
        self._overlay_packages = overlay_packages or []
        self._extra_resource_roots = tuple(extra_resource_roots)
        self._prompt_set = require_prompt_set(prompt_set)

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
        :meth:`list_rules` / :meth:`list_prompts` / :meth:`list_eval_samples`.
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
        return [
            (label, root)
            for label, (root,) in self._layer_candidates(subdir)
            if root is not None and root.is_dir()
        ]

    def _layer_candidates(self, *subdirs: str) -> list[tuple[str, tuple[Path | None, ...]]]:
        """Every layer's ``(label, (<layer>/<subdir> or None for each of subdirs))``.

        One row per layer, so several kinds of one layer travel together
        (:meth:`collect_rules` reads ``rules`` and ``skills`` from one row).

        Example: ``source._layer_candidates("rules", "skills")[-1][0]`` -> ``"<repo-local>"``.
        """
        repo_local = self._repo_root / "playbook"
        return [
            *(
                (package, tuple(_resource_subdir(package, subdir) for subdir in subdirs))
                for package in self._packages()
            ),
            *(
                (root.parent.name, tuple(root / subdir for subdir in subdirs))
                for root in self._extra_resource_roots
            ),
            (REPO_LOCAL_SOURCE, tuple(repo_local / subdir for subdir in subdirs)),
        ]

    def _packages(self) -> tuple[str, ...]:
        """The importable layers: the engine package, then the overlays."""
        return (self._engine_package, *self._overlay_packages)

    def list_rules(self) -> list[Rule]:
        """Every rule of every layer, raising the first :class:`RuleLoadError` found."""
        rules, errors = self.collect_rules()
        if errors:
            raise errors[0]
        return rules

    def collect_rules(self) -> tuple[list[Rule], list[RuleLoadError]]:
        """Every well-formed rule plus one error per malformed rule file, never raising.

        Layers come in :meth:`layer_roots` order; inside a layer, ``<layer>/rules/``
        first, then each skill's ``<layer>/skills/<dir>/rules/`` (prU D5). A rule
        found in a skill's ``rules/`` is a member of that skill: its
        ``home_skill`` is the skill's id, which also fills ``skill`` when the file
        leaves it out. Later layers still override earlier ones by id.

        Example::

            >>> FileSystemArtifactSource(repo_root=Path("/no/such/repo")).collect_rules()[1]
            []
        """
        loaded = [
            _load_rule_or_error(path, label, home)
            for label, (rules_root, skills_root) in self._layer_candidates("rules", "skills")
            for home, path in _layer_rule_files(rules_root, skills_root)
        ]
        rules = [item for item in loaded if isinstance(item, Rule)]
        return rules, [item for item in loaded if isinstance(item, RuleLoadError)]

    @property
    def prompt_set(self) -> PromptSet:
        """The prompt set :meth:`list_prompts` returns (D76; ``Config.prompt_set``)."""
        return self._prompt_set

    def list_prompts(self) -> list[Prompt]:
        """Every layer's prompts in :attr:`prompt_set` (:func:`layer_prompts`), layer by layer.

        Example::

            >>> FileSystemArtifactSource(repo_root=Path("/no/such/repo")).list_prompts()  # doctest: +SKIP
            [Prompt(...), ...]
        """
        return [
            prompt
            for label, root in self.layer_roots("prompts")
            for prompt in layer_prompts(root, label, self._prompt_set)
        ]

    def prompt_set_layers(self) -> list[PromptSetLayer]:
        """Each layer's ``prompts/<set>/`` that holds prompts, with that layer's v1 prompts.

        Example::

            >>> FileSystemArtifactSource(repo_root=Path("/no/such/repo")).prompt_set_layers()  # doctest: +SKIP
            []
        """
        layers = []
        for label, root in self.layer_roots("prompts"):
            for prompt_set in LATER_PROMPT_SETS:
                twins = prompt_set_prompts(root, label, prompt_set)
                if not twins:
                    continue
                layers.append(
                    PromptSetLayer(
                        prompt_set=prompt_set,
                        set_dir=prompt_set_dir(root, prompt_set),
                        v1=tuple(layer_prompts(root, label, DEFAULT_PROMPT_SET)),
                        twins=tuple(twins),
                        rendered=prompt_set == self._prompt_set,
                    )
                )
        return layers

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

        What ``SyncContext.from_repo(..., tolerate_load_errors=True)`` reads, so
        ``playbook validate`` reports each malformed hook (prK §P P8c).

        Example::

            >>> FileSystemArtifactSource(repo_root=Path("/no/such/repo")).collect_hooks()
            ([], [])
        """
        walks = [walk_hook_layer(root, label) for label, root in self.layer_roots("hooks")]
        return [h for walk in walks for h in walk.hooks], [e for walk in walks for e in walk.errors]

    def list_eval_samples(self) -> list[EvalSample]:
        """Walk every layer's ``eval_samples/<id>/`` (:meth:`layer_roots` order).

        Each layer's ``eval_samples/`` (``catalog/core/eval_samples/`` for the
        engine, ``catalog/plugins/<name>/eval_samples/`` for a bundled plugin,
        ``<pkg>/resources/eval_samples/`` for an overlay package, then
        ``<repo>/playbook/eval_samples/``). Later layers do NOT override earlier
        ones here — ``catalog.resolve``'s :class:`OverlayResolver` handles ID-based
        collision semantics for rules/prompts/skills, but eval samples are
        aggregated as-is in v1 (no per-layer override pass yet; the
        collision-by-id pattern is identical and lands when first overlay ships
        eval samples). Each sample's ``source_package`` is its layer's label (the
        engine package, a bundled-plugin or overlay-package name, or
        ``"<repo-local>"``).
        """
        return [
            load_eval_sample_from_dir(sample_dir, source_package=label)
            for label, root in self.layer_roots("eval_samples")
            for sample_dir in discover_eval_sample_dirs(root)
        ]


def engine_package_of(source: ArtifactSource) -> str:
    """The ``source_package`` of ``source``'s engine layer; hooks from it are engine-sourced.

    A filesystem source can be pointed at another engine package (tests do);
    any other source is assumed to serve the real one.

    Example::

        >>> engine_package_of(FileSystemArtifactSource(repo_root=Path(".")))  # doctest: +SKIP
        'coding_agent_playbook'
    """
    if isinstance(source, FileSystemArtifactSource):
        return source.engine_package
    return ENGINE_PACKAGE
