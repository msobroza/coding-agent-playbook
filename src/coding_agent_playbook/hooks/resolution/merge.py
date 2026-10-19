"""Fold every layer's definition of one hook id into the one that syncs (§A.6, lock L2).

``OverlayResolver.resolve_hooks`` hands :func:`merge_hook_layers` all the
definitions of an id in layer order (engine, overlays in ``overlays_enabled``
order, repo-local; :func:`split_hook_layers` sorts a source's flat list into
those layers), not only the winner, because the additive policy compares each
override with what it overrides:

- an overlay replaces the frontmatter by id but may only add (H14,
  :mod:`.override_rules`), and its builtin ``handler.config`` merges per the
  handler's key policies (:func:`merge_config`);
- a repo-local definition replaces a non-mandatory hook outright, every config
  key ``replace``; over a ``mandatory`` hook it is refused (H15);
- a second definition of the id in the same layer is refused (H2).

Violations are returned, never raised: ``playbook validate`` reports them and
the validate-gated ``playbook sync`` refuses to render (specs/prK-lifecycle-hooks.md
§B.5). The handler key policies come from an injected :class:`ConfigSchemaLookup`;
the real ``CONFIG_SCHEMA`` registry is K2's, and without one every key is
``replace``.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol

from coding_agent_playbook.catalog.layers import REPO_LOCAL_SOURCE
from coding_agent_playbook.hooks.resolution.override_rules import (
    bound_handler,
    overlay_override_problems,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.hook_schema import HookHandler

#: How a builtin handler's config key merges across layers (§A.6): ``extend``
#: (deny rows, patterns: union, earlier first, deduped), ``strictest`` (ordered
#: modes: the stricter wins), ``relax`` (allowlists: union), ``replace``.
KeyPolicy = Literal["extend", "strictest", "relax", "replace"]


@dataclass(frozen=True)
class ConfigKeySpec:
    """The merge policy of one handler config key; ``order`` ranks a ``strictest`` key.

    Example: ``ConfigKeySpec("strictest", order=("off", "warn", "block"))``.
    """

    policy: KeyPolicy
    order: tuple[str, ...] = ()


class ConfigSchemaLookup(Protocol):
    """Where a builtin handler's config key policies (``CONFIG_SCHEMA``) and its
    ``[guardrails]`` domain (``CONFIG_DOMAIN``, §B.3) come from."""

    def key_specs(self, builtin: str) -> Mapping[str, ConfigKeySpec]:
        """Key policies of handler ``builtin``; ``{}`` when it declares none."""
        ...

    def config_domain(self, builtin: str) -> str | None:
        """The ``[guardrails]`` domain handler ``builtin`` reads, or None when it reads none."""
        ...


_NO_SPECS: Final[Mapping[str, ConfigKeySpec]] = MappingProxyType({})


class _NoHandlerSchemas:
    """No handler declares key policies or a guardrails domain: every key is ``replace``."""

    def key_specs(self, builtin: str) -> Mapping[str, ConfigKeySpec]:
        return _NO_SPECS

    def config_domain(self, builtin: str) -> str | None:
        return None


#: The lookup until K2's handler registry exists.
NO_HANDLER_SCHEMAS: Final[ConfigSchemaLookup] = _NoHandlerSchemas()


@dataclass(frozen=True)
class HookViolation:
    """One refused layer override: the rule (``H2``/``H14``/``H15``), where, and why.

    ``where`` is the offending definition's ``HOOK.md`` path, else its
    ``source_package``.

    Example::

        >>> HookViolation("H14", "guard-x", "acme", "overlay 'acme' override of 'guard-x' drops event 'stop'").rule
        'H14'
    """

    rule: str
    hook_id: str
    where: str
    message: str


class HookLayerMerger(Protocol):
    """The shape of :func:`merge_hook_layers`, so ``OverlayResolver`` can take a spy."""

    def __call__(
        self, definitions: Sequence[Hook], *, schemas: ConfigSchemaLookup = ...
    ) -> tuple[Hook, list[HookViolation]]: ...


def merge_hook_layers(
    definitions: Sequence[Hook], *, schemas: ConfigSchemaLookup = NO_HANDLER_SCHEMAS
) -> tuple[Hook, list[HookViolation]]:
    """Fold ``definitions`` (one id, layer order) into the effective hook, plus violations.

    Never raises for a violation; a refused override (H2, H15) leaves the
    earlier definition in place. Raises ``ValueError`` only for an empty input.

    Example::

        >>> hook, violations = merge_hook_layers([engine_hook, overlay_hook])  # doctest: +SKIP
    """
    if not definitions:
        raise ValueError(
            f"merge_hook_layers needs at least one definition, got {list(definitions)!r}"
        )
    heads, violations = _one_per_layer(definitions)
    merged = heads[0]
    for later in heads[1:]:
        merged, found = _merge_pair(merged, later, schemas)
        violations.extend(found)
    return merged, violations


def split_hook_layers(
    hooks: list[Hook], *, engine_package: str
) -> tuple[list[Hook], list[list[Hook]], list[Hook]]:
    """Split a source's flat hook list into ``(engine, overlays, repo_local)`` layers.

    The engine layer is ``source_package == engine_package`` exactly: a
    bundled plugin such as ``coding_agent_playbook.plugins.superpowers`` is an
    overlay. Overlays keep their first-appearance order, which
    ``FileSystemArtifactSource.layer_roots`` makes the resolution order.

    Example::

        >>> split_hook_layers([], engine_package="coding_agent_playbook")
        ([], [], [])
    """
    engine: list[Hook] = []
    overlays: dict[str, list[Hook]] = {}
    repo_local: list[Hook] = []
    for hook in hooks:
        if hook.source_package == engine_package:
            engine.append(hook)
        elif hook.source_package == REPO_LOCAL_SOURCE:
            repo_local.append(hook)
        else:
            overlays.setdefault(hook.source_package, []).append(hook)
    return engine, list(overlays.values()), repo_local


def merge_config(
    earlier: Mapping[str, Any], later: Mapping[str, Any], specs: Mapping[str, ConfigKeySpec]
) -> dict[str, Any]:
    """``earlier`` with each key of ``later`` merged per its spec (``replace`` without one).

    Keys only ``earlier`` has are kept. Pure: neither input is modified.

    Example::

        >>> merge_config({"deny": ["a"]}, {"deny": ["b"]}, {"deny": ConfigKeySpec("extend")})
        {'deny': ['a', 'b']}
    """
    merged = dict(earlier)
    for key, value in later.items():
        spec = specs.get(key)
        if spec is not None and key in earlier:
            value = _merge_value(spec, earlier[key], value)
        merged[key] = value
    return merged


def _merge_value(spec: ConfigKeySpec, old: Any, new: Any) -> Any:
    if spec.policy in ("extend", "relax") and isinstance(old, list) and isinstance(new, list):
        return _union(old, new)
    if spec.policy == "strictest":
        return _stricter(spec.order, old, new)
    return new


def _union(old: list[Any], new: list[Any]) -> list[Any]:
    """``old`` then ``new``, deduped by equality: rows may be tables, which are unhashable."""
    merged: list[Any] = []
    for item in [*old, *new]:
        if item not in merged:
            merged.append(item)
    return merged


def _stricter(order: tuple[str, ...], old: Any, new: Any) -> Any:
    """The stricter of two modes; an unranked ``new`` never lowers a ranked ``old``."""
    # Tuple membership compares by equality, so an unhashable value cannot raise.
    if new not in order:
        return old if old in order else new
    if old not in order:
        return new
    return new if order.index(new) > order.index(old) else old


def _one_per_layer(definitions: Sequence[Hook]) -> tuple[list[Hook], list[HookViolation]]:
    """The first definition of each layer, and an H2 violation for every further one."""
    first_of: dict[str, Hook] = {}
    violations: list[HookViolation] = []
    for hook in definitions:
        first = first_of.setdefault(hook.source_package, hook)
        if first is not hook:
            message = (
                f"id {hook.frontmatter.id!r} is defined more than once in layer "
                f"{hook.source_package!r}: {_where(first)}, {_where(hook)}"
            )
            violations.append(_violation("H2", hook, message))
    return list(first_of.values()), violations


def _merge_pair(
    earlier: Hook, later: Hook, schemas: ConfigSchemaLookup
) -> tuple[Hook, list[HookViolation]]:
    hook_id = later.frontmatter.id
    if later.source_package == REPO_LOCAL_SOURCE:
        if earlier.frontmatter.mandatory:
            message = (
                f"{hook_id!r} is mandatory (overlay {earlier.source_package}) and cannot be "
                "overridden by a repo-local definition"
            )
            return earlier, [_violation("H15", later, message)]
        return _with_merged_config(earlier, later, NO_HANDLER_SCHEMAS), []
    prefix = f"overlay {later.source_package!r} override of {hook_id!r}"
    violations = [
        _violation("H14", later, f"{prefix} {problem}")
        for problem in overlay_override_problems(earlier, later)
    ]
    return _with_merged_config(earlier, later, schemas), violations


def _with_merged_config(earlier: Hook, later: Hook, schemas: ConfigSchemaLookup) -> Hook:
    """``later`` whose builtin handlers' configs are merged with ``earlier``'s."""
    before, after = earlier.frontmatter, later.frontmatter
    handler = (
        None if after.handler is None else _merged_handler(before.handler, after.handler, schemas)
    )
    handlers = {
        event: _merged_handler(bound_handler(before, event), new, schemas)
        for event, new in after.handlers.items()
    }
    frontmatter = dataclasses.replace(after, handler=handler, handlers=handlers)
    return dataclasses.replace(later, frontmatter=frontmatter)


def _merged_handler(
    old: HookHandler | None, new: HookHandler, schemas: ConfigSchemaLookup
) -> HookHandler:
    """``new`` with ``old``'s config merged in, when both bind the same builtin."""
    if old is None or new.builtin is None or old.builtin != new.builtin:
        return new
    config = merge_config(old.config, new.config, schemas.key_specs(new.builtin))
    return dataclasses.replace(new, config=config)


def _violation(rule: str, hook: Hook, message: str) -> HookViolation:
    return HookViolation(rule, hook.frontmatter.id, _where(hook), message)


def _where(hook: Hook) -> str:
    return hook.source_package if hook.source_path is None else str(hook.source_path)
