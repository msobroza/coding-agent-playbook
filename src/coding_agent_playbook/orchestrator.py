"""Sync orchestration: glue between sources, renderer, and adapters.

This module exposes the data structure and helpers that the per-subcommand
modules in ``coding_agent_playbook.commands`` consume. The pieces here:

- :class:`SyncContext` — the bundle of (config, facts, source, adapters,
  resolved artifacts) handed to every command.
- :class:`OverlayResolver` — three-layer merge per SPEC §11 (engine, overlays,
  repo-local). Records collisions for ``playbook check``.
- :class:`RuleRegistryImpl` — concrete ``RuleRegistry`` from the renderer
  Protocol. Built once per sync from the applies_if-filtered rule list.
- :func:`filter_applies_if` / :func:`build_prompt_environment` — the shared
  applies_if filter and the rule-aware Jinja environments every prompt render
  (``sync``, ``render``, the eval runner) builds the same way.
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

import sys
from dataclasses import dataclass, field
from importlib import metadata
from typing import TYPE_CHECKING

from coding_agent_playbook.bundled_content import canonical_overlay_name
from coding_agent_playbook.detector import detect, evaluate_predicate
from coding_agent_playbook.renderer import build_environment, render_sandboxed
from coding_agent_playbook.sources.filesystem import (
    FileSystemArtifactSource,
    FileSystemStateSource,
)

if TYPE_CHECKING:
    from pathlib import Path

    from jinja2 import Environment

    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.config import Config
    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.renderer import RuleRegistry
    from coding_agent_playbook.sources.base import ArtifactSource, StateSource
    from coding_agent_playbook.types import Prompt, Rule, Skill


@dataclass(frozen=True)
class Collision:
    """One overlay collision recorded by :class:`OverlayResolver`.

    ``kind`` is one of ``"rule"``, ``"prompt"``, ``"skill"``; ``artifact_id`` is
    the conflicting ID; ``winner`` and ``losers`` are the source package names
    (e.g. ``"coding_agent_playbook"``, ``"<repo-local>"``).
    """

    kind: str
    artifact_id: str
    winner: str
    losers: tuple[str, ...]


class OverlayResolver:
    """Merge engine + overlay + repo-local artifact lists by ID (SPEC §11).

    Resolution order (later wins on ID collision):
      1. Engine artifacts (the bundled ``content/core/``).
      2. Each overlay package or bundled plugin, in ``config.overlays_enabled`` order.
      3. Repo-local artifacts under ``<repo>/playbook/``.

    For each ``(kind, id)`` pair the winner is kept; losers are recorded for
    ``playbook check`` and ``playbook render --show-source``.
    """

    def __init__(self) -> None:
        self._collisions: list[Collision] = []

    @property
    def collisions(self) -> list[Collision]:
        return list(self._collisions)

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


def filter_applies_if[T: "Rule | Prompt"](
    artifacts: list[T],
    facts: Facts,
    repo_root: Path,
) -> list[T]:
    """Drop the artifacts whose ``applies_if`` is false for ``facts`` (SPEC §6.4).

    An empty predicate always passes. ``repo_root`` anchors ``has_file`` paths.

    Example::

        rules = filter_applies_if(ctx.rules_resolved, ctx.facts, ctx.repo_root)
    """
    kept: list[T] = []
    for artifact in artifacts:
        predicate = artifact.frontmatter.applies_if or {}
        if not predicate or evaluate_predicate(predicate, facts, repo_root=repo_root):
            kept.append(artifact)
    return kept


def build_prompt_environment(
    rules: list[Rule], facts: Facts
) -> tuple[RuleRegistryImpl, Environment]:
    """Build the rule registry and the prompt Jinja environment that renders through it.

    The registry renders included rules in an environment *without* ``rule()``
    (rules cannot include rules, SPEC §6.2.5); the returned prompt environment
    registers ``rule()`` against that registry. Both see ``facts`` for the
    ``has_framework``/``has_ml_dep`` helpers.

    Example::

        registry, prompt_env = build_prompt_environment(applicable_rules, facts)
    """
    rule_env = build_environment([], is_prompt_context=False)
    rule_env.globals["_facts"] = dict(facts)
    registry = RuleRegistryImpl(rules, facts, rule_env)
    prompt_env = build_environment([], is_prompt_context=True, rule_registry=registry)
    prompt_env.globals["_facts"] = dict(facts)
    return registry, prompt_env


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

    ``rules_resolved``, ``prompts_resolved``, ``skills_resolved`` are
    post-overlay-merge but pre-applies_if-filter — filtering is the command's
    responsibility (sync filters; render does not).
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

    @classmethod
    def from_repo(
        cls,
        repo_root: Path,
        *,
        rule_registry: RuleRegistry | None = None,
    ) -> SyncContext:
        """Discovery: load config → detect facts → instantiate sources → resolve overlays.

        ``rule_registry`` is optional because the adapters need it but the
        registry itself depends on the filtered rule list, which depends on
        facts. Callers that want the full pipeline build the context once
        without a registry, then re-build the adapters via
        :func:`discover_adapters` after the registry exists.

        Prints one ``warning:`` line per deprecated ``coding_agent_playbook.packs.*``
        overlay name, before anything else runs (:func:`_warn_deprecated_overlays`).
        """
        state_source = FileSystemStateSource(repo_root=repo_root)
        config = state_source.load_config()
        _warn_deprecated_overlays(config, state_source)
        facts = detect(repo_root)

        artifact_source = FileSystemArtifactSource(
            repo_root=repo_root,
            overlay_packages=list(config.overlays_enabled),
        )
        # FileSystemArtifactSource walks the engine and bundled-plugin artifacts
        # in the bundled content (``content/core/``, ``content/plugins/<name>/``)
        # and each overlay package's ``resources/`` tree via importlib.resources;
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
        # v1: source already flattened; per-layer wiring lands when the first
        # overlay package needs it. See SPEC §11 for layer order.
        # ID collisions across the merged list still flag winners vs losers
        # via insertion-order semantics, which is enough for the engine-only
        # v1 we ship today.
        rules_resolved = resolver.resolve_rules(all_rules, [], [])
        prompts_resolved = resolver.resolve_prompts(all_prompts, [], [])
        skills_resolved = resolver.resolve_skills(all_skills, [], [])

        adapters = discover_adapters(config, rule_registry=rule_registry)

        return cls(
            repo_root=repo_root,
            config=config,
            facts=facts,
            artifact_source=artifact_source,
            state_source=state_source,
            adapters=adapters,
            rules_resolved=rules_resolved,
            prompts_resolved=prompts_resolved,
            skills_resolved=skills_resolved,
            overlay_collisions=resolver.collisions,
        )
