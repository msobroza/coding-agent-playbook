"""Pins of core skill ``playbook-creator`` (prU D70; C-playbook-creator-02).

Every member gates on ``playbook_layer``, so the skill is checked on the authoring
probe (the reference probe plus an empty ``playbook/`` layer), which activates
every member pinned here.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_LAYER: Final = {"playbook_layer": True}
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
    probe_inactive=frozenset(),
    probe="authoring",
    section_ids=("layers", "rules", "validation", "skills", "hooks", "prompts", "plugins"),
    rules={
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
