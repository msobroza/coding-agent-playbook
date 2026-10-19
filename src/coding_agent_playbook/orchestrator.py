"""Sync orchestration: glue between sources, renderer, and adapters.

This module exposes the data structure and helpers that the per-subcommand
modules in ``coding_agent_playbook.commands`` consume. The pieces here:

- :class:`SyncContext` — the bundle of (config, facts, source, adapters,
  resolved artifacts) handed to every command.
- :class:`OverlayResolver` — three-layer merge per SPEC §11 (engine, overlays,
  repo-local). Records collisions for ``playbook check``; hooks merge through
  the additive ``hook_policy.merge_hook_layers`` (specs/prK-lifecycle-hooks.md §A.6).
- :func:`discover_adapters` — entry-point discovery + always-enable
  ``agents_md``.

The rule registry that prompts include rules through lives in
:mod:`coding_agent_playbook.rule_registry`, which imports
:func:`template_source` from here; this module never imports it back.

PR 10's invariants:
  - The orchestrator never instantiates an adapter directly; everything goes
    through ``[project.entry-points."coding_agent_playbook.adapters"]``.
  - ``rules_resolved`` etc. are post-overlay-merge but pre-applies_if-filter.
    Filtering happens inside the commands so each command can pick its own
    semantics (sync filters; render does not; check shows both sides).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from importlib import metadata
from typing import TYPE_CHECKING

from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE
from coding_agent_playbook.catalog.roots import canonical_overlay_name
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.config.tables.hooks import PolicyTables
from coding_agent_playbook.detector.facts import detect
from coding_agent_playbook.hook_policy import (
    NO_HANDLER_SCHEMAS,
    RegistryCatalog,
    merge_hook_layers,
    split_hook_layers,
)

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.hook_schema import HookSchemaError
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.catalog.source import ArtifactSource
    from coding_agent_playbook.config.files import StateSource
    from coding_agent_playbook.config.model import Config
    from coding_agent_playbook.detector.facts import Facts
    from coding_agent_playbook.hook_policy import (
        ConfigSchemaLookup,
        HookLayerMerger,
        HookViolation,
    )
    from coding_agent_playbook.renderer import RuleRegistry


@dataclass(frozen=True)
class Collision:
    """One overlay collision recorded by :class:`OverlayResolver`.

    ``kind`` is one of ``"rule"``, ``"prompt"``, ``"skill"``, ``"hook"``;
    ``artifact_id`` is the conflicting ID; ``winner`` and ``losers`` are the
    source package names (e.g. ``"coding_agent_playbook"``, ``"<repo-local>"``).
    A hook's winner is the merged definition's layer, which a refused
    override (H2, H15) leaves earlier than the last one.
    """

    kind: str
    artifact_id: str
    winner: str
    losers: tuple[str, ...]


class OverlayResolver:
    """Merge engine + overlay + repo-local artifact lists by ID (SPEC §11).

    Resolution order (later wins on ID collision):
      1. Engine artifacts (the bundled ``catalog/core/``).
      2. Each overlay package or bundled plugin, in ``config.overlays_enabled`` order.
      3. Repo-local artifacts under ``<repo>/playbook/``.

    For each ``(kind, id)`` pair the winner is kept; losers are recorded for
    ``playbook check`` and ``playbook render --show-source``. Hooks instead
    merge every definition of an id (:meth:`resolve_hooks`); ``merge_hooks``
    and ``hook_schemas`` are injectable so tests can spy on that merge.
    """

    def __init__(
        self,
        *,
        hook_schemas: ConfigSchemaLookup = NO_HANDLER_SCHEMAS,
        merge_hooks: HookLayerMerger = merge_hook_layers,
    ) -> None:
        self._collisions: list[Collision] = []
        self._hook_schemas = hook_schemas
        self._merge_hooks = merge_hooks
        self._hook_violations: list[HookViolation] = []
        self._hook_definitions: dict[str, tuple[Hook, ...]] = {}

    @property
    def collisions(self) -> list[Collision]:
        return list(self._collisions)

    @property
    def hook_violations(self) -> list[HookViolation]:
        """Every refused hook override (H2, H14, H15), in resolution order."""
        return list(self._hook_violations)

    @property
    def hook_definitions(self) -> dict[str, tuple[Hook, ...]]:
        """Every layer's definition of each hook id, in layer order (validate's H12)."""
        return dict(self._hook_definitions)

    def resolve_rules(
        self,
        engine: list[Rule],
        overlays: list[list[Rule]],
        repo_local: list[Rule],
    ) -> list[Rule]:
        return self._resolve("rule", engine, overlays, repo_local)

    def resolve_prompts(
        self,
        engine: list[Prompt],
        overlays: list[list[Prompt]],
        repo_local: list[Prompt],
    ) -> list[Prompt]:
        return self._resolve("prompt", engine, overlays, repo_local)

    def resolve_skills(
        self,
        engine: list[Skill],
        overlays: list[list[Skill]],
        repo_local: list[Skill],
    ) -> list[Skill]:
        return self._resolve("skill", engine, overlays, repo_local)

    def resolve_hooks(
        self,
        engine: list[Hook],
        overlays: list[list[Hook]],
        repo_local: list[Hook],
    ) -> list[Hook]:
        """Merge each hook id across every layer (§A.6); never raises for a violation.

        Unlike :meth:`_resolve`, which keeps only the winner, every definition
        of an id goes to the layer merge, because the additive policy compares
        each override with what it overrides. Violations land on
        :attr:`hook_violations`; ids defined more than once record a
        ``Collision(kind="hook")``.

        Example::

            >>> OverlayResolver().resolve_hooks([engine_hook], [[overlay_hook]], [])  # doctest: +SKIP
            [Hook(...)]
        """
        by_id: dict[str, list[Hook]] = {}
        for layer in (engine, *overlays, repo_local):
            for hook in layer:
                by_id.setdefault(hook.frontmatter.id, []).append(hook)
        resolved: list[Hook] = []
        for hook_id, definitions in by_id.items():
            merged, violations = self._merge_hooks(definitions, schemas=self._hook_schemas)
            self._hook_definitions[hook_id] = tuple(definitions)
            self._hook_violations.extend(violations)
            if len(definitions) > 1:
                self._collisions.append(_hook_collision(hook_id, merged, definitions))
            resolved.append(merged)
        return resolved

    def _resolve[T](
        self,
        kind: str,
        engine: list[T],
        overlays: list[list[T]],
        repo_local: list[T],
    ) -> list[T]:
        winners: dict[str, T] = {}
        loser_log: dict[str, list[str]] = {}
        # Flatten the layers in priority-ascending order; later layers win.
        layers: list[list[T]] = [engine, *overlays, repo_local]
        for layer in layers:
            for artifact in layer:
                artifact_id = artifact_id_of(artifact)
                if artifact_id in winners:
                    previous = winners[artifact_id]
                    loser_log.setdefault(artifact_id, []).append(_source_package(previous))
                winners[artifact_id] = artifact
        # Stable order: engine, overlays, repo-local — preserved by dict insertion.
        for artifact_id, losers in loser_log.items():
            self._collisions.append(
                Collision(
                    kind=kind,
                    artifact_id=artifact_id,
                    winner=_source_package(winners[artifact_id]),
                    losers=tuple(losers),
                )
            )
        return list(winners.values())


def _hook_collision(hook_id: str, merged: Hook, definitions: list[Hook]) -> Collision:
    """The merged definition's layer wins; every other definition's layer lost."""
    losers = [hook.source_package for hook in definitions]
    if merged.source_package in losers:  # an injected merger may return any layer
        losers.remove(merged.source_package)
    return Collision("hook", hook_id, merged.source_package, tuple(losers))


def artifact_id_of(artifact: object) -> str:
    """Return the artifact's ID for collision tracking and provenance lookups.

    Rules/Prompts carry a dataclass frontmatter (``frontmatter.id``); Skills
    carry an open dict (``frontmatter["id"]``). Skills without an explicit id
    fall back to ``"skill"`` to mirror :meth:`Skill.to_prompt`'s behaviour.

    Public helper (no underscore) — ``commands/render.py`` reuses it when
    looking up overlay collisions by ID.
    """
    frontmatter = artifact.frontmatter  # type: ignore[attr-defined]
    if hasattr(frontmatter, "id"):
        return str(frontmatter.id)
    if isinstance(frontmatter, dict):
        return str(frontmatter.get("id", "skill"))
    raise TypeError(f"cannot extract id from artifact {artifact!r}")


def _source_package(artifact: object) -> str:
    package = getattr(artifact, "source_package", None)
    return str(package) if package is not None else "<unknown>"


def template_source(artifact: Rule | Prompt) -> str:
    """Name ``artifact``'s template in error messages: its source path, else its id.

    Example: ``template_source(rule)`` -> ``"/repo/playbook/rules/x.md.j2"``.
    """
    path = artifact.source_path
    return str(path) if path is not None else artifact_id_of(artifact)


def discover_adapters(
    config: Config,
    *,
    rule_registry: RuleRegistry | None = None,
) -> dict[str, Adapter]:
    """Discover enabled adapters via the ``coding_agent_playbook.adapters``
    entry-point group.

    The returned mapping is ``name -> instance``. ``agents_md`` is always
    included (SPEC §4.3). Adapters that accept ``rule_registry`` get it; those
    that don't (currently ``agents_md`` and ``shared_skills``) are constructed
    with no arguments. The ``TypeError`` fallback is the canonical idiom for handling
    the two adapter signatures uniformly.
    """
    eps = metadata.entry_points(group="coding_agent_playbook.adapters")
    enabled = set(config.adapters_enabled) | {"agents_md"}
    discovered: dict[str, Adapter] = {}
    for ep in eps:
        if ep.name not in enabled:
            continue
        cls = ep.load()
        try:
            discovered[ep.name] = cls(rule_registry=rule_registry)
        except TypeError:
            discovered[ep.name] = cls()
    return discovered


def installed_output_locations() -> tuple[str, ...]:
    """Every current and retired output location of an installed adapter, enabled or not.

    Disabled adapters count: their earlier output is exactly what ``playbook
    sync`` must still be able to clean up (SPEC §4.2 step 9). So do retired
    locations (``retired_output_locations``, e.g. the pre-v0.21 ``shared_skills/``):
    the first sync after an upgrade settles the tree an older engine wrote. An
    adapter whose entry point fails to load declares nothing, so its output is
    never deleted.

    Example::

        >>> "shared_skills/" in installed_output_locations()  # doctest: +SKIP
        True
    """
    locations: list[str] = []
    for ep in metadata.entry_points(group="coding_agent_playbook.adapters"):
        try:
            cls = ep.load()
        except (ImportError, AttributeError):
            continue
        locations.extend(getattr(cls, "output_locations", ()))
        locations.extend(getattr(cls, "retired_output_locations", ()))
    return tuple(locations)


def _warn_deprecated_overlays(config: Config, state: FileSystemStateSource) -> None:
    """Print one stderr ``warning:`` per distinct deprecated overlay name (SPEC v0.19).

    The line names the file to fix: the local file when it sets
    ``overlays_enabled`` (lists replace whole in the SPEC §7.2 merge), else the
    committed one. A print, not ``warnings.warn``: CLI users never see a
    ``DeprecationWarning``, and pytest runs with ``filterwarnings = error``.
    Called only from :meth:`SyncContext.from_repo`, so a directly built
    ``SyncContext`` (or ``Config``) stays silent.

    Example::

        >>> _warn_deprecated_overlays(config, state)  # doctest: +SKIP
        warning: <file>: overlays_enabled: '<old>' is deprecated; use '<new>'
    """
    if not config.deprecated_overlay_names:
        return
    local_sets_list = "overlays_enabled" in state.load_local_overrides()
    source = state._CONFIG_LOCAL_FILENAME if local_sets_list else state._CONFIG_FILENAME
    # Listed twice, a name is walked twice (canonical_overlay_list keeps it), but warned once.
    for old in dict.fromkeys(config.deprecated_overlay_names):
        print(
            f"warning: {source}: overlays_enabled: '{old}' is deprecated; "
            f"use '{canonical_overlay_name(old)}'",
            file=sys.stderr,
        )


@dataclass
class SyncContext:
    """Bundle of state every CLI command needs after reading the config.

    ``rules_resolved``, ``prompts_resolved``, ``skills_resolved`` and
    ``hooks_resolved`` are post-overlay-merge but pre-applies_if-filter —
    filtering is the command's responsibility (sync filters; render does not).
    ``hook_load_errors`` holds the malformed hooks that ``tolerate_hook_errors``
    set aside; ``hook_violations`` the refused layer overrides (prK §A.5, §A.6).
    ``policy_tables`` holds the committed ``[hooks]`` / ``[guardrails]`` tables,
    raw so validate can report a malformed one (H21); read hooks policy there,
    never from ``config.extra_tables``, which merges ``.local.toml`` in (§B.1).
    """

    repo_root: Path
    config: Config
    facts: Facts
    artifact_source: ArtifactSource
    state_source: StateSource
    adapters: dict[str, Adapter] = field(default_factory=dict)
    rules_resolved: list[Rule] = field(default_factory=list)
    prompts_resolved: list[Prompt] = field(default_factory=list)
    skills_resolved: list[Skill] = field(default_factory=list)
    overlay_collisions: list[Collision] = field(default_factory=list)
    hooks_resolved: list[Hook] = field(default_factory=list)
    hook_definitions: dict[str, tuple[Hook, ...]] = field(default_factory=dict)
    hook_load_errors: list[HookSchemaError] = field(default_factory=list)
    hook_violations: list[HookViolation] = field(default_factory=list)
    policy_tables: PolicyTables = field(default_factory=PolicyTables)

    @classmethod
    def from_repo(
        cls,
        repo_root: Path,
        *,
        rule_registry: RuleRegistry | None = None,
        tolerate_hook_errors: bool = False,
        warn_deprecated: bool = True,
    ) -> SyncContext:
        """Discovery: load config → detect facts → instantiate sources → resolve overlays.

        ``rule_registry`` is optional because the adapters need it but the
        registry itself depends on the filtered rule list, which depends on
        facts. Callers that want the full pipeline build the context once
        without a registry, then re-build the adapters via
        :func:`discover_adapters` after the registry exists.

        A malformed hook raises ``HookSchemaError`` (sync, check, render and
        eval fail loudly); ``tolerate_hook_errors=True`` records each one on
        ``hook_load_errors`` instead, so ``playbook validate`` can report them
        all (prK §P P8c).

        Prints one ``warning:`` line per deprecated ``coding_agent_playbook.packs.*``
        overlay name, before anything else runs (:func:`_warn_deprecated_overlays`).
        ``warn_deprecated=False`` is for an internal re-read inside a command that
        already built its own context (the hook twins' policy read during
        ``init``), so the user sees each warning once.
        """
        state_source = FileSystemStateSource(repo_root=repo_root)
        config = state_source.load_config()
        if warn_deprecated:
            _warn_deprecated_overlays(config, state_source)
        return cls.from_config(
            repo_root,
            config,
            rule_registry=rule_registry,
            tolerate_hook_errors=tolerate_hook_errors,
            policy_tables=state_source.load_policy_tables(),
        )

    @classmethod
    def from_config(
        cls,
        repo_root: Path,
        config: Config,
        *,
        artifact_source: ArtifactSource | None = None,
        rule_registry: RuleRegistry | None = None,
        tolerate_hook_errors: bool = False,
        policy_tables: PolicyTables | None = None,
    ) -> SyncContext:
        """:meth:`from_repo` minus the config load: detect → walk → resolve overlays.

        Config-less ``playbook validate`` passes a stand-in ``config`` and an
        ``artifact_source`` with extra checkout layers (prK §P P8); by default
        the source walks the engine, ``config.overlays_enabled`` and
        ``<repo>/playbook/``. Without ``policy_tables`` there is no ``[hooks]``
        table, so hooks are off.

        Example::

            >>> SyncContext.from_config(repo, config).rules_resolved  # doctest: +SKIP
            [Rule(...), ...]
        """
        facts = detect(repo_root)
        if artifact_source is None:
            artifact_source = FileSystemArtifactSource(
                repo_root=repo_root,
                overlay_packages=list(config.overlays_enabled),
            )
        # FileSystemArtifactSource walks the engine and bundled-plugin artifacts
        # in the catalog (``catalog/core/``, ``catalog/plugins/<name>/``)
        # and each overlay package's ``resources/`` tree via importlib.resources;
        # repo-local artifacts come from ``<repo>/playbook/``. v1 walks all of
        # those in a single ``list_*`` call — sufficient for PR 10. PRs 13+
        # may split per-layer if we need fine-grained source provenance.
        resolver = OverlayResolver(hook_schemas=RegistryCatalog())  # handlers' CONFIG_SCHEMA
        all_rules = artifact_source.list_rules()
        all_prompts = artifact_source.list_prompts()
        all_skills = artifact_source.list_skills()
        # TODO(PR-13): the OverlayResolver supports per-layer wiring
        # (engine, overlays, repo-local) for the three-layer merge in
        # SPEC §11, but ``FileSystemArtifactSource`` currently returns a
        # single flattened list across all sources.
        # v1: source already flattened; per-layer wiring lands when the first
        # overlay package needs it. See SPEC §11 for layer order.
        # ID collisions across the merged list still flag winners vs losers
        # via insertion-order semantics, which is enough for the engine-only
        # v1 we ship today.
        rules_resolved = resolver.resolve_rules(all_rules, [], [])
        prompts_resolved = resolver.resolve_prompts(all_prompts, [], [])
        skills_resolved = resolver.resolve_skills(all_skills, [], [])
        hooks_resolved, hook_load_errors = _resolve_hooks(
            artifact_source, resolver, tolerate=tolerate_hook_errors
        )

        adapters = discover_adapters(config, rule_registry=rule_registry)

        return cls(
            repo_root=repo_root,
            config=config,
            facts=facts,
            artifact_source=artifact_source,
            state_source=FileSystemStateSource(repo_root=repo_root),
            adapters=adapters,
            rules_resolved=rules_resolved,
            prompts_resolved=prompts_resolved,
            skills_resolved=skills_resolved,
            overlay_collisions=resolver.collisions,
            hooks_resolved=hooks_resolved,
            hook_definitions=resolver.hook_definitions,
            hook_load_errors=hook_load_errors,
            hook_violations=resolver.hook_violations,
            policy_tables=PolicyTables() if policy_tables is None else policy_tables,
        )


def _resolve_hooks(
    source: ArtifactSource, resolver: OverlayResolver, *, tolerate: bool
) -> tuple[list[Hook], list[HookSchemaError]]:
    """Merge ``source``'s hooks layer by layer; return them and the load errors.

    Unlike the other kinds, hooks need real layers, because the additive merge
    treats an overlay and a repo-local override differently (§A.6). A malformed
    hook raises unless ``tolerate`` records it (P8c).
    """
    hooks, errors = source.collect_hooks() if tolerate else (source.list_hooks(), [])
    layers = split_hook_layers(hooks, engine_package=engine_package_of(source))
    return resolver.resolve_hooks(*layers), errors


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
