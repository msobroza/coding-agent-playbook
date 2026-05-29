"""Sync orchestration: glue between sources, renderer, and adapters.

This module exposes the data structure and helpers that the per-subcommand
modules in ``coding_agent_playbook.commands`` consume. The pieces here:

- :class:`SyncContext` — the bundle of (config, facts, source, adapters,
  resolved artifacts) handed to every command.
- :class:`OverlayResolver` — three-layer merge per SPEC §11 (engine, overlays,
  repo-local). Records collisions for ``cap check``.
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
from coding_agent_playbook.renderer import render_string
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
      1. Engine package artifacts (``coding_agent_playbook.resources.rules/*``).
      2. Each overlay package in ``config.overlays_enabled`` order.
      3. Repo-local artifacts under ``<repo>/playbook/``.

    For each ``(kind, id)`` pair the winner is kept; losers are recorded for
    ``cap check`` and ``cap render --show-source``.
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
        rule = self._by_id.get(rule_id)
        if rule is None:
            return ""
        if rule.is_templated:
            # Merge stored facts beneath the caller-supplied context so callers
            # can pass {} (the auto-appended-appendix path in renderer.py does)
            # without hitting StrictUndefined on every templated rule that
            # references a fact. Caller-supplied keys win on collision.
            merged_context = {**self._facts, **context}
            body = render_string(rule.template_body, merged_context, env=self._env)
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
    that don't (currently only ``agents_md``) are constructed with no
    arguments. The ``TypeError`` fallback is the canonical idiom for handling
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
        """Discovery: load config → instantiate sources → resolve overlays.

        ``rule_registry`` is optional because the adapters need it but the
        registry itself depends on the filtered rule list, which depends on
        facts. Callers that want the full pipeline build the context once
        without a registry, then re-build the adapters via
        :func:`discover_adapters` after the registry exists.
        """
        state_source = FileSystemStateSource(repo_root=repo_root)
        config = state_source.load_config()
        facts = detect(repo_root)

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
