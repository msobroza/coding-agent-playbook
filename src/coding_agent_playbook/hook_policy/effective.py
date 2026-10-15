"""The effective hook view: which merged hooks are on, and with what config (prK §A.7, §B.1, §B.3).

:func:`resolve_effective_hooks` is the single place that turns the hooks the
layer merge produced (§A.6) into what sync renders (§C.1.3 calls it):

1. the §B.1 on-formula: ``[hooks] enabled``, the definition's ``enabled``, then
   ``mandatory`` or (not in ``disable`` and (in ``enable`` or tier in ``tiers``));
   an ``overlay``-tier mechanism is never switched on from ``[hooks]`` (K-11);
2. applicability: ``applies_if`` ANDed with the linked rule's;
3. ``supports ∩ [hooks] adapters``;
4. the effective matcher (a scoped linked rule's globs become ``paths`` on tool
   events that declare none), the per-event ``on_error`` clamp, and the config
   layers after §A.6's: the handler's ``[guardrails]`` domain, then the
   consumer's ``[hooks.<hook-id>]``, each merged with the handler's key policies,
   minus its ``relax`` keys for a mandatory hook; last, a builtin's
   ``lint_codes`` from the linked rule, its ``when`` blocks resolved (§A.7 item 3).

Pure: it never mutates its inputs and never raises for a bad hook. Validate
(H3-H21) gates sync first; a value it would reject is skipped here with a reason
(an invalid ``applies_if``, a dangling ``linked_rule``) or passed through.
"""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook._hook_schema import HookMatcher
from coding_agent_playbook.hook_policy.lint_codes import (
    LINT_CODES_KEY,
    linked_lint_config,
    resolve_lint_codes,
)
from coding_agent_playbook.hook_policy.merge import NO_HANDLER_SCHEMAS, merge_config
from coding_agent_playbook.hook_policy.override_rules import bound_handler
from coding_agent_playbook.hook_policy.resolved import (
    EffectiveHooks,
    ResolvedHandler,
    ResolvedHook,
    SkippedHook,
    external_argv,
    script_sha256,
)
from coding_agent_playbook.hook_policy.tables import HOOK_CAPABLE_ADAPTERS, HOOK_EVENTS

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.hook_policy.handler_catalog import HandlerCatalog
    from coding_agent_playbook.hook_policy.merge import ConfigKeySpec, ConfigSchemaLookup
    from coding_agent_playbook.hooks_config import GuardrailsConfig, HooksConfig
    from coding_agent_playbook.types import Hook, HookHandler, Rule

_OVERLAY_TIER: Final = "overlay"


@dataclass(frozen=True)
class _Inputs:
    """Everything one hook's resolution reads besides the hook itself."""

    rules: Mapping[str, Rule]
    cfg: HooksConfig
    guardrails: GuardrailsConfig
    facts: Facts
    repo_root: Path
    targets: tuple[str, ...]
    schemas: ConfigSchemaLookup
    handlers: HandlerCatalog | None


def resolve_effective_hooks(
    hooks: Sequence[Hook],
    rules: Sequence[Rule],
    hooks_cfg: HooksConfig,
    guardrails_cfg: GuardrailsConfig,
    facts: Facts,
    repo_root: Path,
    *,
    adapters_enabled: Sequence[str],
    schemas: ConfigSchemaLookup = NO_HANDLER_SCHEMAS,
    handlers: HandlerCatalog | None = None,
) -> EffectiveHooks:
    """Split merged ``hooks`` into on (:class:`ResolvedHook`) and off (:class:`SkippedHook`).

    ``rules`` is the merged rule set (pre-``applies_if``), ``adapters_enabled``
    the config's, ``schemas`` the handlers' key policies and guardrails domains.
    ``handlers`` resolves a builtin name provided by an out-of-tree package to
    an ``entry_point`` record (in-tree wins), and is the default ``schemas``.
    With ``[hooks]`` off, every list is empty: sync renders nothing and prints
    its one notice line instead.

    Example::

        >>> view = resolve_effective_hooks(ctx.hooks_resolved, ctx.rules_resolved,
        ...     hooks_cfg, guardrails_cfg, ctx.facts, ctx.repo_root,
        ...     adapters_enabled=ctx.config.adapters_enabled)  # doctest: +SKIP
        >>> [hook.to_json() for hook in view.resolved]  # doctest: +SKIP
    """
    if not hooks_cfg.enabled:
        return EffectiveHooks([], [], [])
    targets = _hook_adapters(hooks_cfg, adapters_enabled)
    rule_ids = {rule.frontmatter.id: rule for rule in rules}
    if handlers is not None and schemas is NO_HANDLER_SCHEMAS:
        schemas = handlers
    inputs = _Inputs(
        rule_ids, hooks_cfg, guardrails_cfg, facts, repo_root, targets, schemas, handlers
    )
    warnings = _adapter_warnings(hooks_cfg, targets)
    resolved: list[ResolvedHook] = []
    skipped: list[SkippedHook] = []
    for hook in hooks:
        warnings.extend(_switch_warnings(hook, hooks_cfg))
        gated = _skip_reason(hook, inputs)
        if gated is None:
            resolved.append(_resolve(hook, inputs, warnings))
        else:
            skipped.append(SkippedHook(hook.frontmatter.id, gated[1], gate=gated[0]))
    # Handlers bound to several events share a consumer layer: warn once.
    return EffectiveHooks(resolved, skipped, list(dict.fromkeys(warnings)))


