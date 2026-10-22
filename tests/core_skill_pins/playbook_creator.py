"""Pins of core skill ``playbook-creator`` (prU D70, D74, D75, D78(18); C-playbook-creator-01, -02).

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
#: A skill's SKILL.md in any layer.
_SKILL_MD_GLOBS: Final = (
    "catalog/**/skills/*/SKILL.md",
    "playbook/skills/*/SKILL.md",
    "src/*/resources/skills/*/SKILL.md",
)
#: A hook directory in any layer.
_HOOK_GLOBS: Final = (
    "catalog/**/hooks/**/HOOK.md",
    "catalog/**/hooks/**/HOOK.md.j2",
    "playbook/hooks/**",
    "src/*/resources/hooks/**",
)
_SKILL_TAGS: Final = ("playbook", "skills")
_HOOK_TAGS: Final = ("playbook", "hooks")

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
        "playbook-skill-sections",
        "playbook-skill-md",
        "playbook-skill-files",
        "playbook-hook-definition",
        "playbook-hook-guardrails",
        "playbook-prompt-frontmatter",
        "playbook-eval-samples",
        "playbook-plugin-layout",
        "playbook-third-party-content",
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
        "playbook-skill-sections": RulePin(
            applies_if=_LAYER,
            globs=_SKILL_MD_GLOBS,
            priority=40,
            name="Skill sections",
            tags=_SKILL_TAGS,
            section="skills",
        ),
        "playbook-skill-md": RulePin(
            applies_if=_LAYER,
            globs=_SKILL_MD_GLOBS,
            priority=41,
            name="SKILL.md",
            tags=_SKILL_TAGS,
            section="skills",
        ),
        "playbook-skill-files": RulePin(
            applies_if=_LAYER,
            globs=tuple(
                f"{root}/{kind}/**"
                for root in ("catalog/**/skills/*", "playbook/skills/*", "src/*/resources/skills/*")
                for kind in ("references", "scripts", "examples")
            ),
            priority=42,
            name="Skill files",
            tags=_SKILL_TAGS,
            section="skills",
        ),
        "playbook-hook-definition": RulePin(
            applies_if=_LAYER,
            globs=_HOOK_GLOBS,
            priority=43,
            name="Hook definition",
            tags=_HOOK_TAGS,
            section="hooks",
        ),
        "playbook-hook-guardrails": RulePin(
            applies_if=_LAYER,
            globs=_HOOK_GLOBS,
            priority=44,
            name="Hook guardrails",
            tags=_HOOK_TAGS,
            section="hooks",
        ),
        "playbook-prompt-frontmatter": RulePin(
            applies_if=_LAYER,
            globs=(
                "catalog/**/prompts/*.md",
                "catalog/**/prompts/*.md.j2",
                "playbook/prompts/*",
                "src/*/resources/prompts/*",
            ),
            priority=45,
            name="Prompt frontmatter",
            tags=("playbook", "prompts"),
            section="prompts",
        ),
        "playbook-eval-samples": RulePin(
            applies_if=_LAYER,
            globs=(
                "catalog/**/eval_samples/**",
                "playbook/eval_samples/**",
                "src/*/resources/eval_samples/**",
            ),
            priority=46,
            name="Eval samples",
            tags=("playbook", "evals"),
            section="prompts",
        ),
        "playbook-plugin-layout": RulePin(
            applies_if=_LAYER,
            globs=("catalog/plugins/*/*", "src/*/resources/**", "src/*/__init__.py"),
            priority=60,
            name="Plugin and overlay layout",
            tags=("playbook", "plugins"),
            section="plugins",
        ),
        "playbook-third-party-content": RulePin(
            applies_if=_LAYER,
            globs=(
                "catalog/**/ATTRIBUTIONS.md",
                "catalog/**/LICENSE*",
                "src/*/resources/**/ATTRIBUTIONS.md",
                "playbook/**/ATTRIBUTIONS.md",
            ),
            priority=61,
            name="Third-party content",
            tags=("playbook", "plugins", "licensing"),
            section="plugins",
        ),
    },
)
