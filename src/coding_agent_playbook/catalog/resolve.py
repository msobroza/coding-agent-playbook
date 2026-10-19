"""The overlay merge: one winner per artifact id across the Layers (SPEC §11).

:class:`OverlayResolver` merges the engine, overlay and repo-local layers by id
(later wins) and records each :class:`Collision` for ``playbook check``; hooks
instead merge every layer's definition through the additive
``hook_policy.merge_hook_layers`` (specs/prK-lifecycle-hooks.md §A.6). Split out
of the sync orchestration module in A5 (specs/prT-package-layout.md 4.14).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from coding_agent_playbook.artifacts.identity import artifact_id_of, source_package_of
from coding_agent_playbook.hook_policy import NO_HANDLER_SCHEMAS, merge_hook_layers

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.hook_policy import (
        ConfigSchemaLookup,
        HookLayerMerger,
        HookViolation,
    )


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
                    loser_log.setdefault(artifact_id, []).append(source_package_of(previous))
                winners[artifact_id] = artifact
        # Stable order: engine, overlays, repo-local — preserved by dict insertion.
        for artifact_id, losers in loser_log.items():
            self._collisions.append(
                Collision(
                    kind=kind,
                    artifact_id=artifact_id,
                    winner=source_package_of(winners[artifact_id]),
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