# --- which adapters receive hooks ------------------------------------------------


def _hook_adapters(cfg: HooksConfig, adapters_enabled: Sequence[str]) -> tuple[str, ...]:
    """``[hooks] adapters`` (default: every enabled one) ∩ ``adapters_enabled`` ∩ hook-capable."""
    wanted = adapters_enabled if cfg.adapters is None else cfg.adapters
    return tuple(
        name
        for name in dict.fromkeys(wanted)
        if name in adapters_enabled and name in HOOK_CAPABLE_ADAPTERS
    )


def _adapter_warnings(cfg: HooksConfig, targets: tuple[str, ...]) -> list[str]:
    capable = ", ".join(sorted(HOOK_CAPABLE_ADAPTERS))
    return [
        f"[hooks] adapters lists {name!r}, which is not an enabled hook-capable adapter "
        f"({capable}); it renders no hooks"
        for name in cfg.adapters or ()
        if name not in targets
    ]


def _supported(hook: Hook, targets: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in dict.fromkeys(hook.frontmatter.supports) if name in targets)


# --- on or off: the gates, first reason wins ---------------------------------------


def _switch_warnings(hook: Hook, cfg: HooksConfig) -> Iterator[str]:
    """``[hooks]`` switches that name a hook they cannot switch (validate reports H15)."""
    fm = hook.frontmatter
    if fm.mandatory and fm.id in cfg.disable:
        yield (
            f"[hooks] disable names {fm.id!r}, which is mandatory "
            f"(overlay {hook.source_package}); it stays on"
        )
    if fm.tier == _OVERLAY_TIER and not fm.mandatory and fm.id in cfg.enable:
        yield (
            f"[hooks] enable names {fm.id!r}, an overlay-tier mechanism; [hooks] cannot "
            "switch it on, only an overlay promoting it to tier: default"
        )


def _skip_reason(hook: Hook, inputs: _Inputs) -> tuple[str, str] | None:
    """``(gate, reason)`` of the first gate that turns ``hook`` off, else ``None``."""
    return next(
        ((name, reason) for name, gate in _GATES if (reason := gate(hook, inputs)) is not None),
        None,
    )


def _definition_off(hook: Hook, inputs: _Inputs) -> str | None:
    return None if hook.frontmatter.enabled else "its definition sets enabled: false"


def _switched_off(hook: Hook, inputs: _Inputs) -> str | None:
    """The §B.1 switches: mandatory beats them all, ``disable`` beats ``enable``."""
    fm, cfg = hook.frontmatter, inputs.cfg
    if fm.mandatory:
        return None
    if fm.id in cfg.disable:
        return "disabled by [hooks] disable"
    if fm.tier == _OVERLAY_TIER:
        # K-11 (locked) narrows the §B.1 formula: `enable` cannot activate a mechanism.
        return "tier 'overlay' is activated only by an overlay promoting the hook to tier: default"
    if fm.id in cfg.enable or fm.tier in cfg.tiers:
        return None
    return (
        f"tier {fm.tier!r} is not in [hooks] tiers {list(cfg.tiers)!r} "
        "and [hooks] enable does not name it"
    )


def _applies_if_fails(hook: Hook, inputs: _Inputs) -> str | None:
    applies_if = hook.frontmatter.applies_if
    try:
        holds = _predicate_holds(applies_if, inputs)
    except ValueError as exc:
        return f"applies_if is invalid: {exc}"
    return None if holds else f"applies_if {applies_if!r} does not hold"


