"""Sync orchestration: glue between sources, renderer, and adapters.

This module exposes the data structure and helpers that the per-subcommand
modules in ``coding_agent_playbook.commands`` consume. The pieces here:

- :class:`SyncContext` — the bundle of (config, facts, source, adapters,
  resolved artifacts) handed to every command.
- :class:`OverlayResolver` — three-layer merge per SPEC §11 (engine, overlays,
  repo-local). Records collisions for ``playbook check``; hooks merge through
  the additive ``hook_policy.merge_hook_layers`` (specs/prK-lifecycle-hooks.md §A.6).
- :class:`RuleRegistryImpl` — concrete ``RuleRegistry`` from the renderer
  Protocol. Built once per sync from the applies_if-filtered rule list.
- :func:`discover_adapters` — entry-point discovery + always-enable
  ``agents_md``.

PR 10's invariants:
  - The orchestrator never instantiates an adapter directly; everything goes
    through ``[project.entry-points."coding_agent_playbook.adapters"]``.
  - ``rules_resolved`` etc. are post-overlay-merge but pre-applies_if-filter.
    Filtering happens inside the commands so each command can pick its own
    semantics (sync filters; render does not; check shows both sides).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import metadata
from typing import TYPE_CHECKING

from coding_agent_playbook.detector import detect
from coding_agent_playbook.hook_policy import (
    NO_HANDLER_SCHEMAS,
    merge_hook_layers,
    split_hook_layers,
)
from coding_agent_playbook.renderer import render_sandboxed
from coding_agent_playbook.sources.filesystem import (
    ENGINE_PACKAGE,
    FileSystemArtifactSource,
    FileSystemStateSource,
)

if TYPE_CHECKING:
    from pathlib import Path

    from jinja2 import Environment

    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.config import Config
    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.hook_policy import (
        ConfigSchemaLookup,
        HookLayerMerger,
        HookViolation,
    )
    from coding_agent_playbook.renderer import RuleRegistry
    from coding_agent_playbook.sources.base import ArtifactSource, StateSource
    from coding_agent_playbook.types import Hook, HookSchemaError, Prompt, Rule, Skill


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
      1. Engine package artifacts (``coding_agent_playbook.resources.rules/*``).
      2. Each overlay package in ``config.overlays_enabled`` order.
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


class RuleRegistryImpl:
    """Concrete :class:`RuleRegistry` used by the orchestrator.

    Built once per sync from the merged + applies_if-filtered rule list. The
    ``render_for_inclusion`` method returns the inline body for a rule (with
    ``### {rule.name}`` header) or ``""`` when the rule is filtered out — the
    silent-omission contract from SPEC §6.2.5.
    """

    def __init__(self, rules: list[Rule], facts: Facts, env: Environment) -> None:
        self._by_id = {rule.frontmatter.id: rule for rule in rules}
        self._facts = facts
        self._env = env

    def render_for_inclusion(self, rule_id: str, context: dict[str, object]) -> str:
        """Render ``rule_id`` for inline placement in a prompt (``""`` if filtered out).

        A sandbox violation raises :class:`TemplateSecurityError` naming the
        rule's source file (specs/prK-lifecycle-hooks.md §P1).
        """
        rule = self._by_id.get(rule_id)
        if rule is None:
            return ""
        if rule.is_templated:
            # Merge stored facts beneath the caller-supplied context so callers
            # can pass {} (the auto-appended-appendix path in renderer.py does)
            # without hitting StrictUndefined on every templated rule that
            # references a fact. Caller-supplied keys win on collision.
            merged_context = {**self._facts, **context}
            body = render_sandboxed(
                rule.template_body, merged_context, env=self._env, source=template_source(rule)
            )
        else:
            body = rule.body
        return f"### {rule.frontmatter.name}\n\n{body}"


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
    """Every ``output_locations`` entry declared by an installed adapter, enabled or not.

    Disabled adapters count: their earlier output is exactly what ``playbook
    sync`` must still be able to clean up (SPEC §4.2 step 9). An adapter whose
    entry point fails to load declares nothing, so its output is never deleted.

    Example::

        >>> ".claude/skills/" in installed_output_locations()  # doctest: +SKIP
        True
    """
    locations: list[str] = []
    for ep in metadata.entry_points(group="coding_agent_playbook.adapters"):
        try:
            cls = ep.load()
        except (ImportError, AttributeError):
            continue
        locations.extend(getattr(cls, "output_locations", ()))
    return tuple(locations)


@dataclass
class SyncContext:
    """Bundle of state every CLI command needs after reading the config.

    ``rules_resolved``, ``prompts_resolved``, ``skills_resolved`` and
    ``hooks_resolved`` are post-overlay-merge but pre-applies_if-filter —
    filtering is the command's responsibility (sync filters; render does not).
    ``hook_load_errors`` holds the malformed hooks that ``tolerate_hook_errors``
    set aside; ``hook_violations`` the refused layer overrides (prK §A.5, §A.6).
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

    @classmethod
    def from_repo(
        cls,
        repo_root: Path,
        *,
        rule_registry: RuleRegistry | None = None,
        tolerate_hook_errors: bool = False,
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
        """
        config = FileSystemStateSource(repo_root=repo_root).load_config()
        return cls.from_config(
            repo_root,
            config,
            rule_registry=rule_registry,
            tolerate_hook_errors=tolerate_hook_errors,
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
    ) -> SyncContext:
        """:meth:`from_repo` minus the config load: detect → walk → resolve overlays.

        Config-less ``playbook validate`` passes a stand-in ``config`` and an
        ``artifact_source`` with extra checkout layers (prK §P P8); by default
        the source walks the engine, ``config.overlays_enabled`` and
        ``<repo>/playbook/``.

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
        # Engine + overlay artifacts come from importlib.resources via the
        # FileSystemArtifactSource walking each package's ``resources/`` tree;
        # repo-local artifacts come from ``<repo>/playbook/``. v1 walks all of
        # those in a single ``list_*`` call — sufficient for PR 10. PRs 13+
        # may split per-layer if we need fine-grained source provenance.
        resolver = OverlayResolver()
        all_rules = artifact_source.list_rules()
        all_prompts = artifact_source.list_prompts()
        all_skills = artifact_source.list_skills()
        # TODO(PR-13): the OverlayResolver supports per-layer wiring
        # (engine, overlays, repo-local) for the three-layer merge in
        # SPEC §11, but ``FileSystemArtifactSource`` currently returns a
        # single flattened list across all sources.
        # v1: source already flattened; per-layer wiring lands when first
        # overlay pack lands. See SPEC §11 for layer order.
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
    engine_package = (
        source.engine_package if isinstance(source, FileSystemArtifactSource) else ENGINE_PACKAGE
    )
    layers = split_hook_layers(hooks, engine_package=engine_package)
    return resolver.resolve_hooks(*layers), errors
