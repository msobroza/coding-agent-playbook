"""skill-nudge's per-skill glob table, derived at sync (specs/prS-skills-context.md 8.5.2).

``skill_glob_rows`` groups the globs of the member rules this sync renders by
the skill that owns them (ADR 0001), so the runtime can name the skill that
covers an edited file without importing the catalog. Pure functions of the
rules: no repository needed.
"""

from __future__ import annotations

from typing import Literal

from coding_agent_playbook._guard_config_skills import SKILL_NUDGE_HOOK_ID, skill_glob_rows
from coding_agent_playbook.guard_config import GuardConfigInputs, render_guard_config
from coding_agent_playbook.hooks_config import GuardrailsConfig, HooksConfig
from coding_agent_playbook.types import Rule, RuleFrontmatter
from tests.hook_samples import resolved_hook


def _rule(
    rule_id: str,
    skill: str | None,
    globs: list[str],
    *,
    scope: Literal["always", "scoped"] = "scoped",
) -> Rule:
    """A rendered rule with ``skill`` and ``globs``; the body is irrelevant to the table."""
    fm = RuleFrontmatter(
        id=rule_id, name=rule_id, description="d", scope=scope, globs=globs, skill=skill
    )
    return Rule(fm, "Body.\n", "Body.\n", False, None, "coding_agent_playbook")


def test_skill_glob_rows_group_member_globs_by_skill() -> None:
    rules = [
        _rule("python-typing", "python-coding", ["**/*.py"]),
        _rule("pytest", "python-testing", ["tests/**/*.py"]),
        _rule("python-error-handling", "python-coding", ["src/**/*.py"]),
    ]

    assert skill_glob_rows(rules) == [
        {"id": "python-coding", "globs": ["**/*.py", "src/**/*.py"]},
        {"id": "python-testing", "globs": ["tests/**/*.py"]},
    ]


def test_rules_without_skill_or_globs_add_nothing() -> None:
    rules = [
        _rule("python-house-style", None, [], scope="always"),
        _rule("project-context", None, ["**/*.py"], scope="always"),
        _rule("python-pure-core", "python-coding", []),
    ]

    assert skill_glob_rows(rules) == []


def test_rows_are_sorted_and_globs_deduplicated() -> None:
    rules = [
        _rule("fastapi-app-wiring", "python-tooling", ["**/api/**/*.py", "tests/**/*.py"]),
        _rule("ml-serialization-security", "ml-data", ["**/*.py"]),
        _rule("fastapi-error-boundaries", "python-tooling", ["**/*.py", "tests/**/*.py"]),
    ]

    assert skill_glob_rows(rules) == [
        {"id": "ml-data", "globs": ["**/*.py"]},
        {"id": "python-tooling", "globs": ["**/api/**/*.py", "tests/**/*.py", "**/*.py"]},
    ]


def test_skill_nudge_config_is_derived_and_replaces_a_layer_value() -> None:
    """A layer's ``skills`` (no schema declares it) never survives: sync's table wins."""
    layered = {"skills": [{"id": "rogue", "globs": ["**"]}], "keep": True}
    nudge = resolved_hook(SKILL_NUDGE_HOOK_ID, events=("post_tool_use",), config=layered)
    rows = skill_glob_rows([_rule("pytest", "python-testing", ["tests/**/*.py"])])
    inputs = GuardConfigInputs(
        hooks=[nudge, resolved_hook("guard-x")],
        hooks_config=HooksConfig(enabled=True),
        guardrails=GuardrailsConfig(),
        engine_version="0.2.0",
        skill_globs=rows,
    )

    hooks = render_guard_config(inputs)["hooks"]

    assert hooks[SKILL_NUDGE_HOOK_ID]["handlers"]["post_tool_use"]["config"] == {
        "keep": True,
        "skills": [{"id": "python-testing", "globs": ["tests/**/*.py"]}],
    }
    assert "skills" not in hooks["guard-x"]["handlers"]["pre_tool_use"]["config"]
