"""The effective hook view: which hooks are on, and their merged config (prK §A.7, §B.1, §B.3).

``resolve_effective_hooks`` is pure over merged hooks, the rule set, the parsed
``[hooks]`` / ``[guardrails]`` tables and the detector facts. It applies the §B.1
on-formula, ``applies_if`` ANDed with the linked rule's, the linked rule's globs
as ``paths`` (tool events only), ``supports ∩ [hooks] adapters``, the per-event
``on_error`` clamp, and the consumer config layers. Handler key policies and the
guardrails domain come from :class:`FakeHandlerSchemas` (the registry is K2's).
The ``guard_config.json`` record (``to_json``) is tested in
``test_hook_policy_resolved.py``.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_policy import (
    APPLICABILITY_GATES,
    NO_HANDLER_SCHEMAS,
    ConfigKeySpec,
    ConfigSchemaLookup,
    EffectiveHooks,
    SkippedHook,
    effective_applies_if,
    resolve_effective_hooks,
)
from coding_agent_playbook.hooks_config import (
    GuardrailsConfig,
    HooksConfig,
    parse_guardrails_config,
    parse_hooks_config,
)
from coding_agent_playbook.types import Hook, Rule, RuleFrontmatter
from tests.fakes import FakeHandlerSchemas
from tests.hook_samples import sample_hook

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.detector import Facts

OVERLAY = "acme_rules"
FASTAPI: Facts = {"frameworks": {"fastapi": "0.110"}}
_MODES = ("off", "warn", "block")


def _resolve(
    hooks: Sequence[Hook],
    *,
    cfg: HooksConfig | None = None,
    rules: Sequence[Rule] = (),
    guardrails: GuardrailsConfig | None = None,
    facts: Facts | None = None,
    adapters: Sequence[str] = ("claude_code", "opencode"),
    schemas: ConfigSchemaLookup = NO_HANDLER_SCHEMAS,
) -> EffectiveHooks:
    return resolve_effective_hooks(
        hooks,
        rules,
        HooksConfig(enabled=True) if cfg is None else cfg,
        GuardrailsConfig() if guardrails is None else guardrails,
        {} if facts is None else facts,
        Path("/repo"),
        adapters_enabled=adapters,
        schemas=schemas,
    )


def _rule(
    rule_id: str = "pii-handling",
    *,
    scope: str = "always",
    globs: Sequence[str] = (),
    applies_if: dict[str, Any] | None = None,
) -> Rule:
    frontmatter = RuleFrontmatter(
        id=rule_id,
        name="PII handling",
        description="Mask PII.",
        scope=scope,  # type: ignore[arg-type]
        globs=list(globs),
        applies_if=applies_if or {},
    )
    return Rule(frontmatter, "Mask it.\n", "Mask it.\n", False, None, "<repo-local>")


def _ids(view: EffectiveHooks) -> list[str]:
    return [hook.id for hook in view.resolved]


def _only_skip(view: EffectiveHooks) -> SkippedHook:
    assert view.resolved == []
    (skipped,) = view.skipped
    return skipped


def _config(view: EffectiveHooks, event: str = "pre_tool_use") -> dict[str, Any]:
    (hook,) = view.resolved
    return hook.handlers[event].config


# --- the on-formula (§B.1) -------------------------------------------------------


@pytest.mark.parametrize(
    "cfg", [parse_hooks_config(None), parse_hooks_config({}), HooksConfig(enabled=False)]
)
def test_hooks_off_when_table_absent_or_disabled(cfg: HooksConfig) -> None:
    assert _resolve([sample_hook()], cfg=cfg) == EffectiveHooks([], [], [])


@pytest.mark.parametrize(
    ("tier", "switches", "on"),
    [
        ("default", {}, True),
        ("opt-in", {}, False),
        ("opt-in", {"tiers": ("default", "opt-in")}, True),
        ("opt-in", {"enable": ("guard-x",)}, True),
        ("default", {"disable": ("guard-x",)}, False),
        ("default", {"tiers": ("opt-in",)}, False),
        ("default", {"tiers": (), "enable": ("guard-x",)}, True),
    ],
)
def test_on_formula(tier: str, switches: dict[str, Any], on: bool) -> None:
    view = _resolve([sample_hook(tier=tier)], cfg=HooksConfig(enabled=True, **switches))

    assert _ids(view) == (["guard-x"] if on else [])


def test_disable_wins_over_enable() -> None:
    cfg = HooksConfig(enabled=True, enable=("guard-x",), disable=("guard-x",))

    skipped = _only_skip(_resolve([sample_hook(tier="opt-in")], cfg=cfg))

    assert skipped == SkippedHook("guard-x", "disabled by [hooks] disable")


def test_tier_off_reason_names_the_tier() -> None:
    skipped = _only_skip(_resolve([sample_hook(tier="opt-in")]))

    assert skipped.reason == (
        "tier 'opt-in' is not in [hooks] tiers ['default'] and [hooks] enable does not name it"
    )


def test_mandatory_ignores_disable_and_tier() -> None:
    hook = sample_hook(OVERLAY, tier="opt-in", mandatory=True)
    cfg = HooksConfig(enabled=True, tiers=(), disable=("guard-x",))

    view = _resolve([hook], cfg=cfg)

    assert _ids(view) == ["guard-x"]
    assert view.warnings == [
        "[hooks] disable names 'guard-x', which is mandatory (overlay acme_rules); it stays on"
    ]


def test_overlay_tier_is_never_switched_on_from_config() -> None:
    """K-11 (locked): only an overlay promoting it to tier: default activates it."""
    cfg = HooksConfig(enabled=True, tiers=("default", "opt-in"), enable=("guard-x",))

    view = _resolve([sample_hook(tier="overlay")], cfg=cfg)

    assert _only_skip(view).reason == (
        "tier 'overlay' is activated only by an overlay promoting the hook to tier: default"
    )
    assert view.warnings == [
        "[hooks] enable names 'guard-x', an overlay-tier mechanism; [hooks] cannot "
        "switch it on, only an overlay promoting it to tier: default"
    ]


def test_definition_enabled_false_is_off() -> None:
    cfg = HooksConfig(enabled=True, enable=("guard-x",))

    skipped = _only_skip(_resolve([sample_hook(enabled=False)], cfg=cfg))

    assert skipped.reason == "its definition sets enabled: false"


# --- applicability: applies_if and linked_rule (§A.7) ---------------------------


def test_applies_if_false_is_skipped_with_reason() -> None:
    hook = sample_hook(applies_if={"has_framework": ["fastapi"]})

    assert _ids(_resolve([hook], facts=FASTAPI)) == ["guard-x"]
    assert _only_skip(_resolve([hook])).reason == (
        "applies_if {'has_framework': ['fastapi']} does not hold"
    )


def test_invalid_applies_if_is_skipped_not_raised() -> None:
    """Validate reports the unknown key (H17); resolution never raises."""
    skipped = _only_skip(_resolve([sample_hook(applies_if={"orm_version": "2"})]))

    assert skipped.reason == "applies_if is invalid: unknown predicate key: 'orm_version'"


def test_linked_rule_applies_if_anded_and_not_applicable_reason() -> None:
    rule = _rule(applies_if={"has_framework": ["fastapi"]})
    linked = sample_hook(linked_rule="pii-handling")
    both = sample_hook(linked_rule="pii-handling", applies_if={"has_framework": ["flask"]})

    assert _ids(_resolve([linked], rules=[rule], facts=FASTAPI)) == ["guard-x"]
    assert _only_skip(_resolve([linked], rules=[rule])).reason == (
        "linked rule 'pii-handling' not applicable"
    )
    assert _only_skip(_resolve([both], rules=[rule], facts=FASTAPI)).reason.startswith(
        "applies_if {'has_framework': ['flask']}"
    )


def test_linked_rule_with_an_invalid_applies_if_is_skipped_not_raised() -> None:
    rule = _rule(applies_if={"orm_version": "2"})

    skipped = _only_skip(_resolve([sample_hook(linked_rule="pii-handling")], rules=[rule]))

    assert skipped.reason == (
        "linked rule 'pii-handling' has an invalid applies_if: unknown predicate key: 'orm_version'"
    )


def test_dangling_linked_rule_is_skipped() -> None:
    """Validate reports the dangling id (H18); resolution skips the hook."""
    skipped = _only_skip(_resolve([sample_hook(linked_rule="no-such-rule")]))

    assert skipped.reason == "linked rule 'no-such-rule' not found"


def test_skipped_hook_names_the_gate_that_turned_it_off() -> None:
    """resync-on-detector-input-change keeps rows only for the applicability gates (K5)."""
    rule = _rule(applies_if={"has_framework": ["fastapi"]})
    hooks = [
        sample_hook(id="by-applies-if", applies_if={"has_framework": ["flask"]}),
        sample_hook(id="by-linked-rule", linked_rule="pii-handling"),
        sample_hook(id="by-tier", tier="opt-in"),
        sample_hook(id="by-definition", enabled=False),
    ]

    gates = {skip.id: skip.gate for skip in _resolve(hooks, rules=[rule]).skipped}

    assert gates == {
        "by-applies-if": "applies_if",
        "by-linked-rule": "linked_rule",
        "by-tier": "switch",
        "by-definition": "definition",
    }
    assert {"applies_if", "linked_rule"} == APPLICABILITY_GATES


def test_effective_applies_if_ands_the_linked_rule_predicate() -> None:
    rule = _rule(applies_if={"has_framework": ["fastapi"]})
    both = sample_hook(linked_rule="pii-handling", applies_if={"has_file": ["Dockerfile"]})

    assert effective_applies_if(both, {"pii-handling": rule}) == (
        {"has_file": ["Dockerfile"]},
        {"has_framework": ["fastapi"]},
    )
    assert effective_applies_if(sample_hook(), {}) == ()
    assert effective_applies_if(sample_hook(linked_rule="gone"), {}) is None


@pytest.mark.parametrize(
    ("rule", "hook_paths", "expected"),
    [
        (_rule(scope="scoped", globs=["**/*.sql"]), [], ["**/*.sql"]),
        (_rule(scope="scoped", globs=["**/*.sql"]), ["db/*.sql"], ["db/*.sql"]),
        (_rule(scope="always", globs=["**/*.sql"]), [], []),
        (_rule(scope="scoped", globs=[]), [], []),
    ],
)
def test_linked_rule_globs_inherited_only_when_scoped_and_no_explicit_paths(
    rule: Rule, hook_paths: list[str], expected: list[str]
) -> None:
    matcher = {"pre_tool_use": {"tools": ["edit"], "paths": hook_paths}}
    hook = sample_hook(linked_rule="pii-handling", matcher=matcher)

    (resolved,) = _resolve([hook], rules=[rule]).resolved

    assert resolved.matcher["pre_tool_use"].paths == expected
    assert resolved.matcher["pre_tool_use"].tools == ["edit"]


def test_linked_rule_globs_never_added_to_events_without_a_paths_dimension() -> None:
    rule = _rule(scope="scoped", globs=["**/*.sql"])
    hook = sample_hook(
        linked_rule="pii-handling",
        events=["pre_tool_use", "stop"],
        decisions=["deny", "none"],
    )

    (resolved,) = _resolve([hook], rules=[rule]).resolved

    assert resolved.matcher["pre_tool_use"].paths == ["**/*.sql"]
    assert resolved.matcher["stop"].paths == []


# --- adapters: supports ∩ [hooks] adapters ---------------------------------------


def test_no_supported_adapter_enabled_is_skipped() -> None:
    hook = sample_hook(supports=["opencode"])

    skipped = _only_skip(_resolve([hook], adapters=["claude_code", "continue"]))

    assert skipped.reason == (
        "no adapter it supports (['opencode']) receives hooks; [hooks] adapters: ['claude_code']"
    )


def test_explicit_hook_adapters_narrow_the_enabled_ones() -> None:
    hook = sample_hook(supports=["claude_code", "opencode"])
    cfg = HooksConfig(enabled=True, adapters=("opencode",))

    (resolved,) = _resolve([hook], cfg=cfg).resolved

    assert resolved.supports == ("opencode",)


def test_default_hook_adapters_are_the_enabled_hook_capable_ones() -> None:
    hook = sample_hook(supports=["claude_code", "opencode"])

    (resolved,) = _resolve([hook], adapters=["continue", "opencode"]).resolved

    assert resolved.supports == ("opencode",)


def test_hook_adapter_that_renders_no_hooks_is_warned() -> None:
    cfg = HooksConfig(enabled=True, adapters=("claude-code", "opencode"))

    view = _resolve([], cfg=cfg, adapters=["claude_code"])

    assert view.warnings == [
        "[hooks] adapters lists 'claude-code', which is not an enabled hook-capable adapter "
        "(claude_code, opencode); it renders no hooks",
        "[hooks] adapters lists 'opencode', which is not an enabled hook-capable adapter "
        "(claude_code, opencode); it renders no hooks",
    ]


# --- on_error clamp (§A.2) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("events", "declared", "expected"),
    [
        (["pre_tool_use", "stop"], "ask", {"pre_tool_use": "ask", "stop": "open"}),
        (
            ["user_prompt_submit", "post_tool_use"],
            "deny",
            {"user_prompt_submit": "deny", "post_tool_use": "open"},
        ),
        (["session_start"], "open", {"session_start": "open"}),
    ],
)
def test_on_error_clamped_to_open_per_event(
    events: list[str], declared: str, expected: dict[str, str]
) -> None:
    hook = sample_hook(OVERLAY, events=events, on_error=declared, decisions=["none"])

    (resolved,) = _resolve([hook]).resolved

    assert resolved.on_error == expected


# --- config layers: guardrails domain, then [hooks.<id>] (§A.6, §B.1, §B.3) ----------


def _guard_x(config: dict[str, Any], **overrides: Any) -> Hook:
    return sample_hook(OVERLAY, handler={"builtin": "guard_x", "config": config}, **overrides)


def _schemas(domain: str | None = None, **specs: ConfigKeySpec) -> FakeHandlerSchemas:
    domains = {} if domain is None else {"guard_x": domain}
    return FakeHandlerSchemas({"guard_x": dict(specs)}, domains=domains)


def test_guardrails_domain_merged_with_key_policies() -> None:
    hook = _guard_x({"protected_branches": ["main"], "mode": "warn"})
    guardrails = parse_guardrails_config({"git": {"protected_branches": ["develop"]}})
    schemas = _schemas("git", protected_branches=ConfigKeySpec("extend"))

    view = _resolve([hook], guardrails=guardrails, schemas=schemas)

    assert _config(view) == {"protected_branches": ["main", "develop"], "mode": "warn"}


def test_guardrails_defaults_never_override_a_layer_value() -> None:
    hook = _guard_x({"protected_branches": ["trunk"]})

    view = _resolve([hook], guardrails=GuardrailsConfig(), schemas=_schemas("git"))

    assert _config(view) == {"protected_branches": ["trunk"]}


def test_guardrails_apply_only_to_handlers_that_declare_the_domain() -> None:
    guardrails = parse_guardrails_config({"git": {"protected_branches": ["develop"]}})

    view = _resolve([_guard_x({})], guardrails=guardrails, schemas=_schemas(None))

    assert _config(view) == {}


def test_consumer_layer_merges_last_with_key_policies() -> None:
    hook = _guard_x({"mode": "block", "message": "engine", "rows": ["a"]})
    cfg = HooksConfig(
        enabled=True, per_hook={"guard-x": {"mode": "off", "message": "ours", "rows": ["b"]}}
    )
    schemas = _schemas(rows=ConfigKeySpec("extend"), mode=ConfigKeySpec("strictest", order=_MODES))

    view = _resolve([hook], cfg=cfg, schemas=schemas)

    assert _config(view) == {"mode": "block", "message": "ours", "rows": ["a", "b"]}


def test_consumer_layer_relax_keys_ignored_for_mandatory_with_warning() -> None:
    hook = _guard_x({"allow_paths": ["fixtures/**"]}, mandatory=True)
    cfg = HooksConfig(enabled=True, per_hook={"guard-x": {"allow_paths": ["**"], "max": 3}})
    guardrails = parse_guardrails_config({"secrets": {"allow_paths": ["tests/**"]}})
    schemas = _schemas("secrets", allow_paths=ConfigKeySpec("relax"))

    view = _resolve([hook], cfg=cfg, guardrails=guardrails, schemas=schemas)

    assert _config(view) == {"allow_paths": ["fixtures/**"], "max": 3}
    assert view.warnings == [
        "[guardrails.secrets] allow_paths is ignored for 'guard-x': a mandatory hook's "
        "relax keys cannot be loosened by the consumer",
        "[hooks.guard-x] allow_paths is ignored for 'guard-x': a mandatory hook's "
        "relax keys cannot be loosened by the consumer",
    ]


def test_consumer_layer_relax_keys_apply_to_non_mandatory_hooks() -> None:
    hook = _guard_x({"allow_paths": ["fixtures/**"]})
    cfg = HooksConfig(enabled=True, per_hook={"guard-x": {"allow_paths": ["tests/**"]}})

    view = _resolve([hook], cfg=cfg, schemas=_schemas(allow_paths=ConfigKeySpec("relax")))

    assert _config(view) == {"allow_paths": ["fixtures/**", "tests/**"]}
    assert view.warnings == []


def test_consumer_layer_reaches_external_handlers_as_replace() -> None:
    handler = {"command": "python", "script": "scripts/check.py", "config": {"limit": 5}}
    hook = sample_hook(OVERLAY, handler=handler)
    cfg = HooksConfig(enabled=True, per_hook={"guard-x": {"limit": 9}})

    assert _config(_resolve([hook], cfg=cfg)) == {"limit": 9}


def test_per_event_handlers_each_get_the_layers() -> None:
    handlers = {
        "stop": {"builtin": "guard_x", "config": {"rows": ["a"]}},
        "pre_tool_use": {"builtin": "guard_x:pre_edit"},
    }
    hook = sample_hook(OVERLAY, events=["stop", "pre_tool_use"], handler=None, handlers=handlers)
    cfg = HooksConfig(enabled=True, per_hook={"guard-x": {"rows": ["b"]}})

    (resolved,) = _resolve([hook], cfg=cfg).resolved

    assert resolved.handlers["stop"].config == {"rows": ["b"]}
    assert resolved.handlers["pre_tool_use"].name == "guard_x:pre_edit"
    assert resolved.handlers["pre_tool_use"].config == {"rows": ["b"]}


# --- purity ------------------------------------------------------------------------


def test_resolution_never_mutates_its_inputs() -> None:
    hook = _guard_x(
        {"rows": ["a"]},
        matcher={"pre_tool_use": {"tools": ["edit"]}},
        linked_rule="pii-handling",
    )
    rule = _rule(scope="scoped", globs=["**/*.sql"])
    cfg = HooksConfig(enabled=True, per_hook={"guard-x": {"rows": ["b"]}})
    before = (copy.deepcopy(hook), copy.deepcopy(rule), copy.deepcopy(cfg))

    view = _resolve([hook], cfg=cfg, rules=[rule], schemas=_schemas(rows=ConfigKeySpec("extend")))
    view.resolved[0].handlers["pre_tool_use"].config["rows"].append("c")
    view.resolved[0].matcher["pre_tool_use"].paths.append("x")

    assert (hook, rule, cfg) == before


def test_resolved_order_follows_the_input_order() -> None:
    hooks = [sample_hook(id="b-hook"), sample_hook(id="a-hook", tier="opt-in"), sample_hook(id="c")]

    view = _resolve(hooks)

    assert _ids(view) == ["b-hook", "c"]
    assert [skipped.id for skipped in view.skipped] == ["a-hook"]