def _linked_rule_fails(hook: Hook, inputs: _Inputs) -> str | None:
    """A dangling (H18) or inapplicable linked rule turns the hook off (§A.7 item 1)."""
    rule_id = hook.frontmatter.linked_rule
    if rule_id is None:
        return None
    rule = inputs.rules.get(rule_id)
    if rule is None:
        return f"linked rule {rule_id!r} not found"
    try:
        holds = _predicate_holds(rule.frontmatter.applies_if, inputs)
    except ValueError as exc:
        return f"linked rule {rule_id!r} has an invalid applies_if: {exc}"
    return None if holds else f"linked rule {rule_id!r} not applicable"


def _no_target_adapter(hook: Hook, inputs: _Inputs) -> str | None:
    if _supported(hook, inputs.targets):
        return None
    return (
        f"no adapter it supports ({hook.frontmatter.supports!r}) receives hooks; "
        f"[hooks] adapters: {list(inputs.targets)!r}"
    )


_GATES: Final[tuple[tuple[str, Callable[[Hook, _Inputs], str | None]], ...]] = (
    ("definition", _definition_off),
    ("switch", _switched_off),
    ("applies_if", _applies_if_fails),
    ("linked_rule", _linked_rule_fails),
    ("adapters", _no_target_adapter),
)


def effective_applies_if(
    hook: Hook, rules: Mapping[str, Rule]
) -> tuple[dict[str, Any], ...] | None:
    """The predicates that must all hold for ``hook`` to apply: its own, then its linked rule's.

    Empty predicates are left out (``()`` means always); ``None`` when the
    linked rule is missing, so the hook can never apply. The same AND the
    ``applies_if`` and ``linked_rule`` gates evaluate (§A.7 item 1).

    Example::

        >>> effective_applies_if(hook_linked_to_ml_rule, {"ml": ml_rule})  # doctest: +SKIP
        ({'any_ml_stack': ['torch']},)
    """
    predicates = [dict(hook.frontmatter.applies_if or {})]
    rule_id = hook.frontmatter.linked_rule
    if rule_id is not None:
        rule = rules.get(rule_id)
        if rule is None:
            return None
        predicates.append(dict(rule.frontmatter.applies_if or {}))
    return tuple(predicate for predicate in predicates if predicate)


def _predicate_holds(predicate: Mapping[str, Any], inputs: _Inputs) -> bool:
    if not predicate:
        return True
    # Imported here: detector imports packaging, and importing hook_policy stays stdlib-only.
    from coding_agent_playbook.detector import evaluate_predicate

    return evaluate_predicate(dict(predicate), inputs.facts, repo_root=inputs.repo_root)


# --- the record of an on hook -----------------------------------------------------


def _resolve(hook: Hook, inputs: _Inputs, warnings: list[str]) -> ResolvedHook:
    fm = hook.frontmatter
    matcher = _effective_matcher(hook, inputs.rules.get(fm.linked_rule or ""))
    bound = {event: h for event in fm.events if (h := bound_handler(fm, event)) is not None}
    # The advisory's globs come from the effective matcher, inherited paths included.
    advisory_source = dataclasses.replace(
        hook, frontmatter=dataclasses.replace(fm, matcher=matcher)
    )
    return ResolvedHook(
        id=fm.id,
        source_package=hook.source_package,
        events=tuple(fm.events),
        priority=fm.priority,
        matcher=matcher,
        handlers={
            event: _resolve_handler(hook, handler, inputs, warnings)
            for event, handler in bound.items()
        },
        decisions=tuple(fm.decisions),
        timeout=fm.timeout,
        on_error={event: _clamped_on_error(fm.on_error, event) for event in fm.events},
        supports=_supported(hook, inputs.targets),
        mandatory=fm.mandatory,
        script_sha256=script_sha256(hook, bound.values()),
        advisory=advisory_source.to_advisory_rule() if inputs.cfg.advisory else None,
        definition=hook,
    ).with_rendered_body(hook.body)  # a .md body is final; sync re-renders a .md.j2 one


