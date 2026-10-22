"""Pins of core skill ``playbook-creator`` (prU D70, D74, D75, D78(18); C-playbook-creator-01).

Every member gates on ``playbook_layer``, so the skill is checked on the authoring
probe (the reference probe plus an empty ``playbook/`` layer). The engine-only
``playbook-engine-catalog-gate`` also needs ``catalog/core``, which that probe
lacks, so it is the one probe-inactive member.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_LAYER: Final = {"playbook_layer": True}
_LAYER_GLOBS: Final = ("catalog/**", "playbook/**", "src/*/resources/**")
#: A rule file in any layer's rules/ directory, a skill's included.
_RULE_GLOBS: Final = (
    "catalog/**/rules/**/*.md",
    "catalog/**/rules/**/*.md.j2",
    "playbook/**/rules/**/*.md",
    "playbook/**/rules/**/*.md.j2",
    "src/*/resources/**/rules/**/*.md",
    "src/*/resources/**/rules/**/*.md.j2",
)
_LAYER_TAGS: Final = ("playbook", "layers")
_RULE_TAGS: Final = ("playbook", "rules")
_VALIDATION_TAGS: Final = ("playbook", "validation")

PINS: Final = CoreSkillPins(
    skill_id="playbook-creator",
    where="Playbook content in catalog/, playbook/ or an overlay's resources/",
    members=(
        "playbook-ask-for-missing-inputs",
        "playbook-layer-placement",
        "playbook-override-by-id",
        "playbook-rule-frontmatter",
        "playbook-rule-ids",
        "playbook-rule-gates",
        "playbook-rule-templates",
        "playbook-rule-body",
        "playbook-validate-and-sync",
        "playbook-engine-catalog-gate",
    ),
    probe_inactive=frozenset({"playbook-engine-catalog-gate"}),
    probe="authoring",
    section_ids=("layers", "rules", "validation", "skills", "hooks", "prompts", "plugins"),
    rules={
        "playbook-ask-for-missing-inputs": RulePin(
            applies_if=_LAYER,
            globs=("catalog/**", "playbook/**"),
            priority=20,
            name="Ask for missing inputs",
            tags=_LAYER_TAGS,
            section="layers",
        ),
        "playbook-layer-placement": RulePin(
            applies_if=_LAYER,
            globs=_LAYER_GLOBS,
            priority=21,
            name="Layer placement",
            tags=_LAYER_TAGS,
            section="layers",
        ),
        "playbook-override-by-id": RulePin(
            applies_if=_LAYER,
            globs=_LAYER_GLOBS,
            priority=22,
            name="Override by id",
            tags=_LAYER_TAGS,
            section="layers",
        ),
        "playbook-rule-frontmatter": RulePin(
            applies_if=_LAYER,
            globs=_RULE_GLOBS,
            priority=23,
            name="Rule frontmatter",
            tags=_RULE_TAGS,
            section="rules",
        ),
        "playbook-rule-ids": RulePin(
            applies_if=_LAYER,
            globs=_RULE_GLOBS,
            priority=24,
            name="Rule ids",
            tags=_RULE_TAGS,
            section="rules",
        ),
        "playbook-rule-gates": RulePin(
            applies_if=_LAYER,
            globs=_RULE_GLOBS,
            priority=25,
            name="Rule gates",
            tags=_RULE_TAGS,
            section="rules",
        ),
        "playbook-rule-templates": RulePin(
            applies_if=_LAYER,
            globs=_RULE_GLOBS,
            priority=26,
            name="Rule templates",
            tags=_RULE_TAGS,
            section="rules",
        ),
        "playbook-rule-body": RulePin(
            applies_if=_LAYER,
            globs=_RULE_GLOBS,
            priority=27,
            name="Rule body",
            tags=_RULE_TAGS,
            section="rules",
        ),
        "playbook-validate-and-sync": RulePin(
            applies_if=_LAYER,
            globs=(*_LAYER_GLOBS, ".coding-agent-playbook.toml"),
            priority=28,
            name="Validate and sync",
            tags=_VALIDATION_TAGS,
            section="validation",
        ),
        "playbook-engine-catalog-gate": RulePin(
            applies_if={"playbook_layer": True, "has_file": ["catalog/core"]},
            globs=(
                "catalog/**",
                "tests/core_skill_pins/**",
                "tests/hook_runtime/handlers/**",
                "tests/plugins/**",
                "tests/core_skills/**",
            ),
            priority=29,
            name="Engine catalog gate",
            tags=_VALIDATION_TAGS,
            section="validation",
        ),
    },
)