def _effective_matcher(hook: Hook, rule: Rule | None) -> dict[str, HookMatcher]:
    """A copy of the matcher of every declared event; a scoped linked rule's globs fill ``paths``.

    Only on events with a ``paths`` dimension, and only where the hook declares
    none: explicit paths win, with no union (§A.7 item 2).
    """
    globs = [] if rule is None or rule.frontmatter.scope != "scoped" else rule.frontmatter.globs
    matcher: dict[str, HookMatcher] = {}
    for event in hook.frontmatter.events:
        authored = hook.frontmatter.matcher.get(event)
        entry = HookMatcher() if authored is None else copy.deepcopy(authored)
        if globs and not entry.paths and "paths" in _matcher_fields(event):
            entry.paths = list(globs)
        matcher[event] = entry
    return matcher


def _matcher_fields(event: str) -> frozenset[str]:
    spec = HOOK_EVENTS.get(event)
    return frozenset() if spec is None else spec.matcher_fields


def _clamped_on_error(declared: str, event: str) -> str:
    """``declared`` where the event honours it, else ``open`` (the §A.2 clamp)."""
    spec = HOOK_EVENTS.get(event)
    return declared if spec is not None and declared in spec.on_error_allowed else "open"


def _resolve_handler(
    hook: Hook, handler: HookHandler, inputs: _Inputs, warnings: list[str]
) -> ResolvedHandler:
    """``handler`` with the consumer layers merged into a copy of its config."""
    specs = {} if handler.builtin is None else inputs.schemas.key_specs(handler.builtin)
    config = copy.deepcopy(handler.config)
    for label, layer in _consumer_layers(hook, handler, inputs):
        config = merge_config(config, _without_relaxed(layer, specs, hook, label, warnings), specs)
    if handler.builtin is not None:
        config.update(_linked_lint_codes(hook, inputs))
        return _builtin(handler.builtin, config, inputs.handlers)
    return ResolvedHandler(
        "external", argv=external_argv(hook.frontmatter.id, handler), config=config
    )


def _linked_lint_codes(hook: Hook, inputs: _Inputs) -> dict[str, Any]:
    """``{"lint_codes": ...}`` from the linked rule's ``lint_codes`` (§A.7 item 3), else ``{}``.

    The rule is the one source: it replaces any value, and the key is no
    handler's ``CONFIG_SCHEMA`` key, so no layer can set it.
    """
    rule = inputs.rules.get(hook.frontmatter.linked_rule or "")
    if rule is None or not rule.frontmatter.lint_codes:
        return {}
    codes = resolve_lint_codes(
        rule.frontmatter.lint_codes, inputs.facts, lambda p, _facts: _predicate_holds(p, inputs)
    )
    return {LINT_CODES_KEY: linked_lint_config(rule.frontmatter.id, codes)}


def _builtin(name: str, config: dict[str, Any], handlers: HandlerCatalog | None) -> ResolvedHandler:
    """An in-tree builtin by name, or the out-of-tree entry point that provides ``name``."""
    entry = None if handlers is None else handlers.lookup(name)
    if entry is None or entry.source != "entry_point" or entry.target is None:
        return ResolvedHandler("builtin", name=name, config=config)
    return ResolvedHandler(
        "entry_point", name=name, target=entry.target, dist=entry.dist, config=config
    )


def _consumer_layers(
    hook: Hook, handler: HookHandler, inputs: _Inputs
) -> list[tuple[str, dict[str, Any]]]:
    """The config layers after §A.6's, in merge order: the guardrails domain, then [hooks.<id>]."""
    layers: list[tuple[str, dict[str, Any]]] = []
    domain = None if handler.builtin is None else inputs.schemas.config_domain(handler.builtin)
    if domain is not None:
        layers.append((f"[guardrails.{domain}]", inputs.guardrails.domain_values(domain)))
    hook_id = hook.frontmatter.id
    layers.append((f"[hooks.{hook_id}]", copy.deepcopy(inputs.cfg.per_hook.get(hook_id, {}))))
    return layers


def _without_relaxed(
    layer: dict[str, Any],
    specs: Mapping[str, ConfigKeySpec],
    hook: Hook,
    label: str,
    warnings: list[str],
) -> dict[str, Any]:
    """``layer`` minus its ``relax`` keys when ``hook`` is mandatory, each one warned."""
    if not hook.frontmatter.mandatory:
        return layer
    relaxed = [key for key in layer if key in specs and specs[key].policy == "relax"]
    warnings.extend(
        f"{label} {key} is ignored for {hook.frontmatter.id!r}: a mandatory hook's "
        "relax keys cannot be loosened by the consumer"
        for key in relaxed
    )
    return {key: value for key, value in layer.items() if key not in relaxed}
